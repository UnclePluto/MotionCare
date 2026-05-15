import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TrainingTrackingDetailPage } from "./TrainingTrackingDetailPage";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

vi.mock("@ant-design/charts", () => ({
  DualAxes: () => <div data-testid="dual-axes-chart">趋势图</div>,
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

const trackingDetail = {
  patient: {
    id: 201,
    name: "训练患者甲",
    phone: "13800000201",
  },
  project_options: [
    { project_patient_id: 9001, project_id: 1, project_name: "研究项目 A", group_name: "试验组" },
    { project_patient_id: 9002, project_id: 2, project_name: "研究项目 B", group_name: "对照组" },
  ],
  current_project_patient: {
    id: 9001,
    project_id: 1,
    project_name: "研究项目 A",
    group_name: "试验组",
  },
  current_prescription: {
    id: 501,
    version: 3,
    status: "active",
  },
  prescription_completion: [
    {
      action_id: 1001,
      action_name: "坐站转移训练",
      prescribed_count: 16,
      completed_count: 12,
      completion_rate: 75,
    },
  ],
  trends: {
    daily_30d: [
      { date: "2026-05-13", completed_count: 1, moving_average: 0.7 },
      { date: "2026-05-14", completed_count: 2, moving_average: 1.1 },
    ],
    daily_7d: [{ date: "2026-05-14", completed_count: 2, moving_average: 1.1 }],
    weekly: [{ week_start: "2026-W20", completed_count: 5, moving_average: 5 }],
  },
  game_summary: {
    average_score: 88.5,
    average_accuracy: 91,
    total_errors: 6,
    by_game: [
      {
        game_name: "认知卡片",
        completed_count: 4,
        average_score: 88.5,
        average_accuracy: 91,
        total_errors: 6,
      },
    ],
  },
  recent_records: [
    {
      id: 7001,
      trained_at: "2026-05-14T10:30:00+08:00",
      action_name: "坐站转移训练",
      game_name: "认知卡片",
      status: "completed",
      score: 92,
      accuracy: 95,
      error_count: 1,
    },
  ],
};

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
    expect(screen.getAllByText("75%").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("dual-axes-chart").length).toBeGreaterThan(0);
    expect(screen.getAllByText("平均得分").length).toBeGreaterThan(0);
    expect(screen.getAllByText("88.5").length).toBeGreaterThan(0);
    expect(screen.getAllByText("平均正确率").length).toBeGreaterThan(0);
    expect(screen.getAllByText("91%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("总错误次数").length).toBeGreaterThan(0);
    expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    expect(screen.getAllByText("认知卡片").length).toBeGreaterThan(0);
    expect(screen.getByText("2026-05-14 10:30")).toBeInTheDocument();
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

  it("无效 patientId 不请求接口", () => {
    renderAt("/training-tracking/patients/not-a-number");

    expect(screen.getByText("无效的患者 ID")).toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("无可访问项目时展示空状态", async () => {
    mockGet.mockResolvedValue({ data: { ...trackingDetail, project_options: [], current_project_patient: null } });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("暂无可追踪项目")).toBeInTheDocument();
  });
});
