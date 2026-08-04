import {
  defaultScheduler,
  notifyManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import dayjs, { type Dayjs } from "dayjs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  shanghaiDateStart,
  shanghaiToday,
} from "../../utils/shanghaiTime";
import { WearableHealthTab } from "./WearableHealthTab";

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));
const FIXED_SYSTEM_TIME = new Date("2026-08-03T04:00:00Z");

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

vi.mock("@ant-design/charts", () => ({
  DualAxes: (props: Record<string, unknown>) => (
    <pre data-testid="wearable-chart">{JSON.stringify(props)}</pre>
  ),
  Line: (props: Record<string, unknown>) => (
    <pre data-testid="wearable-chart">{JSON.stringify(props)}</pre>
  ),
}));

vi.mock("antd", async (importOriginal) => {
  const actual = await importOriginal<typeof import("antd")>();
  type RangePickerProps = {
    "aria-label"?: string;
    onChange?: (value: [Dayjs, Dayjs] | null) => void;
  };
  const RangePicker = ({ "aria-label": ariaLabel, onChange }: RangePickerProps) => (
    <button
      aria-label={ariaLabel}
      type="button"
      onClick={() => onChange?.([dayjs("2026-06-01"), dayjs("2026-07-15")])}
    >
      选择健康日期范围
    </button>
  );
  return {
    ...actual,
    DatePicker: {
      ...actual.DatePicker,
      RangePicker,
    },
  };
});

const capabilities = {
  ring: false,
  measure_heart_rate: true,
  measure_blood_pressure: true,
  measure_blood_oxygen: true,
};

function boundSyncStatus(
  overrides: Record<string, unknown> = {},
) {
  return {
    is_bound: true,
    binding_id: 17,
    bound_at: "2026-07-24T18:30:00+08:00",
    device_id: 7,
    model: "M1",
    device_short_code: "0826",
    last_device_status: "online",
    last_battery_level: 82,
    last_communication_at: "2026-07-24T02:00:00Z",
    capabilities,
    last_sync_at: null,
    metrics: [],
    ...overrides,
  };
}

function unboundSyncStatus() {
  return {
    is_bound: false,
    binding_id: null,
    bound_at: null,
    device_id: null,
    model: null,
    device_short_code: null,
    last_device_status: null,
    last_battery_level: null,
    last_communication_at: null,
    capabilities: {
      ...capabilities,
      measure_heart_rate: false,
      measure_blood_pressure: false,
      measure_blood_oxygen: false,
    },
    last_sync_at: null,
    metrics: [],
  };
}

function renderTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <WearableHealthTab patientId={201} projectPatientId={9001} />
    </QueryClientProvider>,
  );
  return { ...result, queryClient };
}

function dailySummaryResponse(start: string, end: string) {
  const items = [];
  for (
    let cursor = shanghaiDateStart(end);
    !cursor.isBefore(shanghaiDateStart(start));
    cursor = cursor.subtract(1, "day")
  ) {
    items.push({
      record_date: cursor.format("YYYY-MM-DD"),
      steps: 0,
    });
  }
  return Promise.resolve({ data: { start, end, items } });
}

describe("WearableHealthTab", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(FIXED_SYSTEM_TIME);
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
            bound_at: "2026-07-24T18:30:00+08:00",
            device_id: 7,
            model: "M1",
            device_short_code: "0826",
            last_device_status: "online",
            last_battery_level: 82,
            last_communication_at: "2026-07-24T02:00:00Z",
            capabilities,
            last_sync_at: "2026-07-24T02:00:00Z",
            metrics: [],
          },
        });
      }
      if (url.includes("measurements")) {
        return Promise.resolve({
          data: {
            metric_type: "heart_rate",
            bucket: "raw",
            start: "2026-06-25",
            end: "2026-07-24",
            total: 0,
            page: 1,
            page_size: 500,
            next_page: null,
            items: [],
          },
        });
      }
      if (url.includes("daily-summaries")) return Promise.resolve({ data: { items: [{ record_date: "2026-07-23", steps: 6000 }] } });
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    mockPost.mockResolvedValue({ data: { status: "queued" } });
  });

  afterEach(() => {
    cleanup();
    notifyManager.setScheduler(defaultScheduler);
    vi.useRealTimers();
  });

  it("固定页面日期基准为上海 2026-08-03", () => {
    expect(shanghaiToday().format("YYYY-MM-DD")).toBe("2026-08-03");
    expect(Date.now()).toBe(FIXED_SYSTEM_TIME.getTime());
  });

  it("加载快捷日期筛选、四项趋势并并行请求三项原始测量，且不自动发起通信测试", async () => {
    const today = shanghaiToday();
    const defaultStart = today.subtract(29, "day").format("YYYY-MM-DD");
    const defaultEnd = today.format("YYYY-MM-DD");
    renderTab();

    expect(await screen.findByText("设备 0826")).toBeInTheDocument();
    expect(screen.getByText("近 7 天")).toBeInTheDocument();
    expect(screen.getByText("近 30 天")).toBeInTheDocument();
    expect(screen.getByText("自定义")).toBeInTheDocument();
    expect(screen.queryByLabelText("健康指标")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("图表间隔")).not.toBeInTheDocument();
    expect(screen.getByText("日汇总")).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
    await waitFor(() => {
      for (const metricType of [
        "heart_rate",
        "blood_pressure",
        "blood_oxygen",
      ]) {
        expect(mockGet).toHaveBeenCalledWith(
          "/wearables/patients/201/measurements/",
          expect.objectContaining({
            params: expect.objectContaining({
              project_patient: 9001,
              metric_type: metricType,
              bucket: "raw",
              start: defaultStart,
              end: defaultEnd,
            }),
            signal: expect.any(AbortSignal),
          }),
        );
      }
    });
    expect(screen.getByText("心率趋势")).toBeInTheDocument();
    expect(screen.getByText("血压趋势")).toBeInTheDocument();
    expect(screen.getByText("血氧趋势")).toBeInTheDocument();
    expect(screen.getByText("步数趋势")).toBeInTheDocument();
  });

  it("趋势卡片不展示主动测量与能力提示但保留顶部设备操作", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: boundSyncStatus({
            capabilities: {
              ...boundSyncStatus().capabilities,
              measure_heart_rate: true,
              measure_blood_pressure: true,
              measure_blood_oxygen: true,
            },
          }),
        });
      }
      if (url.includes("measurements") || url.includes("daily-summaries")) {
        return Promise.resolve({ data: { items: [] } });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderTab();

    expect(await screen.findByText("心率趋势")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "测量心率" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "测量血压" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "测量血氧" })).not.toBeInTheDocument();
    expect(screen.queryByText("该型号能力尚未验证")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /通信测试/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /主动同步/ })).toBeInTheDocument();
  });

  it("点击近 7 天后按上海今天和之前六天重查三项测量与日汇总", async () => {
    const today = shanghaiToday();
    const start = today.subtract(6, "day").format("YYYY-MM-DD");
    const end = today.format("YYYY-MM-DD");
    renderTab();
    await screen.findByText("设备 0826");

    fireEvent.click(screen.getByText("近 7 天"));

    await waitFor(() => {
      for (const metricType of [
        "heart_rate",
        "blood_pressure",
        "blood_oxygen",
      ]) {
        expect(mockGet).toHaveBeenCalledWith(
          "/wearables/patients/201/measurements/",
          expect.objectContaining({
            params: expect.objectContaining({
              metric_type: metricType,
              start,
              end,
              bucket: "raw",
            }),
          }),
        );
      }
      expect(mockGet).toHaveBeenCalledWith(
        "/wearables/patients/201/daily-summaries/",
        expect.objectContaining({
          params: expect.objectContaining({
            project_patient: 9001,
            start,
            end,
          }),
        }),
      );
    });
  });

  it("趋势日期切换不重新查询或重置日汇总历史", async () => {
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          return dailySummaryResponse(
            String(config?.params?.start),
            String(config?.params?.end),
          );
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );
    renderTab();

    await screen.findByRole("button", { name: "获取更多" });
    const historyCallsBefore = mockGet.mock.calls.filter(
      ([url, config]) =>
        String(url).includes("daily-summaries") &&
        !(config as { params?: Record<string, unknown> }).params
          ?.project_patient,
    ).length;

    fireEvent.click(screen.getByText("近 7 天"));

    await waitFor(() => {
      const trendCalls = mockGet.mock.calls.filter(
        ([url, config]) =>
          String(url).includes("daily-summaries") &&
          (config as { params?: Record<string, unknown> }).params
            ?.project_patient === 9001,
      );
      expect(trendCalls.at(-1)?.[1]).toMatchObject({
        params: {
          project_patient: 9001,
          start: "2026-07-28",
          end: "2026-08-03",
        },
      });
    });

    const historyCallsAfter = mockGet.mock.calls.filter(
      ([url, config]) =>
        String(url).includes("daily-summaries") &&
        !(config as { params?: Record<string, unknown> }).params
          ?.project_patient,
    ).length;
    expect(historyCallsAfter).toBe(historyCallsBefore);
  });

  it("日汇总每次追加更早五天并在绑定日期停止", async () => {
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          const start = String(config?.params?.start);
          const end = String(config?.params?.end);
          return dailySummaryResponse(start, end);
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );

    renderTab();

    expect(await screen.findByText("2026-08-03")).toBeInTheDocument();
    expect(screen.getByText("2026-07-30")).toBeInTheDocument();
    expect(screen.queryByText("2026-07-29")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
    expect(await screen.findByText("2026-07-29")).toBeInTheDocument();
    expect(screen.getByText("2026-07-25")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
    expect(await screen.findByText("2026-07-24")).toBeInTheDocument();
    expect(screen.getByText("没有更多数据了")).toBeInTheDocument();

    const dates = screen
      .getAllByRole("row")
      .map((row) => row.firstElementChild?.textContent)
      .filter((date): date is string => /^\d{4}-\d{2}-\d{2}$/.test(date ?? ""));
    expect(dates).toEqual([
      "2026-08-03",
      "2026-08-02",
      "2026-08-01",
      "2026-07-31",
      "2026-07-30",
      "2026-07-29",
      "2026-07-28",
      "2026-07-27",
      "2026-07-26",
      "2026-07-25",
      "2026-07-24",
    ]);
  });

  it("日汇总初始失败时提供重新加载入口", async () => {
    let failed = false;
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          if (config?.params?.project_patient) {
            return dailySummaryResponse(
              String(config.params.start),
              String(config.params.end),
            );
          }
          if (!failed) {
            failed = true;
            return Promise.reject(new Error("history unavailable"));
          }
          return dailySummaryResponse(
            String(config?.params?.start),
            String(config?.params?.end),
          );
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );

    renderTab();

    expect(await screen.findByText("加载日汇总失败")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    expect(await screen.findByText("2026-08-03")).toBeInTheDocument();
  });

  it("加载更多失败时保留首批数据并允许重试", async () => {
    let secondPageAttempts = 0;
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          const start = String(config?.params?.start);
          const end = String(config?.params?.end);
          if (!config?.params?.project_patient && start === "2026-07-25") {
            secondPageAttempts += 1;
            if (secondPageAttempts === 1) {
              return Promise.reject(new Error("next page unavailable"));
            }
          }
          return dailySummaryResponse(start, end);
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );

    renderTab();

    expect(await screen.findByText("2026-08-03")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "获取更多" }));

    const retry = await screen.findByRole("button", {
      name: "获取更多失败，点击重试",
    });
    expect(screen.getByText("2026-08-03")).toBeInTheDocument();

    fireEvent.click(retry);
    expect(await screen.findByText("2026-07-29")).toBeInTheDocument();
  });

  it("加载下一批期间保留首批数据并展示正在获取", async () => {
    let resolveNextPage!: (value: {
      data: {
        start: string;
        end: string;
        items: Array<{ record_date: string; steps: number }>;
      };
    }) => void;
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          const start = String(config?.params?.start);
          const end = String(config?.params?.end);
          if (config?.params?.project_patient || start === "2026-07-30") {
            return dailySummaryResponse(start, end);
          }
          return new Promise((resolve) => {
            resolveNextPage = resolve;
          });
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );
    renderTab();

    expect(await screen.findByText("2026-08-03")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "获取更多" }));

    expect(
      await screen.findByRole("button", { name: "正在获取…" }),
    ).toBeDisabled();
    expect(screen.getByText("2026-08-03")).toBeInTheDocument();

    resolveNextPage({
      data: {
        start: "2026-07-25",
        end: "2026-07-29",
        items: [{ record_date: "2026-07-29", steps: 0 }],
      },
    });
    expect(await screen.findByText("2026-07-29")).toBeInTheDocument();
  });

  it("主动同步刷新已加载分页但不收回历史行", async () => {
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          return dailySummaryResponse(
            String(config?.params?.start),
            String(config?.params?.end),
          );
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );
    renderTab();

    await screen.findByText("2026-08-03");
    fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
    expect(await screen.findByText("2026-07-25")).toBeInTheDocument();
    const historyWindowCallCount = (start: string) =>
      mockGet.mock.calls.filter(
        ([url, config]) =>
          String(url).includes("daily-summaries") &&
          !(config as { params?: Record<string, unknown> }).params
            ?.project_patient &&
          (config as { params?: Record<string, unknown> }).params?.start ===
            start,
      ).length;
    const historyCallsBeforeSync = {
      first: historyWindowCallCount("2026-07-30"),
      second: historyWindowCallCount("2026-07-25"),
    };

    fireEvent.click(screen.getByRole("button", { name: /主动同步/ }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/wearables/patients/201/sync/",
        {},
      );
    });
    await waitFor(() => {
      expect(historyWindowCallCount("2026-07-30")).toBeGreaterThan(
        historyCallsBeforeSync.first,
      );
      expect(historyWindowCallCount("2026-07-25")).toBeGreaterThan(
        historyCallsBeforeSync.second,
      );
    });
    expect(screen.getByText("2026-07-25")).toBeInTheDocument();
  });

  it("主动同步进行中切换趋势日期仍保持锁定并在成功后刷新当前趋势与全部历史页", async () => {
    let resolveSync!: (value: { data: { status: "queued" } }) => void;
    mockPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSync = resolve;
        }),
    );
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          return dailySummaryResponse(
            String(config?.params?.start),
            String(config?.params?.end),
          );
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );
    renderTab();

    await screen.findByText("2026-08-03");
    fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
    expect(await screen.findByText("2026-07-25")).toBeInTheDocument();

    const callCount = (
      kind: "measurement" | "daily-trend" | "daily-history",
      start?: string,
    ) =>
      mockGet.mock.calls.filter(([url, config]) => {
        const params = (
          config as { params?: Record<string, unknown> } | undefined
        )?.params;
        if (kind === "measurement") {
          return (
            String(url).includes("measurements") &&
            params?.metric_type === "heart_rate"
          );
        }
        if (kind === "daily-trend") {
          return (
            String(url).includes("daily-summaries") &&
            params?.project_patient === 9001
          );
        }
        return (
          String(url).includes("daily-summaries") &&
          !params?.project_patient &&
          params?.start === start
        );
      }).length;

    fireEvent.click(screen.getByRole("button", { name: /主动同步/ }));
    expect(screen.getByRole("button", { name: /主动同步/ })).toBeDisabled();

    fireEvent.click(screen.getByText("近 7 天"));
    await waitFor(() => {
      const dailyTrendCalls = mockGet.mock.calls.filter(
        ([url, config]) =>
          String(url).includes("daily-summaries") &&
          (config as { params?: Record<string, unknown> }).params
            ?.project_patient === 9001,
      );
      expect(dailyTrendCalls.at(-1)?.[1]).toMatchObject({
        params: {
          start: "2026-07-28",
          end: "2026-08-03",
        },
      });
    });
    expect(screen.getByRole("button", { name: /主动同步/ })).toBeDisabled();

    const callsBeforeCompletion = {
      measurement: callCount("measurement"),
      dailyTrend: callCount("daily-trend"),
      firstHistory: callCount("daily-history", "2026-07-30"),
      secondHistory: callCount("daily-history", "2026-07-25"),
    };

    resolveSync({ data: { status: "queued" } });

    expect(
      await screen.findByText("健康数据同步已排队，尚未确认新数据到达。"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(callCount("measurement")).toBeGreaterThan(
        callsBeforeCompletion.measurement,
      );
      expect(callCount("daily-trend")).toBeGreaterThan(
        callsBeforeCompletion.dailyTrend,
      );
      expect(callCount("daily-history", "2026-07-30")).toBeGreaterThan(
        callsBeforeCompletion.firstHistory,
      );
      expect(callCount("daily-history", "2026-07-25")).toBeGreaterThan(
        callsBeforeCompletion.secondHistory,
      );
    });
    expect(screen.getByText("2026-07-25")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /主动同步/ })).toBeEnabled();
  });

  it("离开设备绑定后清除其历史分页，返回时只重新加载最近五天", async () => {
    let bindingGeneration = 17;
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          const start = String(config?.params?.start);
          const end = String(config?.params?.end);
          if (config?.params?.project_patient) {
            return dailySummaryResponse(start, end);
          }
          return dailySummaryResponse(start, end).then(({ data }) => ({
            data: {
              ...data,
              items: data.items.map((item) => ({
                ...item,
                steps: bindingGeneration,
              })),
            },
          }));
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );
    const { queryClient } = renderTab();

    await screen.findByText("2026-08-03");
    fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
    expect(await screen.findByText("2026-07-25")).toBeInTheDocument();

    bindingGeneration = 19;
    act(() => {
      queryClient.setQueryData(
        ["wearable-sync-status", 201],
        boundSyncStatus({
          binding_id: 19,
          device_id: 9,
          device_short_code: "9009",
        }),
      );
    });
    expect(await screen.findByText("设备 9009")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText("2026-07-25")).not.toBeInTheDocument(),
    );

    const historyCallsBeforeReturn = mockGet.mock.calls.length;
    bindingGeneration = 17;
    act(() => {
      queryClient.setQueryData(
        ["wearable-sync-status", 201],
        boundSyncStatus(),
      );
    });

    expect(await screen.findByText("设备 0826")).toBeInTheDocument();
    await waitFor(() => {
      const returnHistoryCalls = mockGet.mock.calls
        .slice(historyCallsBeforeReturn)
        .filter(
          ([url, config]) =>
            String(url).includes("daily-summaries") &&
            !(config as { params?: Record<string, unknown> }).params
              ?.project_patient,
        );
      expect(returnHistoryCalls).toHaveLength(1);
      expect(returnHistoryCalls[0]?.[1]).toMatchObject({
        params: {
          start: "2026-07-30",
          end: "2026-08-03",
        },
      });
    });
    expect(screen.queryByText("2026-07-25")).not.toBeInTheDocument();
    const dates = screen
      .getAllByRole("row")
      .map((row) => row.firstElementChild?.textContent)
      .filter((date): date is string => /^\d{4}-\d{2}-\d{2}$/.test(date ?? ""));
    expect(dates).toEqual([
      "2026-08-03",
      "2026-08-02",
      "2026-08-01",
      "2026-07-31",
      "2026-07-30",
    ]);
  });

  it("离开绑定会中止旧分页请求，旧响应迟到时返回绑定仍只加载最近五天", async () => {
    let bindingGeneration = 17;
    let oldPageSignal: AbortSignal | undefined;
    let resolveOldPage!: (value: {
      data: {
        start: string;
        end: string;
        items: Array<{ record_date: string; steps: number }>;
      };
    }) => void;
    mockGet.mockImplementation(
      (
        url: string,
        config?: {
          params?: Record<string, unknown>;
          signal?: AbortSignal;
        },
      ) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          const start = String(config?.params?.start);
          const end = String(config?.params?.end);
          if (config?.params?.project_patient) {
            return dailySummaryResponse(start, end);
          }
          if (bindingGeneration === 17 && start === "2026-07-24") {
            oldPageSignal = config?.signal;
            return new Promise((resolve) => {
              resolveOldPage = resolve;
            });
          }
          return dailySummaryResponse(start, end).then(({ data }) => ({
            data: {
              ...data,
              items: data.items.map((item) => ({
                ...item,
                steps: bindingGeneration,
              })),
            },
          }));
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );
    const { queryClient } = renderTab();

    await screen.findByText("2026-08-03");
    fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
    expect(await screen.findByText("2026-07-25")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
    expect(
      await screen.findByRole("button", { name: "正在获取…" }),
    ).toBeDisabled();

    bindingGeneration = 19;
    await act(async () => {
      queryClient.setQueryData(
        ["wearable-sync-status", 201],
        boundSyncStatus({
          binding_id: 19,
          device_id: 9,
          device_short_code: "9009",
        }),
      );
    });
    expect(await screen.findByText("设备 9009")).toBeInTheDocument();
    await waitFor(() => expect(oldPageSignal?.aborted).toBe(true));

    const historyCallsBeforeReturn = mockGet.mock.calls.length;
    bindingGeneration = 17;
    act(() => {
      queryClient.setQueryData(
        ["wearable-sync-status", 201],
        boundSyncStatus(),
      );
    });

    expect(await screen.findByText("设备 0826")).toBeInTheDocument();
    await waitFor(() => {
      const returnHistoryCalls = mockGet.mock.calls
        .slice(historyCallsBeforeReturn)
        .filter(
          ([url, config]) =>
            String(url).includes("daily-summaries") &&
            !(config as { params?: Record<string, unknown> }).params
              ?.project_patient,
        );
      expect(returnHistoryCalls).toHaveLength(1);
      expect(returnHistoryCalls[0]?.[1]).toMatchObject({
        params: {
          start: "2026-07-30",
          end: "2026-08-03",
        },
      });
    });
    expect(screen.queryByText("2026-07-25")).not.toBeInTheDocument();

    await act(async () => {
      resolveOldPage({
        data: {
          start: "2026-07-24",
          end: "2026-07-24",
          items: [{ record_date: "2026-07-24", steps: 17 }],
        },
      });
      await Promise.resolve();
    });

    expect(screen.queryByText("2026-07-24")).not.toBeInTheDocument();
    expect(screen.queryByText("2026-07-25")).not.toBeInTheDocument();
  });

  it("同一事件循环内切换绑定会立即删除旧历史 query，返回时不复用旧分页", async () => {
    let bindingGeneration = 17;
    let resolveOldPage!: (value: {
      data: {
        start: string;
        end: string;
        items: Array<{ record_date: string; steps: number }>;
      };
    }) => void;
    mockGet.mockImplementation(
      (
        url: string,
        config?: {
          params?: Record<string, unknown>;
          signal?: AbortSignal;
        },
      ) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          const start = String(config?.params?.start);
          const end = String(config?.params?.end);
          if (config?.params?.project_patient) {
            return dailySummaryResponse(start, end);
          }
          if (bindingGeneration === 17 && start === "2026-07-24") {
            return new Promise((resolve) => {
              resolveOldPage = resolve;
            });
          }
          return dailySummaryResponse(start, end).then(({ data }) => ({
            data: {
              ...data,
              items: data.items.map((item) => ({
                ...item,
                steps: bindingGeneration,
              })),
            },
          }));
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );
    const { queryClient } = renderTab();
    const bindingAHistoryKey = [
      "wearable-daily-history",
      201,
      9001,
      17,
      "2026-07-24T18:30:00+08:00",
      "2026-08-03",
    ] as const;

    await screen.findByText("2026-08-03");
    fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
    expect(await screen.findByText("2026-07-25")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
    expect(
      await screen.findByRole("button", { name: "正在获取…" }),
    ).toBeDisabled();

    notifyManager.setScheduler((callback) => callback());
    bindingGeneration = 19;
    act(() => {
      queryClient.setQueryData(
        ["wearable-sync-status", 201],
        boundSyncStatus({
          binding_id: 19,
          device_id: 9,
          device_short_code: "9009",
        }),
      );
    });

    expect(screen.getByText("设备 9009")).toBeInTheDocument();
    expect(queryClient.getQueryData(bindingAHistoryKey)).toBeUndefined();

    bindingGeneration = 17;
    await act(async () => {
      queryClient.setQueryData(
        ["wearable-sync-status", 201],
        boundSyncStatus(),
      );
      await Promise.resolve();
    });

    expect(screen.getByText("设备 0826")).toBeInTheDocument();
    expect(screen.queryByText("2026-07-25")).not.toBeInTheDocument();
    expect(await screen.findByText("2026-08-03")).toBeInTheDocument();
    expect(
      queryClient.getQueryData<{ pages: unknown[] }>(bindingAHistoryKey)
        ?.pages,
    ).toHaveLength(1);

    await act(async () => {
      resolveOldPage({
        data: {
          start: "2026-07-24",
          end: "2026-07-24",
          items: [{ record_date: "2026-07-24", steps: 17 }],
        },
      });
      await Promise.resolve();
    });

    expect(screen.queryByText("2026-07-24")).not.toBeInTheDocument();
    expect(
      queryClient.getQueryData<{ pages: unknown[] }>(bindingAHistoryKey)
        ?.pages,
    ).toHaveLength(1);
  });

  it("切换患者后不会展示旧患者迟到的日汇总响应", async () => {
    let resolveOldHistory!: (value: {
      data: {
        items: Array<{ record_date: string; steps: number }>;
      };
    }) => void;
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          const isNextPatient = url.includes("/patients/202/");
          return Promise.resolve({
            data: boundSyncStatus({
              binding_id: isNextPatient ? 27 : 17,
              device_id: isNextPatient ? 8 : 7,
              device_short_code: isNextPatient ? "0202" : "0826",
            }),
          });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          if (config?.params?.project_patient) {
            return Promise.resolve({ data: { items: [] } });
          }
          if (url.includes("/patients/201/")) {
            return new Promise((resolve) => {
              resolveOldHistory = resolve;
            });
          }
          return Promise.resolve({
            data: {
              items: [{ record_date: "2026-08-03", steps: 202 }],
            },
          });
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <WearableHealthTab patientId={201} projectPatientId={9001} />
      </QueryClientProvider>,
    );
    await screen.findByText("设备 0826");

    rerender(
      <QueryClientProvider client={queryClient}>
        <WearableHealthTab patientId={202} projectPatientId={9002} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("设备 0202")).toBeInTheDocument();
    expect(await screen.findByText("2026-08-03")).toBeInTheDocument();

    resolveOldHistory({
      data: {
        items: [{ record_date: "2026-07-30", steps: 201 }],
      },
    });
    await act(async () => undefined);

    expect(screen.queryByText("2026-07-30")).not.toBeInTheDocument();
    expect(screen.getByText("2026-08-03")).toBeInTheDocument();
  });

  it("选择自定义日期后将范围限制为 31 天并按实际范围重查", async () => {
    renderTab();
    await screen.findByText("设备 0826");

    expect(screen.queryByLabelText("健康日期范围")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("自定义"));
    fireEvent.click(screen.getByRole("button", { name: "健康日期范围" }));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/wearables/patients/201/measurements/",
        expect.objectContaining({
          params: expect.objectContaining({
            metric_type: "heart_rate",
            start: "2026-06-15",
            end: "2026-07-15",
          }),
        }),
      );
    });
  });

  it("未绑定时显示绑定引导且不显示趋势测量按钮", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: { is_bound: false, bound_at: null, metrics: [] },
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    renderTab();

    expect(await screen.findByText("请先在患者接入中绑定穿戴设备。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "测量心率" })).not.toBeInTheDocument();
  });

  it("raw 趋势跟随 next_page 拉齐所有页并保留同刻合法点", async () => {
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({
            data: {
              is_bound: true,
              binding_id: 17,
              bound_at: "2026-07-24T18:30:00+08:00",
              device_id: 7,
              model: "M1",
              device_short_code: "0826",
              last_device_status: "online",
              last_battery_level: 82,
              last_communication_at: "2026-07-24T02:00:00Z",
              capabilities,
              last_sync_at: null,
              metrics: [],
            },
          });
        }
        if (url.includes("daily-summaries")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("measurements")) {
          const page = Number(config?.params?.page ?? 1);
          if (page === 1) {
            return Promise.resolve({
              data: {
                metric_type: "heart_rate",
                bucket: "raw",
                start: "2026-06-25",
                end: "2026-07-24",
                total: 3,
                page: 1,
                page_size: 2,
                next_page: 2,
                items: [
                  { measured_at: "2026-07-24T16:30:00Z", heart_rate: 70 },
                  { measured_at: "2026-07-24T16:30:00Z", heart_rate: 71 },
                ],
              },
            });
          }
          return Promise.resolve({
            data: {
              metric_type: "heart_rate",
              bucket: "raw",
              start: "2026-06-25",
              end: "2026-07-24",
              total: 3,
              page: 2,
              page_size: 2,
              next_page: null,
              items: [
                { measured_at: "2026-07-24T16:31:00Z", heart_rate: 72 },
              ],
            },
          });
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );

    renderTab();

    await waitFor(() => {
      expect(
        mockGet.mock.calls.filter(([url, config]) =>
          String(url).includes("measurements") &&
          (config as { params?: Record<string, unknown> }).params?.metric_type ===
            "heart_rate",
        ),
      ).toHaveLength(2);
    });
    const chartConfig = JSON.parse(
      screen.getAllByTestId("wearable-chart")[0].textContent ?? "{}",
    );
    expect(chartConfig.data).toEqual([
      { label: "07-25 00:30", timestamp: 1784910600000, value: 70 },
      { label: "07-25 00:30", timestamp: 1784910600000, value: 71 },
      { label: "07-25 00:31", timestamp: 1784910660000, value: 72 },
    ]);
  });

  it("分别展示趋势和日汇总的加载态", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
            bound_at: "2026-07-24T18:30:00+08:00",
            device_id: 7,
            model: "M1",
            device_short_code: "0826",
            last_device_status: "online",
            last_battery_level: 82,
            last_communication_at: "2026-07-24T02:00:00Z",
            capabilities,
            last_sync_at: null,
            metrics: [],
          },
        });
      }
      if (url.includes("measurements") || url.includes("daily-summaries")) {
        return new Promise(() => undefined);
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderTab();

    await screen.findByText("设备 0826");
    expect(screen.getByText("正在加载心率趋势")).toBeInTheDocument();
    expect(screen.getByText("正在加载血压趋势")).toBeInTheDocument();
    expect(screen.getByText("正在加载血氧趋势")).toBeInTheDocument();
    expect(screen.getByText("正在加载步数趋势")).toBeInTheDocument();
    expect(screen.getByText("正在加载日汇总")).toBeInTheDocument();
    expect(screen.queryByText("所选日期暂无趋势数据")).not.toBeInTheDocument();
  });

  it("保留后端字段错误并区分趋势与日汇总错误态", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
            bound_at: "2026-07-24T18:30:00+08:00",
            device_id: 7,
            model: "M1",
            device_short_code: "0826",
            last_device_status: "online",
            last_battery_level: 82,
            last_communication_at: "2026-07-24T02:00:00Z",
            capabilities,
            last_sync_at: null,
            metrics: [],
          },
        });
      }
      if (url.includes("measurements")) {
        return Promise.reject({
          response: { data: { end: ["趋势查询最多 31 个自然日。"] } },
        });
      }
      if (url.includes("daily-summaries")) {
        return Promise.reject({
          response: { data: { detail: "日汇总服务暂不可用。" } },
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderTab();

    expect(
      await screen.findAllByText("趋势查询最多 31 个自然日。"),
    ).toHaveLength(3);
    expect(await screen.findAllByText("日汇总服务暂不可用。")).toHaveLength(2);
    expect(screen.queryByText("暂无日汇总数据")).not.toBeInTheDocument();
  });

  it("单项趋势独立错误只显示一次，其他卡片仍显示各自数据", async () => {
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("daily-summaries")) {
          return Promise.resolve({
            data: { items: [{ record_date: "2026-07-24", steps: 7000 }] },
          });
        }
        if (config?.params?.metric_type === "heart_rate") {
          return Promise.reject({
            response: { data: { detail: "心率服务暂不可用。" } },
          });
        }
        const metricType = config?.params?.metric_type;
        return Promise.resolve({
          data: {
            metric_type: metricType,
            bucket: "raw",
            start: "2026-06-25",
            end: "2026-07-24",
            total: 0,
            page: 1,
            page_size: 500,
            next_page: null,
            items:
              metricType === "blood_pressure"
                ? [
                    {
                      measured_at: "2026-07-24T08:00:00Z",
                      systolic: 121,
                      diastolic: 81,
                    },
                  ]
                : [
                    {
                      measured_at: "2026-07-24T08:00:00Z",
                      blood_oxygen: 97,
                    },
                  ],
          },
        });
      },
    );
    renderTab();

    expect(await screen.findAllByText("心率服务暂不可用。")).toHaveLength(1);
    const chartConfigs = screen
      .getAllByTestId("wearable-chart")
      .map((node) => JSON.parse(node.textContent ?? "{}"));
    expect(chartConfigs.some((config) => config.data?.some((point: { value: number }) => point.value === 121))).toBe(true);
    expect(chartConfigs.some((config) => config.data?.some((point: { value: number }) => point.value === 97))).toBe(true);
    expect(chartConfigs.some((config) => config.data?.some((point: { value: number }) => point.value === 7000))).toBe(true);
  });

  it("日汇总成功时统一展示全部指标列且不展示状态列", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
            bound_at: "2026-07-24T18:30:00+08:00",
            device_id: 7,
            model: "M1",
            device_short_code: "0826",
            last_device_status: "online",
            last_battery_level: 82,
            last_communication_at: "2026-07-24T02:00:00Z",
            capabilities,
            last_sync_at: null,
            metrics: [],
          },
        });
      }
      if (url.includes("measurements")) {
        return Promise.resolve({
          data: {
            metric_type: "heart_rate",
            bucket: "raw",
            start: "2026-06-25",
            end: "2026-07-24",
            total: 1,
            page: 1,
            page_size: 500,
            next_page: null,
            items: [
              { measured_at: "2026-07-24T16:30:00Z", heart_rate: 72 },
            ],
          },
        });
      }
      if (url.includes("daily-summaries")) {
        return Promise.resolve({
          data: {
            items: [
              {
                record_date: "2026-07-23",
                heart_rate_avg: 72,
                heart_rate_min: null,
                heart_rate_max: 88,
                heart_rate_count: 12,
                systolic_avg: 120,
                diastolic_avg: 78,
                blood_pressure_count: 4,
                blood_oxygen_avg: 98,
                blood_oxygen_min: 96,
                blood_oxygen_max: 99,
                blood_oxygen_count: 8,
                steps: 6000,
              },
            ],
          },
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderTab();

    await screen.findByRole("columnheader", { name: "心率均值" });
    const headers = screen
      .getAllByRole("columnheader")
      .map((header) => header.textContent);
    expect(headers).toEqual([
      "日期",
      "心率均值",
      "收缩压均值",
      "舒张压均值",
      "血氧均值",
      "步数",
    ]);
    expect(screen.queryByRole("columnheader", { name: "同步状态" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "归属状态" })).not.toBeInTheDocument();
  });

  it("趋势和日汇总无数据时分别显示明确空态", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
            bound_at: "2026-07-24T18:30:00+08:00",
            device_id: 7,
            model: "M1",
            device_short_code: "0826",
            last_device_status: "online",
            last_battery_level: 82,
            last_communication_at: "2026-07-24T02:00:00Z",
            capabilities,
            last_sync_at: null,
            metrics: [],
          },
        });
      }
      if (url.includes("measurements")) {
        return Promise.resolve({
          data: {
            metric_type: "heart_rate",
            bucket: "raw",
            start: "2026-06-25",
            end: "2026-07-24",
            total: 0,
            page: 1,
            page_size: 500,
            next_page: null,
            items: [],
          },
        });
      }
      if (url.includes("daily-summaries")) {
        return Promise.resolve({ data: { items: [] } });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    renderTab();

    expect(await screen.findAllByText("所选日期暂无趋势数据")).toHaveLength(3);
    expect(screen.getByText("所选日期暂无步数趋势数据")).toBeInTheDocument();
    expect(await screen.findByText("暂无日汇总数据")).toBeInTheDocument();
  });

  it("通信测试后显示设备状态文字、电量和上海最近通信时间", async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        device_id: 7,
        model: "M1",
        online: false,
        battery_level: 37,
        last_communication_at: "2026-07-24T16:30:00Z",
        capabilities: { ring: false },
      },
    });
    renderTab();
    await screen.findByText("设备 0826");

    fireEvent.click(screen.getByRole("button", { name: /通信测试/ }));

    expect(await screen.findByText("设备离线")).toBeInTheDocument();
    expect(screen.getByText(/电量：37%/)).toBeInTheDocument();
    expect(screen.getByText(/最近通信：2026-07-25 00:30/)).toBeInTheDocument();
  });

  it("主动同步排队后刷新摘要、趋势和日汇总但不宣称数据已到", async () => {
    renderTab();
    await screen.findByText("设备 0826");
    const measurementCallCount = (metricType: string) =>
      mockGet.mock.calls.filter(
        ([url, config]) =>
          String(url).includes("measurements") &&
          (config as { params?: Record<string, unknown> }).params
            ?.metric_type === metricType,
      ).length;
    const callsBefore = {
      status: mockGet.mock.calls.filter(([url]) =>
        String(url).includes("sync-status"),
      ).length,
      measurements: {
        heart_rate: measurementCallCount("heart_rate"),
        blood_pressure: measurementCallCount("blood_pressure"),
        blood_oxygen: measurementCallCount("blood_oxygen"),
      },
      daily: mockGet.mock.calls.filter(([url]) =>
        String(url).includes("daily-summaries"),
      ).length,
    };

    fireEvent.click(screen.getByRole("button", { name: /主动同步/ }));

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(
        "/wearables/patients/201/sync/",
        {},
      ),
    );

    expect(
      await screen.findByText("健康数据同步已排队，尚未确认新数据到达。"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        mockGet.mock.calls.filter(([url]) =>
          String(url).includes("sync-status"),
        ).length,
      ).toBeGreaterThan(callsBefore.status);
      for (const metricType of [
        "heart_rate",
        "blood_pressure",
        "blood_oxygen",
      ] as const) {
        expect(measurementCallCount(metricType)).toBeGreaterThan(
          callsBefore.measurements[metricType],
        );
      }
      expect(
        mockGet.mock.calls.filter(([url]) =>
          String(url).includes("daily-summaries"),
        ).length,
      ).toBeGreaterThan(callsBefore.daily);
    });
  });

  it("不再展示设备配置草案或配置控件", async () => {
    renderTab();
    await screen.findByText("设备 0826");

    expect(screen.queryByText("设备配置")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("心率间隔（分钟）")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("血压间隔（分钟）")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("血氧间隔（分钟）")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("步数开关待下发值")).not.toBeInTheDocument();
  });

  it("通信测试进行中会禁用主动同步", async () => {
    mockPost.mockImplementation(
      () => new Promise(() => undefined),
    );
    renderTab();
    await screen.findByText("设备 0826");

    fireEvent.click(screen.getByRole("button", { name: /通信测试/ }));

    expect(screen.getByRole("button", { name: /主动同步/ })).toBeDisabled();
  });

  it("操作中解绑后重绑会清理旧锁并允许新设备操作", async () => {
    mockPost.mockImplementation(() => new Promise(() => undefined));
    const { queryClient } = renderTab();
    await screen.findByText("设备 0826");
    fireEvent.click(screen.getByRole("button", { name: /通信测试/ }));

    act(() => {
      queryClient.setQueryData(
        ["wearable-sync-status", 201],
        unboundSyncStatus(),
      );
    });
    await screen.findByText("请先在患者接入中绑定穿戴设备。");
    act(() => {
      queryClient.setQueryData(
        ["wearable-sync-status", 201],
        boundSyncStatus({
          binding_id: 18,
          device_id: 8,
          device_short_code: "9008",
        }),
      );
    });

    expect(await screen.findByText("设备 9008")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /通信测试/ })).toBeEnabled(),
    );
    await waitFor(() => {
      const historyCalls = mockGet.mock.calls.filter(
        ([url, config]) =>
          String(url).includes("daily-summaries") &&
          !(config as { params?: Record<string, unknown> }).params
            ?.project_patient,
      );
      expect(historyCalls.at(-1)?.[1]).toMatchObject({
        params: {
          start: "2026-07-30",
          end: "2026-08-03",
        },
      });
    });
  });

  it("同患者直接换绑会释放进行中的操作并隔离旧设备日汇总", async () => {
    let bindingGeneration = 17;
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({ data: boundSyncStatus() });
        }
        if (url.includes("measurements")) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes("daily-summaries")) {
          if (config?.params?.project_patient) {
            return Promise.resolve({ data: { items: [] } });
          }
          return Promise.resolve({
            data: {
              items: [
                {
                  record_date:
                    bindingGeneration === 17
                      ? "2026-07-30"
                      : "2026-08-03",
                  steps: bindingGeneration,
                },
              ],
            },
          });
        }
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );
    mockPost.mockImplementation(() => new Promise(() => undefined));
    const { queryClient } = renderTab();
    await screen.findByText("设备 0826");
    expect(await screen.findByText("2026-07-30")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /通信测试/ }));

    bindingGeneration = 19;
    act(() => {
      queryClient.setQueryData(
        ["wearable-sync-status", 201],
        boundSyncStatus({
          binding_id: 19,
          device_id: 9,
          device_short_code: "9009",
          last_battery_level: 55,
        }),
      );
    });

    expect(await screen.findByText("设备 9009")).toBeInTheDocument();
    expect(await screen.findByText("2026-08-03")).toBeInTheDocument();
    expect(screen.queryByText("2026-07-30")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /通信测试/ })).toBeEnabled(),
    );
  });

  it("已完成通信测试后换绑不展示旧设备状态或反馈", async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        device_id: 7,
        model: "M1",
        online: false,
        battery_level: 1,
        last_communication_at: "2026-07-24T16:30:00Z",
        capabilities: { ring: false },
      },
    });
    const { queryClient } = renderTab();
    await screen.findByText("设备 0826");
    fireEvent.click(screen.getByRole("button", { name: /通信测试/ }));
    await screen.findByText("通信测试完成，设备当前离线。");

    act(() => {
      queryClient.setQueryData(
        ["wearable-sync-status", 201],
        boundSyncStatus({
          binding_id: 20,
          device_id: 10,
          device_short_code: "9010",
          last_device_status: "online",
          last_battery_level: 99,
          last_communication_at: "2026-07-24T17:00:00Z",
        }),
      );
    });

    expect(await screen.findByText("设备 9010")).toBeInTheDocument();
    expect(
      screen.queryByText("通信测试完成，设备当前离线。"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("设备在线")).toBeInTheDocument();
    expect(screen.getByText("99%")).toBeInTheDocument();
  });

  it("绑定代际变化后忽略旧设备操作的迟到结果", async () => {
    let resolveStatus!: (value: {
      data: {
        device_id: number;
        model: string;
        online: boolean;
        battery_level: number | null;
        last_communication_at: string | null;
        capabilities: { ring: boolean };
      };
    }) => void;
    mockPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveStatus = resolve;
        }),
    );
    const { queryClient } = renderTab();
    await screen.findByText("设备 0826");
    fireEvent.click(screen.getByRole("button", { name: /通信测试/ }));

    act(() => {
      queryClient.setQueryData(["wearable-sync-status", 201], {
        is_bound: true,
        binding_id: 18,
        bound_at: "2026-07-24T18:30:00+08:00",
        device_id: 7,
        model: "M1",
        device_short_code: "0826",
        last_device_status: "online",
        last_battery_level: 82,
        last_communication_at: "2026-07-24T02:00:00Z",
        capabilities,
        last_sync_at: null,
        metrics: [],
      });
    });
    resolveStatus({
      data: {
        device_id: 7,
        model: "M1",
        online: false,
        battery_level: 1,
        last_communication_at: "2026-07-24T16:30:00Z",
        capabilities: { ring: false },
      },
    });

    await act(async () => undefined);
    expect(screen.queryByText("通信测试完成，设备当前离线。")).not.toBeInTheDocument();
    expect(screen.getByText("设备在线")).toBeInTheDocument();
    await waitFor(() => {
      const historyCalls = mockGet.mock.calls.filter(
        ([url, config]) =>
          String(url).includes("daily-summaries") &&
          !(config as { params?: Record<string, unknown> }).params
            ?.project_patient,
      );
      expect(historyCalls.at(-1)?.[1]).toMatchObject({
        params: {
          start: "2026-07-30",
          end: "2026-08-03",
        },
      });
    });
  });
});
