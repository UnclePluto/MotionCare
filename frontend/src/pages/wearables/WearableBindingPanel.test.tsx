import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WearableBindingPanel } from "./WearableBindingPanel";
import type { ProjectPatientWearableBinding, WearableBinding, WearableStatus } from "./types";

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

function emptyBinding(projectPatientId = 12, patientId = 101): ProjectPatientWearableBinding {
  return { project_patient_id: projectPatientId, patient_id: patientId, binding: null };
}

function binding(overrides: Partial<WearableBinding> = {}): WearableBinding {
  return {
    id: 33,
    patient_id: 101,
    device_id: 7,
    short_code: "0826",
    bound_at: "2026-07-24T10:00:00Z",
    unbound_at: null,
    ...overrides,
  };
}

type StatusFixture = WearableStatus & {
  model: string;
  capabilities: { ring: boolean };
};

function status(overrides: Partial<StatusFixture> = {}): StatusFixture {
  return {
    device_id: 7,
    model: "M1",
    online: false,
    battery_level: 30,
    last_communication_at: null,
    capabilities: { ring: false },
    ...overrides,
  };
}

function renderPanel(projectPatientId = 12) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <WearableBindingPanel projectPatientId={projectPatientId} />
    </QueryClientProvider>,
  );
  return {
    ...view,
    queryClient,
    rerenderPanel: (nextProjectPatientId: number) =>
      view.rerender(
        <QueryClientProvider client={queryClient}>
          <WearableBindingPanel projectPatientId={nextProjectPatientId} />
        </QueryClientProvider>,
      ),
  };
}

describe("WearableBindingPanel", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockResolvedValue({ data: emptyBinding() });
  });

  afterEach(() => cleanup());

  it("按固定简码绑定后展示本地成功与通信测试结果", async () => {
    let createdBinding: WearableBinding | null = null;
    mockGet.mockImplementation(() =>
      Promise.resolve({
        data: { ...emptyBinding(), binding: createdBinding },
      }),
    );
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/project-patients/12/bind/") {
        createdBinding = binding();
        return Promise.resolve({ data: createdBinding });
      }
      if (url === "/wearables/devices/7/check-status/") {
        return Promise.resolve({ data: status() });
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    renderPanel();

    fireEvent.change(await screen.findByLabelText("设备固定简码"), { target: { value: "0826" } });
    fireEvent.click(screen.getByRole("button", { name: "绑定设备" }));

    expect(await screen.findByText("患者设备绑定成功")).toBeInTheDocument();
    expect(await screen.findByText("设备通信异常")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "让设备响铃" })).not.toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith("/wearables/project-patients/12/bind/", { short_code: "0826" });
    expect(mockPost).toHaveBeenCalledWith("/wearables/devices/7/check-status/");
  });

  it("直接显示后端返回的脱敏绑定冲突信息", async () => {
    mockPost.mockRejectedValue({ response: { data: { detail: "设备已绑定患者王*。" } } });
    renderPanel();

    fireEvent.change(await screen.findByLabelText("设备固定简码"), { target: { value: "0826" } });
    fireEvent.click(screen.getByRole("button", { name: "绑定设备" }));

    expect(await screen.findByText("设备已绑定患者王*。")).toBeInTheDocument();
  });

  it("解绑确认明确保留历史研究数据", async () => {
    mockGet.mockResolvedValue({
      data: {
        project_patient_id: 12,
        patient_id: 101,
        binding: binding(),
      },
    });
    renderPanel();

    await screen.findByText("当前设备");
    fireEvent.click(screen.getByRole("button", { name: "解绑设备" }));

    expect(await screen.findByText(/历史研究数据不会删除/)).toBeInTheDocument();
  });

  it("仅在通信测试明确返回响铃能力时显示响铃操作", async () => {
    mockGet.mockResolvedValue({
      data: {
        project_patient_id: 12,
        patient_id: 101,
        binding: binding(),
      },
    });
    mockPost.mockResolvedValue({
      data: status({ online: true, battery_level: 80, capabilities: { ring: true } }),
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "通信测试" }));

    expect(await screen.findByRole("button", { name: "让设备响铃" })).toBeInTheDocument();
  });

  it("首次绑定状态查询完成前显示加载态且不能提交绑定", async () => {
    let resolveGet!: (value: { data: ProjectPatientWearableBinding }) => void;
    const pendingGet = new Promise<{ data: ProjectPatientWearableBinding }>((resolve) => {
      resolveGet = resolve;
    });
    mockGet.mockReturnValue(pendingGet);
    renderPanel();

    expect(await screen.findByText("设备绑定状态加载中")).toBeInTheDocument();
    expect(screen.queryByLabelText("设备固定简码")).not.toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();

    await act(async () => {
      resolveGet({ data: emptyBinding() });
      await pendingGet;
    });
    expect(await screen.findByLabelText("设备固定简码")).toBeInTheDocument();
  });

  it("绑定成功会覆盖迟到的旧 GET 并写入完整绑定缓存", async () => {
    let resolveStaleGet!: (value: { data: ProjectPatientWearableBinding }) => void;
    const staleGet = new Promise<{ data: ProjectPatientWearableBinding }>((resolve) => {
      resolveStaleGet = resolve;
    });
    mockGet
      .mockResolvedValueOnce({ data: emptyBinding() })
      .mockReturnValueOnce(staleGet)
      .mockResolvedValue({ data: { ...emptyBinding(), binding: binding() } });
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/project-patients/12/bind/") {
        return Promise.resolve({ data: binding() });
      }
      if (url === "/wearables/devices/7/check-status/") {
        return Promise.resolve({ data: status() });
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    const { queryClient } = renderPanel();

    fireEvent.change(await screen.findByLabelText("设备固定简码"), {
      target: { value: "0826" },
    });
    void queryClient.invalidateQueries({
      queryKey: ["project-patient-wearable-binding", 12],
    });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "绑定设备" }));

    expect(await screen.findByText("当前设备")).toBeInTheDocument();
    expect(queryClient.getQueryData(["project-patient-wearable-binding", 12])).toEqual({
      project_patient_id: 12,
      patient_id: 101,
      binding: binding(),
    });

    await act(async () => {
      resolveStaleGet({ data: emptyBinding() });
      await staleGet;
    });
    expect(screen.getByText("当前设备")).toBeInTheDocument();
    expect(screen.queryByLabelText("设备固定简码")).not.toBeInTheDocument();
  });

  it("切换患者会清理简码且旧患者迟到的绑定响应不污染新患者", async () => {
    let resolveBind!: (value: { data: WearableBinding }) => void;
    const pendingBind = new Promise<{ data: WearableBinding }>((resolve) => {
      resolveBind = resolve;
    });
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/12/")) return Promise.resolve({ data: emptyBinding(12, 101) });
      if (url.includes("/13/")) return Promise.resolve({ data: emptyBinding(13, 202) });
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    mockPost.mockReturnValueOnce(pendingBind);
    const { rerenderPanel } = renderPanel(12);

    fireEvent.change(await screen.findByLabelText("设备固定简码"), {
      target: { value: "0826" },
    });
    fireEvent.click(screen.getByRole("button", { name: "绑定设备" }));
    rerenderPanel(13);

    expect(await screen.findByLabelText("设备固定简码")).toHaveValue("");
    await act(async () => {
      resolveBind({ data: binding() });
      await pendingBind;
    });

    expect(screen.queryByText("患者设备绑定成功")).not.toBeInTheDocument();
    expect(screen.queryByText("当前设备")).not.toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith("/wearables/project-patients/12/bind/", {
      short_code: "0826",
    });
    expect(mockPost).not.toHaveBeenCalledWith("/wearables/devices/7/check-status/");
  });

  it("切换患者会关闭解绑框并忽略旧患者迟到的通信结果", async () => {
    let resolveStatus!: (value: { data: WearableStatus }) => void;
    const pendingStatus = new Promise<{ data: WearableStatus }>((resolve) => {
      resolveStatus = resolve;
    });
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/12/")) {
        return Promise.resolve({ data: { ...emptyBinding(12, 101), binding: binding() } });
      }
      if (url.includes("/13/")) return Promise.resolve({ data: emptyBinding(13, 202) });
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    mockPost.mockReturnValueOnce(pendingStatus);
    const { rerenderPanel } = renderPanel(12);

    fireEvent.click(await screen.findByRole("button", { name: "通信测试" }));
    fireEvent.click(screen.getByRole("button", { name: "解绑设备" }));
    expect(await screen.findByText(/历史研究数据不会删除/)).toBeInTheDocument();

    rerenderPanel(13);
    expect(await screen.findByLabelText("设备固定简码")).toHaveValue("");
    expect(screen.getByRole("dialog")).toHaveClass("ant-zoom-leave");

    await act(async () => {
      resolveStatus({
        data: status({
          online: true,
          last_communication_at: "2026-07-24T02:00:00Z",
        }),
      });
      await pendingStatus;
    });
    expect(screen.queryByText("设备通信正常")).not.toBeInTheDocument();
  });

  it("解绑成功立即清空绑定、显示成功反馈并在后台校准", async () => {
    let resolveRefresh!: (value: { data: ProjectPatientWearableBinding }) => void;
    const pendingRefresh = new Promise<{ data: ProjectPatientWearableBinding }>((resolve) => {
      resolveRefresh = resolve;
    });
    mockGet
      .mockResolvedValueOnce({
        data: { ...emptyBinding(), binding: binding() },
      })
      .mockReturnValueOnce(pendingRefresh);
    mockPost.mockResolvedValueOnce({
      data: {
        binding: binding({ unbound_at: "2026-07-24T11:00:00Z" }),
        historical_data_preserved: true,
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "解绑设备" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认解绑" }));

    expect(await screen.findByText("设备解绑成功")).toBeInTheDocument();
    expect(screen.getByLabelText("设备固定简码")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "解绑设备" })).not.toBeInTheDocument();

    await act(async () => {
      resolveRefresh({ data: emptyBinding() });
      await pendingRefresh;
    });
  });
});
