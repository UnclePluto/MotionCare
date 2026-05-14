import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PrescriptionPanel } from "./PrescriptionPanel";

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

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PrescriptionPanel projectPatientId={9001} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const action = {
  id: 101,
  source_key: "motion-aerobic-high-knee",
  name: "椰林步道模拟（原地高抬腿+摆臂）",
  training_type: "运动训练",
  internal_type: "motion",
  action_type: "有氧训练",
  instruction_text: "动作说明",
  suggested_frequency: "3 次/周",
  suggested_duration_minutes: 20,
  suggested_sets: null,
  suggested_repetitions: null,
  default_difficulty: "低",
  video_url: "https://example.com/video.mp4",
  has_ai_supervision: true,
  is_active: true,
  parameter_mode: "duration",
};

const countAction = {
  id: 102,
  source_key: "motion-resistance-row",
  name: "坐姿划船",
  training_type: "运动训练",
  internal_type: "motion",
  action_type: "抗阻训练",
  instruction_text: "弹力带坐姿背部训练",
  suggested_frequency: "2 次/周",
  suggested_duration_minutes: 10,
  suggested_sets: 3,
  suggested_repetitions: 12,
  default_difficulty: "中",
  video_url: "",
  has_ai_supervision: false,
  is_active: true,
  parameter_mode: "count",
};

const countActionWithoutSuggestedCounts = {
  id: 103,
  source_key: "motion-resistance-leg-kickback",
  name: "腿部后踢",
  training_type: "运动训练",
  internal_type: "motion",
  action_type: "抗阻训练",
  instruction_text: "弹力带下肢后踢",
  suggested_frequency: "2 次/周",
  suggested_duration_minutes: 10,
  suggested_sets: null,
  suggested_repetitions: null,
  default_difficulty: "中",
  video_url: "",
  has_ai_supervision: false,
  is_active: true,
  parameter_mode: "count",
};

const activePrescription = {
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
      action_name_snapshot: "椰林步道模拟（原地高抬腿+摆臂）",
      training_type_snapshot: "运动训练",
      internal_type_snapshot: "motion",
      action_type_snapshot: "有氧训练",
      action_instruction_snapshot: "动作说明",
      video_url_snapshot: "https://example.com/video.mp4",
      has_ai_supervision_snapshot: true,
      weekly_frequency: "3 次/周",
      duration_minutes: 20,
      sets: null,
      repetitions: null,
      difficulty: "低",
      notes: "",
      sort_order: 0,
    },
  ],
};

describe("PrescriptionPanel", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config ? (config as { params?: Record<string, unknown> }).params : {};
      if (url === "/prescriptions/current/") return Promise.resolve({ data: null });
      if (url === "/prescriptions/") return Promise.resolve({ data: [] });
      if (url === "/prescriptions/actions/" && params?.training_type === "运动训练") {
        return Promise.resolve({ data: [action, countAction, countActionWithoutSuggestedCounts] });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    mockPost.mockResolvedValue({
      data: {
        id: 1,
        project_patient: 9001,
        version: 1,
        opened_by: 1,
        opened_by_name: "测试医生",
        opened_at: "2026-05-14T10:00:00+08:00",
        effective_at: "2026-05-14T10:00:00+08:00",
        status: "active",
        note: "",
        actions: [],
      },
    });
  });

  afterEach(() => cleanup());

  it("shows fixed action library as read-only", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("tab", { name: "固定动作库" }));
    expect(await screen.findByText("椰林步道模拟（原地高抬腿+摆臂）")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新增动作" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除" })).not.toBeInTheDocument();
  });

  it("creates an active prescription from selected action", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "开具处方" }));
    fireEvent.click(await screen.findByLabelText("椰林步道模拟（原地高抬腿+摆臂）"));
    fireEvent.click(screen.getByRole("button", { name: "保存并立即生效" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/studies/project-patients/9001/prescriptions/activate-now/",
        expect.objectContaining({
          expected_active_version: null,
          actions: [
            expect.objectContaining({
              action_library_item: 101,
              weekly_frequency: "3 次/周",
              duration_minutes: 20,
            }),
          ],
        }),
      );
    });
  });

  it("creates count-mode prescription action without duration minutes", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "开具处方" }));
    fireEvent.click(await screen.findByLabelText("坐姿划船"));
    fireEvent.click(screen.getByRole("button", { name: "保存并立即生效" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/studies/project-patients/9001/prescriptions/activate-now/",
        expect.objectContaining({
          expected_active_version: null,
          actions: [
            expect.objectContaining({
              action_library_item: 102,
              duration_minutes: null,
              sets: 3,
              repetitions: 12,
            }),
          ],
        }),
      );
    });
  });

  it("uses executable fallback parameters for count-mode action without suggested counts", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "开具处方" }));
    fireEvent.click(await screen.findByLabelText("腿部后踢"));
    await waitFor(() => {
      expect(screen.getAllByRole("cell", { name: "1" })).toHaveLength(2);
    });
    fireEvent.click(screen.getByRole("button", { name: "保存并立即生效" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/studies/project-patients/9001/prescriptions/activate-now/",
        expect.objectContaining({
          expected_active_version: null,
          actions: [
            expect.objectContaining({
              action_library_item: 103,
              duration_minutes: null,
              sets: 1,
              repetitions: 1,
            }),
          ],
        }),
      );
    });
  });

  it("does not submit when selected prescription actions cannot be mapped to action library", async () => {
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config ? (config as { params?: Record<string, unknown> }).params : {};
      if (url === "/prescriptions/current/") return Promise.resolve({ data: activePrescription });
      if (url === "/prescriptions/") return Promise.resolve({ data: [activePrescription] });
      if (url === "/prescriptions/actions/" && params?.training_type === "运动训练") {
        return Promise.resolve({ data: [] });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "调整处方" }));
    fireEvent.click(screen.getByRole("button", { name: "保存并立即生效" }));

    await waitFor(() => {
      expect(mockPost).not.toHaveBeenCalled();
      expect(screen.getByText("动作库未加载完成，请刷新后重试")).toBeInTheDocument();
    });
  });

  it("terminates active prescription after confirmation", async () => {
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config ? (config as { params?: Record<string, unknown> }).params : {};
      if (url === "/prescriptions/current/") return Promise.resolve({ data: activePrescription });
      if (url === "/prescriptions/") return Promise.resolve({ data: [activePrescription] });
      if (url === "/prescriptions/actions/" && params?.training_type === "运动训练") {
        return Promise.resolve({ data: [action, countAction, countActionWithoutSuggestedCounts] });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "终止处方" }));
    expect(await screen.findByText("确认终止当前处方？")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认终止" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/prescriptions/1/terminate/");
    });
  });
});
