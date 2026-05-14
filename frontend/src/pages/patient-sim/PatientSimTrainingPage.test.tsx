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

const twoActionPrescription = {
  ...prescription,
  actions: [
    prescription.actions[0],
    {
      ...prescription.actions[0],
      id: 12,
      action_name_snapshot: "弹力带划船",
      action_instruction_snapshot: "保持躯干稳定，向后拉动弹力带。",
      duration_minutes: 20,
      sets: 3,
      repetitions: 12,
      sort_order: 1,
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

  it("shows backend detail when training record submission fails", async () => {
    mockPost.mockRejectedValue({ response: { data: { detail: "处方动作不属于当前处方" } } });

    renderAt("/patient-sim/project-patients/9001");

    expect(await screen.findByText("当前处方 v1")).toBeInTheDocument();
    fireEvent.click(screen.getByText("坐站转移训练"));
    fireEvent.click(screen.getByRole("button", { name: "提交训练记录" }));

    expect(await screen.findByText("处方动作不属于当前处方")).toBeInTheDocument();
  });

  it("shows default message when training record submission fails without detail", async () => {
    mockPost.mockRejectedValue(new Error("network error"));

    renderAt("/patient-sim/project-patients/9001");

    expect(await screen.findByText("当前处方 v1")).toBeInTheDocument();
    fireEvent.click(screen.getByText("坐站转移训练"));
    fireEvent.click(screen.getByRole("button", { name: "提交训练记录" }));

    expect(await screen.findByText("训练记录提交失败")).toBeInTheDocument();
  });

  it("resets duration and note synchronously when switching actions before submit", async () => {
    mockGet.mockResolvedValue({ data: twoActionPrescription });

    renderAt("/patient-sim/project-patients/9001");

    expect(await screen.findByText("当前处方 v1")).toBeInTheDocument();
    fireEvent.click(screen.getByText("坐站转移训练"));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "9" } });
    fireEvent.change(screen.getByPlaceholderText("可记录本次跟练情况"), { target: { value: "第一项备注" } });

    fireEvent.click(screen.getByText("弹力带划船"));
    fireEvent.click(screen.getByRole("button", { name: "提交训练记录" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/patient-sim/project-patients/9001/training-records/",
        expect.objectContaining({
          prescription_action: 12,
          actual_duration_minutes: 20,
          note: "",
        }),
      );
    });
  });

  it("does not request current prescription with invalid project patient id", async () => {
    renderAt("/patient-sim/project-patients/not-a-number");

    expect(screen.getByText("无效的项目患者 ID")).toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("shows empty action state when current prescription has no actions", async () => {
    mockGet.mockResolvedValue({ data: { ...prescription, actions: [] } });

    renderAt("/patient-sim/project-patients/9001");

    expect(await screen.findByText("当前处方暂无动作")).toBeInTheDocument();
  });
});
