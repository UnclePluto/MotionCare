import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PatientSimTrainingPage } from "./PatientSimTrainingPage";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/patient-sim/project-patients/:projectPatientId" element={<PatientSimTrainingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const prescription = {
  id: 1,
  project_patient: 9001,
  version: 1,
  opened_by: 1,
  opened_by_name: "测试医生",
  opened_at: "2026-05-14T10:00:00+08:00",
  effective_at: "2026-05-14T10:00:00+08:00",
  status: "active",
  note: "",
  actions: [
    {
      id: 11,
      prescription: 1,
      action_library_item: 101,
      action_name_snapshot: "坐站转移训练",
      training_type_snapshot: "运动训练",
      internal_type_snapshot: "motion",
      action_type_snapshot: "平衡训练",
      action_instruction_snapshot: "坐稳后起身，再缓慢坐下。",
      video_url_snapshot: "",
      has_ai_supervision_snapshot: true,
      weekly_frequency: "2 次/周",
      duration_minutes: 15,
      sets: 2,
      repetitions: 10,
      difficulty: "中",
      notes: "",
      sort_order: 0,
    },
  ],
};

describe("PatientSimTrainingPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockResolvedValue({ data: prescription });
    mockPost.mockResolvedValue({ data: { id: 99 } });
  });

  afterEach(() => cleanup());

  it("shows only current prescription actions and submits one training record", async () => {
    renderAt("/patient-sim/project-patients/9001");

    expect(await screen.findByText("当前处方 v1")).toBeInTheDocument();
    fireEvent.click(screen.getByText("坐站转移训练"));
    expect(screen.getByText("坐稳后起身，再缓慢坐下。")).toBeInTheDocument();
    expect(screen.getByText("视频待配置")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "提交训练记录" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/patient-sim/project-patients/9001/training-records/",
        expect.objectContaining({
          prescription_action: 11,
          status: "completed",
        }),
      );
    });
  });

  it("shows empty state without active prescription", async () => {
    mockGet.mockResolvedValue({ data: null });

    renderAt("/patient-sim/project-patients/9001");

    expect(await screen.findByText("暂无可执行处方")).toBeInTheDocument();
  });
});
