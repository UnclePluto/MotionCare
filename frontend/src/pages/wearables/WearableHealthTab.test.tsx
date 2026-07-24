import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WearableHealthTab } from "./WearableHealthTab";

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));

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

const capabilities = {
  ring: false,
  measure_heart_rate: true,
  measure_blood_pressure: true,
  measure_blood_oxygen: true,
  configure_heart_rate_interval: false,
  configure_blood_pressure_interval: false,
  configure_blood_oxygen_interval: false,
  configure_step_switch: false,
};

function renderTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <WearableHealthTab patientId={201} projectPatientId={9001} />
    </QueryClientProvider>,
  );
  return { ...result, queryClient };
}

describe("WearableHealthTab", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
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

  afterEach(() => cleanup());

  it("加载绑定摘要、健康筛选、趋势和日汇总，且不自动发起通信测试", async () => {
    renderTab();

    expect(await screen.findByText("设备 0826")).toBeInTheDocument();
    expect(screen.getByTitle("心率")).toBeInTheDocument();
    expect(screen.getByTitle("原始")).toBeInTheDocument();
    expect(screen.getByText("日汇总")).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(
      "/wearables/patients/201/measurements/",
      expect.objectContaining({ params: expect.objectContaining({ project_patient: 9001, metric_type: "heart_rate", bucket: "raw" }) }),
    ));
  });

  it("步数只展示日总量并隐藏日内间隔与主动测量", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
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
        return Promise.resolve({
          data: {
            items: [
              {
                record_date: "2026-07-22",
                steps: 5000,
                steps_attribution_status: "attributed",
                steps_sync_status: "succeeded",
              },
              {
                record_date: "2026-07-23",
                steps: 6000,
                steps_attribution_status: "ambiguous",
                steps_sync_status: "failed",
              },
            ],
          },
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    renderTab();
    await screen.findByText("设备 0826");
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "健康指标" }));
    fireEvent.click(await screen.findByTitle("步数"));

    expect(screen.queryByLabelText("图表间隔")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "主动测量" })).not.toBeInTheDocument();
    expect(await screen.findByText("5000")).toBeInTheDocument();
    expect(await screen.findByText("6000")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "归属状态" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "同步状态" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "心率均值" })).not.toBeInTheDocument();
    const chartConfigs = screen
      .getAllByTestId("wearable-chart")
      .map((node) => JSON.parse(node.textContent ?? "{}"));
    expect(
      chartConfigs.some(
        (config) =>
          JSON.stringify(config.data) ===
          JSON.stringify([
            { label: "07-22", value: 5000 },
            { label: "07-23", value: 6000 },
          ]),
      ),
    ).toBe(true);
  });

  it("未绑定时显示绑定引导且不显示主动测量", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) return Promise.resolve({ data: { is_bound: false, metrics: [] } });
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    renderTab();

    expect(await screen.findByText("请先在患者接入中绑定穿戴设备。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "主动测量" })).not.toBeInTheDocument();
  });

  it("未验证型号会禁用主动测量并说明原因", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
            device_id: 7,
            model: "UNKNOWN",
            device_short_code: "0826",
            last_device_status: null,
            last_battery_level: null,
            last_communication_at: null,
            capabilities: { ...capabilities, measure_heart_rate: false },
            last_sync_at: null,
            metrics: [],
          },
        });
      }
      if (url.includes("measurements") || url.includes("daily-summaries")) return Promise.resolve({ data: { items: [] } });
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    renderTab();

    expect((await screen.findAllByText("该型号能力尚未验证")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "主动测量" })).toBeDisabled();
  });

  it("raw 趋势跟随 next_page 拉齐所有页并保留同刻合法点", async () => {
    mockGet.mockImplementation(
      (url: string, config?: { params?: Record<string, unknown> }) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({
            data: {
              is_bound: true,
              binding_id: 17,
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
        mockGet.mock.calls.filter(([url]) =>
          String(url).includes("measurements"),
        ),
      ).toHaveLength(2);
    });
    const chartConfig = JSON.parse(
      (await screen.findByTestId("wearable-chart")).textContent ?? "{}",
    );
    expect(chartConfig.data).toEqual([
      { label: "07-25 00:30", value: 70 },
      { label: "07-25 00:30", value: 71 },
      { label: "07-25 00:31", value: 72 },
    ]);
  });

  it("聚合趋势只请求单页且不携带 raw 分页参数", async () => {
    renderTab();
    await screen.findByText("设备 0826");

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "图表间隔" }));
    fireEvent.click(await screen.findByTitle("15 分钟"));

    await waitFor(() => {
      const bucketCalls = mockGet.mock.calls.filter(([, config]) => {
        const params = (config as { params?: Record<string, unknown> } | undefined)
          ?.params;
        return params?.bucket === "15m";
      });
      expect(bucketCalls).toHaveLength(1);
      const params = (
        bucketCalls[0][1] as { params?: Record<string, unknown> }
      ).params;
      expect(params).not.toHaveProperty("page");
      expect(params).not.toHaveProperty("page_size");
    });
  });

  it("切换指标时取消旧指标的分页请求", async () => {
    let heartRateSignal: AbortSignal | undefined;
    mockGet.mockImplementation(
      (
        url: string,
        config?: { params?: Record<string, unknown>; signal?: AbortSignal },
      ) => {
        if (url.includes("sync-status")) {
          return Promise.resolve({
            data: {
              is_bound: true,
              binding_id: 17,
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
        if (
          url.includes("measurements") &&
          config?.params?.metric_type === "heart_rate"
        ) {
          heartRateSignal = config.signal;
          return new Promise(() => undefined);
        }
        if (url.includes("measurements")) {
          return Promise.resolve({
            data: {
              metric_type: "blood_oxygen",
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
        return Promise.reject(new Error(`unmocked GET ${url}`));
      },
    );

    renderTab();
    await screen.findByText("设备 0826");
    await waitFor(() => expect(heartRateSignal).toBeDefined());

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "健康指标" }));
    fireEvent.click(await screen.findByTitle("血氧"));

    await waitFor(() => expect(heartRateSignal?.aborted).toBe(true));
  });

  it("分别展示趋势和日汇总的加载态", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
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
    expect(screen.getByText("正在加载健康趋势")).toBeInTheDocument();
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
      await screen.findByText("趋势查询最多 31 个自然日。"),
    ).toBeInTheDocument();
    expect(await screen.findByText("日汇总服务暂不可用。")).toBeInTheDocument();
    expect(screen.queryByText("暂无日汇总数据")).not.toBeInTheDocument();
  });

  it("日汇总成功时只展示当前指标相关字段和数据完整性", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
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
                record_date: "2026-07-25",
                heart_rate_avg: 72,
                heart_rate_min: 60,
                heart_rate_max: 88,
                heart_rate_count: 12,
                heart_rate_sync_status: "succeeded",
                systolic_avg: 120,
                diastolic_avg: 80,
                blood_oxygen_avg: 98,
                steps: 6000,
              },
            ],
          },
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderTab();

    expect(
      await screen.findByRole("columnheader", { name: "心率均值" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "最低心率" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "最高心率" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "测量次数" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "同步状态" })).toBeInTheDocument();
    expect(screen.getByText("同步成功")).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "血压均值" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "血氧均值" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "步数" })).not.toBeInTheDocument();
  });

  it("趋势和日汇总无数据时分别显示明确空态", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
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

    expect(await screen.findByText("所选日期暂无趋势数据")).toBeInTheDocument();
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

  it.each([
    ["offline", "设备离线"],
    ["timeout", "主动测量超时"],
    ["failed", "主动测量失败"],
  ])("主动测量 %s 不显示成功反馈", async (status, expected) => {
    mockPost.mockResolvedValueOnce({
      data: {
        id: 91,
        command_type: "measure_heart_rate",
        status,
        provider_code: "1802",
        completed_at: "2026-07-24T16:30:00Z",
      },
    });
    renderTab();
    await screen.findByText("设备 0826");

    fireEvent.click(screen.getByRole("button", { name: "主动测量" }));

    expect(await screen.findByText(expected)).toBeInTheDocument();
    expect(screen.queryByText("主动测量请求已提交。")).not.toBeInTheDocument();
  });

  it("主动同步排队后刷新摘要、趋势和日汇总但不宣称数据已到", async () => {
    renderTab();
    await screen.findByText("设备 0826");
    const callsBefore = {
      status: mockGet.mock.calls.filter(([url]) =>
        String(url).includes("sync-status"),
      ).length,
      measurements: mockGet.mock.calls.filter(([url]) =>
        String(url).includes("measurements"),
      ).length,
      daily: mockGet.mock.calls.filter(([url]) =>
        String(url).includes("daily-summaries"),
      ).length,
    };

    fireEvent.click(screen.getByRole("button", { name: /主动同步/ }));

    expect(
      await screen.findByText("健康数据同步已排队，尚未确认新数据到达。"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        mockGet.mock.calls.filter(([url]) =>
          String(url).includes("sync-status"),
        ).length,
      ).toBeGreaterThan(callsBefore.status);
      expect(
        mockGet.mock.calls.filter(([url]) =>
          String(url).includes("measurements"),
        ).length,
      ).toBeGreaterThan(callsBefore.measurements);
      expect(
        mockGet.mock.calls.filter(([url]) =>
          String(url).includes("daily-summaries"),
        ).length,
      ).toBeGreaterThan(callsBefore.daily);
    });
  });

  it("按 capability 提供四项设备配置并发送严格 payload", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
            device_id: 7,
            model: "M1",
            device_short_code: "0826",
            last_device_status: "online",
            last_battery_level: 82,
            last_communication_at: "2026-07-24T02:00:00Z",
            capabilities: {
              ...capabilities,
              configure_heart_rate_interval: true,
              configure_blood_pressure_interval: true,
              configure_blood_oxygen_interval: true,
              configure_step_switch: true,
            },
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
    mockPost.mockResolvedValue({
      data: {
        id: 92,
        command_type: "configure",
        status: "succeeded",
        provider_code: "0",
        completed_at: "2026-07-24T16:30:00Z",
      },
    });
    renderTab();

    expect(await screen.findByText("设备配置")).toBeInTheDocument();
    expect(
      screen.getByText("以下为待下发值，不代表已读取设备当前配置。"),
    ).toBeInTheDocument();
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "心率间隔（分钟）" }),
      { target: { value: "15" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "应用心率间隔" }));
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(
        "/wearables/patients/201/configure/",
        { setting: "heart_rate_interval", interval_minutes: 15 },
      ),
    );

    fireEvent.mouseDown(
      screen.getByRole("combobox", { name: "步数开关待下发值" }),
    );
    fireEvent.click(await screen.findByTitle("关闭"));
    fireEvent.click(screen.getByRole("button", { name: "应用步数开关" }));
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(
        "/wearables/patients/201/configure/",
        { setting: "step_switch", enabled: false },
      ),
    );
  });

  it("设备配置失败状态展示失败且不显示成功反馈", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
            device_id: 7,
            model: "M1",
            device_short_code: "0826",
            last_device_status: "online",
            last_battery_level: 82,
            last_communication_at: "2026-07-24T02:00:00Z",
            capabilities: {
              ...capabilities,
              configure_heart_rate_interval: true,
            },
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
    mockPost.mockResolvedValueOnce({
      data: {
        id: 93,
        command_type: "configure",
        status: "failed",
        provider_code: "1802",
        completed_at: "2026-07-24T16:30:00Z",
      },
    });
    renderTab();
    await screen.findByText("设备配置");

    fireEvent.click(screen.getByRole("button", { name: "应用心率间隔" }));

    expect(await screen.findByText("心率间隔配置失败")).toBeInTheDocument();
    expect(screen.queryByText("心率间隔配置已完成。")).not.toBeInTheDocument();
  });

  it("未验证配置 capability 时逐项禁用并显示原因", async () => {
    renderTab();

    await screen.findByText("设备配置");
    expect(screen.getByRole("button", { name: "应用心率间隔" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "应用血压间隔" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "应用血氧间隔" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "应用步数开关" })).toBeDisabled();
    expect(screen.getAllByText("该型号能力尚未验证")).toHaveLength(4);
  });

  it("任一设备操作进行中会互斥禁用其他操作", async () => {
    mockPost.mockImplementation(
      () => new Promise(() => undefined),
    );
    renderTab();
    await screen.findByText("设备 0826");

    fireEvent.click(screen.getByRole("button", { name: /通信测试/ }));

    expect(screen.getByRole("button", { name: "主动测量" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /主动同步/ })).toBeDisabled();
  });

  it("主动测量排队后短轮询到新点并刷新反馈", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let measurementCalls = 0;
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
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
        measurementCalls += 1;
        const items =
          measurementCalls >= 3
            ? [{ measured_at: "2026-07-24T16:31:00Z", heart_rate: 72 }]
            : [];
        return Promise.resolve({
          data: {
            metric_type: "heart_rate",
            bucket: "raw",
            start: "2026-06-25",
            end: "2026-07-24",
            total: items.length,
            page: 1,
            page_size: 500,
            next_page: null,
            items,
          },
        });
      }
      if (url.includes("daily-summaries")) {
        return Promise.resolve({ data: { items: [] } });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    mockPost.mockResolvedValue({
      data: {
        id: 93,
        command_type: "measure_heart_rate",
        status: "queued",
        provider_code: "1803",
        completed_at: null,
      },
    });
    try {
      renderTab();
      await screen.findByText("设备 0826");
      await waitFor(() => expect(measurementCalls).toBe(1));

      fireEvent.click(screen.getByRole("button", { name: "主动测量" }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2_000);
      });

      expect(
        await screen.findByText("已获取新的心率测量点。"),
      ).toBeInTheDocument();
      expect(measurementCalls).toBe(3);
      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: /主动测量/ }),
        ).toBeEnabled(),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("主动测量最多轮询三次后停止并显示等待超时", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let measurementCalls = 0;
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            binding_id: 17,
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
        measurementCalls += 1;
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
    mockPost.mockResolvedValue({
      data: {
        id: 94,
        command_type: "measure_heart_rate",
        status: "queued",
        provider_code: "1803",
        completed_at: null,
      },
    });
    try {
      renderTab();
      await screen.findByText("设备 0826");
      await waitFor(() => expect(measurementCalls).toBe(1));
      fireEvent.click(screen.getByRole("button", { name: "主动测量" }));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3_000);
      });
      expect(
        await screen.findByText("等待窗口内尚未发现新测量点，请稍后查看。"),
      ).toBeInTheDocument();
      expect(measurementCalls).toBe(4);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
      expect(measurementCalls).toBe(4);
    } finally {
      vi.useRealTimers();
    }
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
  });
});
