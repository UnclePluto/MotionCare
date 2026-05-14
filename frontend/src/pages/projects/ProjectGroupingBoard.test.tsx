import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import {
  ProjectGroupingBoard,
  type ProjectGroupingBoardActionState,
  type ProjectGroupingBoardHandle,
} from "./ProjectGroupingBoard";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

const studyGroupsGetCount = () =>
  mockGet.mock.calls.filter(([url, config]) => {
    const params =
      typeof config === "object" && config ? (config as { params?: Record<string, unknown> }).params : undefined;
    return url === "/studies/groups/" && params?.project === 1;
  }).length;

const dragPatientToGroup = (patientId: number, groupId: number) => {
  const data = new Map<string, string>();
  const dataTransfer = {
    setData: vi.fn((type: string, value: string) => data.set(type, value)),
    getData: vi.fn((type: string) => data.get(type) ?? ""),
  };

  fireEvent.dragStart(screen.getByTestId(`local-assignment-${patientId}`), { dataTransfer });
  fireEvent.dragOver(screen.getByTestId(`group-drop-${groupId}`), { dataTransfer });
  fireEvent.drop(screen.getByTestId(`group-drop-${groupId}`), { dataTransfer });
};

const dropRawPatientIdToGroup = (rawPatientId: string, groupId: number) => {
  const dataTransfer = {
    getData: vi.fn(() => rawPatientId),
  };

  fireEvent.dragOver(screen.getByTestId(`group-drop-${groupId}`), { dataTransfer });
  fireEvent.drop(screen.getByTestId(`group-drop-${groupId}`), { dataTransfer });
};

function ProjectGroupingBoardHarness({
  projectId,
  groupRevision = 0,
  readOnly = false,
}: {
  projectId: number;
  groupRevision?: number;
  readOnly?: boolean;
}) {
  const boardRef = useRef<ProjectGroupingBoardHandle>(null);
  const [actionState, setActionState] = useState<ProjectGroupingBoardActionState>({
    hasActiveGroups: false,
    hasEligibleSelection: false,
    confirmLoading: false,
  });

  return (
    <>
      <button
        type="button"
        disabled={readOnly}
        data-has-active-groups={String(actionState.hasActiveGroups)}
        data-has-eligible-selection={String(actionState.hasEligibleSelection)}
        onClick={() => boardRef.current?.randomize()}
      >
        随机分组
      </button>
      <button
        type="button"
        disabled={readOnly}
        aria-busy={actionState.confirmLoading}
        onClick={() => boardRef.current?.confirm()}
      >
        确认分组
      </button>
      <ProjectGroupingBoard
        ref={boardRef}
        projectId={projectId}
        groupRevision={groupRevision}
        readOnly={readOnly}
        onActionStateChange={setActionState}
      />
    </>
  );
}

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("ProjectGroupingBoard", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config
          ? (config as { params?: Record<string, unknown> }).params
          : undefined;

      if (url === "/patients/") {
        return Promise.resolve({
          data: [
            { id: 1, name: "未入组甲", gender: "male", phone: "13900000001" },
            { id: 2, name: "未入组乙", gender: "female", phone: "13900000002" },
            { id: 201, name: "已确认丙", gender: "male", phone: "13900000201" },
          ],
        });
      }
      if (url === "/studies/groups/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            { id: 10, name: "试验组", target_ratio: 50, sort_order: 0, is_active: true },
            { id: 11, name: "对照组", target_ratio: 50, sort_order: 1, is_active: true },
          ],
        });
      }
      if (url === "/studies/project-patients/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            {
              id: 9001,
              project: 1,
              patient: 201,
              patient_name: "已确认丙",
              patient_phone: "13900000201",
              group: 10,
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  it("全量患者中已确认患者置灰禁选，组列仍展示已确认患者", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("全量患者")).toBeInTheDocument());
    const patientSelection = screen.getByText("全量患者").closest(".ant-card");
    expect(patientSelection).toBeTruthy();
    expect(within(patientSelection as HTMLElement).getByText(/未入组甲/)).toBeInTheDocument();
    expect(within(patientSelection as HTMLElement).getByText(/未入组乙/)).toBeInTheDocument();
    expect(within(patientSelection as HTMLElement).getByText(/已确认丙/)).toBeInTheDocument();
    expect(screen.getByLabelText(/选择患者 已确认丙/)).toBeDisabled();

    const experimentGroup = screen.getByText("试验组").closest(".ant-card");
    expect(experimentGroup).toBeTruthy();
    expect(within(experimentGroup as HTMLElement).getByText("已确认丙")).toBeInTheDocument();
    expect(within(experimentGroup as HTMLElement).getByText("已确认")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "研究录入" })[0]).toHaveAttribute(
      "href",
      "/research-entry/project-patients/9001",
    );
    expect(screen.getAllByRole("link", { name: "打开 CRF" })[0]).toHaveAttribute(
      "href",
      "/crf?projectPatientId=9001",
    );
  });

  it("停用分组内已有已确认患者时仍渲染该分组列", async () => {
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config
          ? (config as { params?: Record<string, unknown> }).params
          : undefined;

      if (url === "/patients/") {
        return Promise.resolve({
          data: [
            { id: 1, name: "未入组甲", gender: "male", phone: "13900000001" },
            { id: 202, name: "已确认丁", gender: "female", phone: "13900000202" },
          ],
        });
      }
      if (url === "/studies/groups/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            { id: 10, name: "试验组", target_ratio: 100, sort_order: 0, is_active: true },
            { id: 12, name: "已停用组", target_ratio: 1, sort_order: 2, is_active: false },
          ],
        });
      }
      if (url === "/studies/project-patients/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            {
              id: 9002,
              project: 1,
              patient: 202,
              patient_name: "已确认丁",
              patient_phone: "13900000202",
              group: 12,
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("已停用组")).toBeInTheDocument());
    const inactiveGroup = screen.getByText("已停用组").closest(".ant-card");
    expect(inactiveGroup).toBeTruthy();
    expect(within(inactiveGroup as HTMLElement).getByText("已确认丁")).toBeInTheDocument();
    expect(within(inactiveGroup as HTMLElement).getByText("已确认")).toBeInTheDocument();
  });

  it("随机只生成本地临时结果，不调用后端 randomize", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));

    await waitFor(() => expect(screen.getByText("本轮")).toBeInTheDocument());
    expect(mockPost.mock.calls.map((call) => call[0])).not.toContain("/studies/projects/1/randomize/");
  });

  it("不展示全量患者临时随机说明文案", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/全量患者/)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    expect(screen.queryByText(/勾选未确认入组患者后点击/)).not.toBeInTheDocument();
  });

  it("不展示旧比例按钮并允许无本轮随机时只保存占比", async () => {
    mockPost.mockResolvedValueOnce({ data: { confirmed: 0, ratios_updated: 2, created: [] } });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("全量患者")).toBeInTheDocument());
    expect(screen.queryByText(new RegExp("权" + "重"))).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /应用占比/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost).toHaveBeenCalledWith("/studies/projects/1/confirm-grouping/", {
      group_ratios: [
        { group_id: 10, target_ratio: 50 },
        { group_id: 11, target_ratio: 50 },
      ],
      assignments: [],
    });
  });

  it("三组占比展示为后端保存的百分比", async () => {
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config
          ? (config as { params?: Record<string, unknown> }).params
          : undefined;
      if (url === "/patients/") return Promise.resolve({ data: [] });
      if (url === "/studies/groups/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            { id: 10, name: "A组", target_ratio: 34, sort_order: 0, is_active: true },
            { id: 11, name: "B组", target_ratio: 33, sort_order: 1, is_active: true },
            { id: 12, name: "C组", target_ratio: 33, sort_order: 2, is_active: true },
          ],
        });
      }
      if (url === "/studies/project-patients/" && params?.project === 1) return Promise.resolve({ data: [] });
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByLabelText("A组占比")).toHaveValue("34"));
    expect(screen.getByLabelText("B组占比")).toHaveValue("33");
    expect(screen.getByLabelText("C组占比")).toHaveValue("33");
  });

  it("分组版本变化后把启用组占比草案自动均衡为 100%", async () => {
    let groupRows = [
      { id: 10, name: "A组", target_ratio: 50, sort_order: 0, is_active: true },
      { id: 11, name: "B组", target_ratio: 50, sort_order: 1, is_active: true },
    ];
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config
          ? (config as { params?: Record<string, unknown> }).params
          : undefined;
      if (url === "/patients/") return Promise.resolve({ data: [] });
      if (url === "/studies/groups/" && params?.project === 1) return Promise.resolve({ data: groupRows });
      if (url === "/studies/project-patients/" && params?.project === 1) return Promise.resolve({ data: [] });
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} groupRevision={0} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByLabelText("A组占比")).toHaveValue("50"));
    groupRows = [
      { id: 10, name: "A组", target_ratio: 50, sort_order: 0, is_active: true },
      { id: 11, name: "B组", target_ratio: 50, sort_order: 1, is_active: true },
      { id: 12, name: "C组", target_ratio: 1, sort_order: 2, is_active: true },
    ];

    await qc.invalidateQueries({ queryKey: ["study-groups", 1] });
    rerender(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} groupRevision={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByLabelText("A组占比")).toHaveValue("34"));
    expect(screen.getByLabelText("B组占比")).toHaveValue("33");
    expect(screen.getByLabelText("C组占比")).toHaveValue("33");
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("占比合计不是 100 时不提交确认", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByLabelText("试验组占比")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("试验组占比"), { target: { value: "40" } });
    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    expect(mockPost).not.toHaveBeenCalled();
    expect((await screen.findAllByText(/启用组占比合计须为 100%/)).length).toBeGreaterThan(0);
  });

  it("取消勾选会同步移除本轮患者", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));
    await waitFor(() => expect(screen.getByText("本轮")).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));

    await waitFor(() => expect(screen.queryByText("本轮")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: /确认分组/ })).toBeEnabled();

    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));

    expect(screen.queryByText("本轮")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /确认分组/ })).toBeEnabled();
  });

  it("允许拖拽本轮随机患者到另一个分组后再确认", async () => {
    mockPost.mockResolvedValueOnce({
      data: { confirmed: 1, created: [{ project_patient_id: 9010, patient_id: 1, group_id: 11 }] },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));
    await waitFor(() => expect(screen.getByTestId("local-assignment-1")).toBeInTheDocument());

    dragPatientToGroup(1, 11);
    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, payload] = mockPost.mock.calls.at(-1) ?? [];
    expect(url).toBe("/studies/projects/1/confirm-grouping/");
    expect(payload.assignments).toEqual([{ patient_id: 1, group_id: 11 }]);
  });

  it("停用组不接受本轮随机患者 drop", async () => {
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config
          ? (config as { params?: Record<string, unknown> }).params
          : undefined;

      if (url === "/patients/") {
        return Promise.resolve({
          data: [
            { id: 1, name: "未入组甲", gender: "male", phone: "13900000001" },
            { id: 202, name: "已确认丁", gender: "female", phone: "13900000202" },
          ],
        });
      }
      if (url === "/studies/groups/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            { id: 10, name: "试验组", target_ratio: 100, sort_order: 0, is_active: true },
            { id: 12, name: "已停用组", target_ratio: 1, sort_order: 1, is_active: false },
          ],
        });
      }
      if (url === "/studies/project-patients/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            {
              id: 9002,
              project: 1,
              patient: 202,
              patient_name: "已确认丁",
              patient_phone: "13900000202",
              group: 12,
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    mockPost.mockResolvedValueOnce({
      data: { confirmed: 1, created: [{ project_patient_id: 9010, patient_id: 1, group_id: 10 }] },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));
    await waitFor(() => expect(screen.getByTestId("local-assignment-1")).toBeInTheDocument());

    dragPatientToGroup(1, 12);
    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [, payload] = mockPost.mock.calls.at(-1) ?? [];
    expect(payload.assignments).toEqual([{ patient_id: 1, group_id: 10 }]);
  });

  it("非法 dataTransfer drop 不改变本轮随机患者分组", async () => {
    mockPost.mockResolvedValueOnce({
      data: { confirmed: 1, created: [{ project_patient_id: 9010, patient_id: 1, group_id: 10 }] },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));
    await waitFor(() => expect(screen.getByTestId("local-assignment-1")).toBeInTheDocument());
    const initialGroupId = screen
      .getByTestId("group-drop-10")
      .querySelector('[data-testid="local-assignment-1"]')
      ? 10
      : 11;

    dropRawPatientIdToGroup("", 11);
    dropRawPatientIdToGroup("1.5", 11);
    dropRawPatientIdToGroup("999", 11);
    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [, payload] = mockPost.mock.calls.at(-1) ?? [];
    expect(payload.assignments).toEqual([{ patient_id: 1, group_id: initialGroupId }]);
  });

  it("组卡片使用内部悬浮删除 X 和精简患者操作", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    const groupCard = await screen.findByTestId("group-card-10");
    expect(groupCard).toHaveStyle({ minWidth: "460px", flexBasis: "460px" });
    expect(within(groupCard).queryByText("占比 %")).not.toBeInTheDocument();
    expect(within(groupCard).getByText("%")).toHaveClass("ratio-input-addon");
    const deleteButton = within(groupCard).getByRole("button", { name: "删除试验组" });
    expect(deleteButton).toHaveClass("group-delete-bubble");
    expect(within(groupCard).getByTestId("confirmed-patient-201")).toHaveClass("patient-card-line");
    expect(within(groupCard).getByRole("link", { name: "详情" })).toBeInTheDocument();
    expect(within(groupCard).getByRole("link", { name: "研究录入" })).toHaveAttribute(
      "href",
      "/research-entry/project-patients/9001",
    );
    expect(within(groupCard).getByRole("link", { name: "打开 CRF" })).toHaveAttribute(
      "href",
      "/crf?projectPatientId=9001",
    );
    expect(within(groupCard).getByRole("button", { name: "解绑" })).toBeInTheDocument();
  });

  it("只读模式禁用分组操作并隐藏破坏性入口", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} readOnly />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "随机分组" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "确认分组" })).toBeDisabled();
    expect(screen.getByLabelText(/选择患者 未入组甲/)).toBeDisabled();
    expect(screen.getByLabelText("试验组占比")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "删除试验组" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "解绑" })).not.toBeInTheDocument();
  });

  it("确认分组提交本地 assignments 并刷新", async () => {
    mockPost.mockResolvedValueOnce({
      data: { confirmed: 1, created: [{ project_patient_id: 9010, patient_id: 1, group_id: 10 }] },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));
    await waitFor(() => expect(screen.getByText("本轮")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    const [url, payload] = mockPost.mock.calls.at(-1) ?? [];
    expect(url).toBe("/studies/projects/1/confirm-grouping/");
    expect(payload.group_ratios).toEqual([
      { group_id: 10, target_ratio: 50 },
      { group_id: 11, target_ratio: 50 },
    ]);
    expect(payload.assignments).toHaveLength(1);
    expect(payload.assignments[0].patient_id).toBe(1);
    expect([10, 11]).toContain(payload.assignments[0].group_id);
  });

  it("普通刷新不覆盖已编辑占比，确认成功后刷新并同步后端占比", async () => {
    let groupRows = [
      { id: 10, name: "试验组", target_ratio: 50, sort_order: 0, is_active: true },
      { id: 11, name: "对照组", target_ratio: 50, sort_order: 1, is_active: true },
    ];
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config
          ? (config as { params?: Record<string, unknown> }).params
          : undefined;

      if (url === "/patients/") {
        return Promise.resolve({
          data: [
            { id: 1, name: "未入组甲", gender: "male", phone: "13900000001" },
            { id: 2, name: "未入组乙", gender: "female", phone: "13900000002" },
          ],
        });
      }
      if (url === "/studies/groups/" && params?.project === 1) {
        return Promise.resolve({ data: groupRows });
      }
      if (url === "/studies/project-patients/" && params?.project === 1) {
        return Promise.resolve({ data: [] });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    mockPost.mockResolvedValueOnce({ data: { confirmed: 0, ratios_updated: 2, created: [] } });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByLabelText("试验组占比")).toHaveValue("50"));
    fireEvent.change(screen.getByLabelText("试验组占比"), { target: { value: "75" } });
    fireEvent.change(screen.getByLabelText("对照组占比"), { target: { value: "25" } });

    groupRows = [
      { id: 10, name: "试验组", target_ratio: 60, sort_order: 0, is_active: true },
      { id: 11, name: "对照组", target_ratio: 40, sort_order: 1, is_active: true },
    ];
    const beforeManualRefresh = studyGroupsGetCount();
    await qc.invalidateQueries({ queryKey: ["study-groups", 1] });
    await waitFor(() => expect(studyGroupsGetCount()).toBeGreaterThan(beforeManualRefresh));
    expect(screen.getByLabelText("试验组占比")).toHaveValue("75");
    expect(screen.getByLabelText("对照组占比")).toHaveValue("25");

    const beforeConfirm = studyGroupsGetCount();
    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    await waitFor(() => expect(studyGroupsGetCount()).toBeGreaterThan(beforeConfirm));
    await waitFor(() => expect(screen.getByLabelText("试验组占比")).toHaveValue("60"));
    expect(screen.getByLabelText("对照组占比")).toHaveValue("40");
  });

  it("网络错误后保留本轮草案以便重试", async () => {
    mockPost.mockRejectedValueOnce(new Error("network"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));
    await waitFor(() => expect(screen.getByText("本轮")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole("button", { name: /确认分组/ })).toBeEnabled());
    expect(screen.getByText("本轮")).toBeInTheDocument();
    expect(screen.getByLabelText(/选择患者 未入组甲/)).toBeChecked();
  });

  it("确认失败后清空本轮结果", async () => {
    mockPost.mockRejectedValueOnce({ response: { data: { detail: "患者已在其他项目入组" } } });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoardHarness projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));
    await waitFor(() => expect(screen.getByText("本轮")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

    await waitFor(() => expect(screen.queryByText("本轮")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: /确认分组/ })).toBeEnabled());
  });
});
