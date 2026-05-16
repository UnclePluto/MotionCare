import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TrainingTrackingDetailPage } from "./TrainingTrackingDetailPage";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

vi.mock("@ant-design/charts", () => ({
  DualAxes: (props: Record<string, unknown>) => (
    <pre data-testid="dual-axes-chart">{JSON.stringify(props, (_key, value) => (typeof value === "function" ? "[function]" : value))}</pre>
  ),
}));

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/training-tracking/patients/:patientId" element={<TrainingTrackingDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function RouteSwitcher() {
  const navigate = useNavigate();
  return (
    <>
      <button type="button" onClick={() => navigate("/training-tracking/patients/202")}>
        切换患者
      </button>
      <Routes>
        <Route path="/training-tracking/patients/:patientId" element={<TrainingTrackingDetailPage />} />
      </Routes>
    </>
  );
}

function renderWithRouteSwitcher(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <RouteSwitcher />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const trackingDetail = {
  patient: {
    id: 201,
    name: "训练患者甲",
    phone_masked: "138****0201",
  },
  project_patients: [
    {
      id: 9001,
      project: 1,
      project_name: "研究项目 A",
      project_status: "active",
      group: 10,
      group_name: "试验组",
      enrolled_at: "2026-05-01T09:00:00+08:00",
    },
    {
      id: 9002,
      project: 2,
      project_name: "研究项目 B",
      project_status: "active",
      group: 20,
      group_name: "对照组",
      enrolled_at: "2026-05-02T09:00:00+08:00",
    },
  ],
  selected_project_patient: {
    id: 9001,
    project: 1,
    project_name: "研究项目 A",
    project_status: "active",
    group: 10,
    group_name: "试验组",
    enrolled_at: "2026-05-01T09:00:00+08:00",
  },
  current_prescription: {
    id: 501,
    version: 3,
    status: "active",
    effective_at: "2026-05-03T10:00:00+08:00",
  },
  prescription_completion: [
    {
      prescription_action: 1001,
      action_name: "坐站转移训练",
      internal_type: "motion",
      action_type: "下肢训练",
      target_count: 16,
      completed_count: 12,
      completion_rate: 75,
      recent_record_at: "2026-05-14",
    },
  ],
  trend: {
    daily: [
      { date: "2026-05-13", completed_count: 1, duration_minutes: 20, game_average_score: 86 },
      { date: "2026-05-14", completed_count: 2, duration_minutes: 35, game_average_score: 92 },
    ],
    moving_average: [
      { date: "2026-05-13", completed_count_avg: 0.7, duration_minutes_avg: 18 },
      { date: "2026-05-14", completed_count_avg: 1.1, duration_minutes_avg: 23 },
    ],
    weekly: [
      {
        week_start: "2026-05-11",
        week_end: "2026-05-17",
        completed_count: 5,
        duration_minutes: 120,
        game_average_score: 88.5,
      },
    ],
  },
  game_summary: {
    average_score: 88.5,
    average_accuracy_rate: 91,
    total_error_count: 6,
    by_game: [
      {
        prescription_action: 1002,
        action_name: "认知卡片",
        record_count: 4,
        average_score: 88.5,
        average_accuracy_rate: 91,
        recent_record_at: "2026-05-14",
      },
    ],
  },
  recent_records: [
    {
      id: 7001,
      training_date: "2026-05-14",
      prescription: 501,
      prescription_version: 3,
      prescription_action: 1001,
      action_name: "坐站转移训练",
      internal_type: "game",
      action_type: "认知训练",
      status: "completed",
      actual_duration_minutes: 18,
      score: 92,
      game_accuracy_rate: 95,
      game_error_count: 1,
      game_difficulty: "中",
      game_ended_early: true,
      game_difficulty_adjust_reason: "今天状态不佳",
      game_upload_mode: "retry",
      game_retry_count: 2,
      game_total_retry_count: 12,
      note: "完成顺利",
    },
    {
      id: 7002,
      training_date: "2026-05-13",
      prescription: 501,
      prescription_version: 3,
      prescription_action: 1002,
      action_name: "旧游戏记录",
      internal_type: "game",
      action_type: "认知训练",
      status: "completed",
      actual_duration_minutes: 10,
      score: 80,
      game_accuracy_rate: 90,
      game_error_count: 2,
      game_difficulty: "易",
      game_ended_early: null,
      game_difficulty_adjust_reason: null,
      game_upload_mode: null,
      game_retry_count: null,
      game_total_retry_count: null,
      note: "旧版明细缺失",
    },
    {
      id: 7003,
      training_date: "2026-05-13",
      prescription: 501,
      prescription_version: 3,
      prescription_action: 1003,
      action_name: "坐站训练",
      internal_type: "motion",
      action_type: "下肢训练",
      status: "completed",
      actual_duration_minutes: 12,
      score: null,
      game_accuracy_rate: null,
      game_error_count: null,
      game_difficulty: null,
      game_ended_early: true,
      game_difficulty_adjust_reason: "不应展示",
      game_upload_mode: "retry",
      game_retry_count: 8,
      game_total_retry_count: 88,
      note: "非游戏记录",
    },
  ],
};

function chartProps() {
  return screen.getAllByTestId("dual-axes-chart").map((node) => JSON.parse(node.textContent ?? "{}") as { data?: unknown[] });
}

function trendChartData() {
  const chart = chartProps().find((props) => {
    const first = Array.isArray(props.data) ? (props.data[0] as Record<string, unknown> | undefined) : undefined;
    return typeof first?.label === "string";
  });
  return (chart?.data ?? []) as Array<Record<string, unknown>>;
}

describe("TrainingTrackingDetailPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url === "/training/tracking/patients/201/") {
        return Promise.resolve({ data: trackingDetail });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  afterEach(() => cleanup());

  it("展示项目下拉、当前处方、完成率、趋势图、游戏摘要和最近记录", async () => {
    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "切换项目" })).toBeInTheDocument();
    expect(screen.getAllByText("研究项目 A").length).toBeGreaterThan(0);
    expect(screen.getByText("试验组")).toBeInTheDocument();
    expect(screen.getByText("当前处方 v3")).toBeInTheDocument();
    expect(screen.getAllByText("坐站转移训练").length).toBeGreaterThan(0);
    expect(screen.getAllByText("16").length).toBeGreaterThan(0);
    expect(screen.getAllByText("75%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2026-05-14").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("dual-axes-chart").length).toBeGreaterThan(0);
    expect(screen.getAllByText("平均得分").length).toBeGreaterThan(0);
    expect(screen.getAllByText("88.5").length).toBeGreaterThan(0);
    expect(screen.getAllByText("平均正确率").length).toBeGreaterThan(0);
    expect(screen.getAllByText("91%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("总错误次数").length).toBeGreaterThan(0);
    expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    expect(screen.getAllByText("认知卡片").length).toBeGreaterThan(0);
    expect(screen.getAllByText("4").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2026-05-14").length).toBeGreaterThan(0);
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(screen.getByText("中")).toBeInTheDocument();
    expect(screen.getByText("提前结束")).toBeInTheDocument();
    expect(screen.getByText("补传")).toBeInTheDocument();
    expect(screen.getByText("12 次")).toBeInTheDocument();
    expect(screen.getByText("今天状态不佳")).toBeInTheDocument();
    expect(screen.getByText("完成顺利")).toBeInTheDocument();
    expect(screen.queryByText("到时完成")).not.toBeInTheDocument();
    expect(screen.queryByText("88 次")).not.toBeInTheDocument();
    expect(screen.queryByText("不应展示")).not.toBeInTheDocument();
  });

  it("初次请求不带 project_patient，并按 range 切换趋势图数据", async () => {
    renderAt("/training-tracking/patients/201");

    await screen.findByText("训练患者甲");
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/tracking/patients/201/", { params: { range: "30d" } });
    });
    await waitFor(() => expect(screen.getAllByTestId("dual-axes-chart").length).toBeGreaterThan(0));
    expect(trendChartData()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "05-14", completed_count: 2, moving_average: 1.1 }),
      ]),
    );

    fireEvent.click(screen.getByText("近 7 天"));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/tracking/patients/201/", { params: { range: "7d" } });
    });
    await waitFor(() => expect(screen.getAllByTestId("dual-axes-chart").length).toBeGreaterThan(0));
    expect(trendChartData()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "05-14", completed_count: 2, moving_average: 1.1 }),
      ]),
    );

    fireEvent.click(screen.getByText("按周"));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/tracking/patients/201/", { params: { range: "weekly" } });
    });
    await waitFor(() => expect(screen.getAllByTestId("dual-axes-chart").length).toBeGreaterThan(0));
    expect(trendChartData()).toEqual([
      expect.objectContaining({
        label: "05-11 至 05-17",
        completed_count: 5,
        moving_average: 5,
      }),
    ]);
  });

  it("切换日期范围重新请求时保留详情页内容", async () => {
    let resolveRangeRequest: ((value: { data: typeof trackingDetail }) => void) | undefined;
    mockGet.mockImplementation((_url: string, config?: unknown) => {
      const params = (config as { params?: Record<string, unknown> } | undefined)?.params;
      if (params?.range === "7d") {
        return new Promise((resolve) => {
          resolveRangeRequest = resolve;
        });
      }
      return Promise.resolve({ data: trackingDetail });
    });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();
    fireEvent.click(screen.getByText("近 7 天"));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/tracking/patients/201/", { params: { range: "7d" } });
    });
    expect(screen.getByText("训练患者甲")).toBeInTheDocument();
    expect(screen.getByText("处方完成情况")).toBeInTheDocument();

    resolveRangeRequest?.({ data: trackingDetail });
  });

  it("切换项目后用 project_patient 重新请求", async () => {
    renderAt("/training-tracking/patients/201");

    await screen.findByText("训练患者甲");
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "切换项目" }));
    const option = await screen.findByTitle("研究项目 B");
    fireEvent.click(option);

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/training/tracking/patients/201/",
        expect.objectContaining({ params: expect.objectContaining({ project_patient: 9002 }) }),
      );
    });
  });

  it("切换患者路由时不沿用上一个患者的项目选择", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === "/training/tracking/patients/201/" || url === "/training/tracking/patients/202/") {
        return Promise.resolve({ data: trackingDetail });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    renderWithRouteSwitcher("/training-tracking/patients/201");

    await screen.findByText("训练患者甲");
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "切换项目" }));
    fireEvent.click(await screen.findByTitle("研究项目 B"));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/training/tracking/patients/201/",
        expect.objectContaining({ params: expect.objectContaining({ project_patient: 9002 }) }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "切换患者" }));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/tracking/patients/202/", { params: { range: "30d" } });
    });
    expect(
      mockGet.mock.calls.some(([url, config]) => {
        const params = (config as { params?: Record<string, unknown> } | undefined)?.params;
        return url === "/training/tracking/patients/202/" && params?.project_patient === 9002;
      }),
    ).toBe(false);
  });

  it("无效 patientId 不请求接口", () => {
    renderAt("/training-tracking/patients/not-a-number");

    expect(screen.getByText("无效的患者 ID")).toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("无可访问项目时展示空状态", async () => {
    mockGet.mockResolvedValue({ data: { ...trackingDetail, project_patients: [], selected_project_patient: null } });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("暂无可追踪项目")).toBeInTheDocument();
  });

  it("请求失败时展示后端错误而不是空态", async () => {
    mockGet.mockRejectedValueOnce({ response: { data: { detail: "患者不存在或无权访问" } } });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("患者不存在或无权访问")).toBeInTheDocument();
    expect(screen.queryByText("暂无训练追踪数据")).not.toBeInTheDocument();
  });
});
