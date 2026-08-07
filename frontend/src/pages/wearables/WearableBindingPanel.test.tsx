import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  WearableBindingActions,
  WearableBindingFeedback,
  WearableBindingModals,
  WearableBindingPanel,
  WearableBindingProvider,
  useWearableBindingView,
} from "./WearableBindingPanel";
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

function postCount(url: string) {
  return mockPost.mock.calls.filter(([calledUrl]) => calledUrl === url).length;
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

function ComposableBindingDetails() {
  const view = useWearableBindingView();
  const binding = view.isLoading ? null : view.binding;
  return (
    <div>
      <span>设备简码：{binding?.short_code ?? "—"}</span>
      <span>设备 ID：{binding?.device_id ?? "—"}</span>
      <span>设备绑定时间：{binding?.bound_at ?? "—"}</span>
    </div>
  );
}

function ComposableBindingControls() {
  const view = useWearableBindingView();
  return (
    <>
      <button type="button" onClick={view.openBind}>强制打开绑定</button>
      <button type="button" onClick={() => view.setShortCode("0826")}>强制填入简码</button>
      <button type="button" onClick={view.submitBind}>强制提交绑定</button>
    </>
  );
}

function renderComposableBinding(projectPatientId = 12) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <WearableBindingProvider projectPatientId={projectPatientId}>
        <WearableBindingActions />
        <ComposableBindingDetails />
        <ComposableBindingControls />
        <WearableBindingFeedback />
        <WearableBindingModals />
      </WearableBindingProvider>
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
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

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));
    const input = await screen.findByLabelText("设备固定简码");
    fireEvent.change(input, { target: { value: "0a8269" } });
    expect(input).toHaveValue("0826");
    fireEvent.click(screen.getByRole("button", { name: "确认绑定" }));

    expect(await screen.findByText("患者设备绑定成功")).toBeInTheDocument();
    expect(await screen.findByText("设备通信异常")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "让设备响铃" })).not.toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith("/wearables/project-patients/12/bind/", { short_code: "0826" });
    expect(mockPost).toHaveBeenCalledWith("/wearables/devices/7/check-status/");
    expect(screen.getByRole("dialog", { name: "绑定穿戴设备" })).toHaveClass("ant-zoom-leave");
  });

  it("组合片段在未绑定时通过共享 Provider 打开绑定弹窗", async () => {
    renderComposableBinding();

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));

    expect(await screen.findByRole("dialog", { name: "绑定穿戴设备" })).toBeInTheDocument();
    expect(screen.getByText("设备固定简码").closest("label")).not.toBeNull();
    expect(screen.getByLabelText("设备固定简码")).toBeInTheDocument();
  });

  it("组合片段在已有绑定时共享设备详情且不显示绑定按钮", async () => {
    mockGet.mockResolvedValue({
      data: { ...emptyBinding(), binding: binding() },
    });
    renderComposableBinding();

    expect(await screen.findByText(/设备简码：0826/)).toBeInTheDocument();
    expect(screen.getByText(/设备 ID：7/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "绑定穿戴设备" })).not.toBeInTheDocument();
  });

  it("公开 Provider 操作不会为已有绑定打开或提交新绑定", async () => {
    mockGet.mockResolvedValue({ data: { ...emptyBinding(), binding: binding() } });
    renderComposableBinding();

    await screen.findByText(/设备简码：0826/);
    fireEvent.click(screen.getByRole("button", { name: "强制打开绑定" }));
    fireEvent.click(screen.getByRole("button", { name: "强制填入简码" }));
    fireEvent.click(screen.getByRole("button", { name: "强制提交绑定" }));

    expect(screen.queryByRole("dialog", { name: "绑定穿戴设备" })).not.toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("绑定弹窗打开期间到达绑定更新会关闭弹窗并拒绝提交", async () => {
    const { queryClient } = renderComposableBinding();

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));
    fireEvent.change(await screen.findByLabelText("设备固定简码"), { target: { value: "0826" } });
    act(() => {
      queryClient.setQueryData<ProjectPatientWearableBinding>(
        ["project-patient-wearable-binding", 12],
        { ...emptyBinding(), binding: binding() },
      );
    });
    expect(await screen.findByText(/设备简码：0826/)).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "绑定穿戴设备" })).toHaveClass("ant-zoom-leave");
    expect(screen.getByRole("button", { name: "确认绑定" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "强制提交绑定" }));

    expect(mockPost).not.toHaveBeenCalled();
  });

  it("外部绑定更新自动关闭弹窗时会清空简码和旧错误", async () => {
    mockPost.mockRejectedValue({ response: { data: { detail: "设备已绑定患者王*。" } } });
    const { queryClient } = renderComposableBinding();

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));
    fireEvent.change(await screen.findByLabelText("设备固定简码"), { target: { value: "0826" } });
    fireEvent.click(screen.getByRole("button", { name: "确认绑定" }));
    expect(await screen.findByText("设备已绑定患者王*。")).toBeInTheDocument();

    act(() => {
      queryClient.setQueryData<ProjectPatientWearableBinding>(
        ["project-patient-wearable-binding", 12],
        { ...emptyBinding(), binding: binding() },
      );
    });
    expect(await screen.findByText(/设备简码：0826/)).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "绑定穿戴设备" })).toHaveClass("ant-zoom-leave");

    act(() => {
      queryClient.setQueryData<ProjectPatientWearableBinding>(
        ["project-patient-wearable-binding", 12],
        emptyBinding(),
      );
    });
    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));

    expect(await screen.findByLabelText("设备固定简码")).toHaveValue("");
    expect(screen.queryByText("设备已绑定患者王*。")).not.toBeInTheDocument();
  });

  it("直接显示后端返回的脱敏绑定冲突信息", async () => {
    mockPost.mockRejectedValue({ response: { data: { detail: "设备已绑定患者王*。" } } });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));
    fireEvent.change(await screen.findByLabelText("设备固定简码"), { target: { value: "0826" } });
    fireEvent.click(screen.getByRole("button", { name: "确认绑定" }));

    expect(await screen.findByText("设备已绑定患者王*。")).toBeInTheDocument();
  });

  it("取消绑定弹窗后再次打开会清空简码和旧错误", async () => {
    mockPost.mockRejectedValue({ response: { data: { detail: "设备已绑定患者王*。" } } });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));
    const input = await screen.findByLabelText("设备固定简码");
    fireEvent.change(input, { target: { value: "0a8269" } });
    expect(input).toHaveValue("0826");
    fireEvent.click(screen.getByRole("button", { name: "确认绑定" }));
    expect(await screen.findByText("设备已绑定患者王*。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /取\s*消/ }));
    fireEvent.click(screen.getByRole("button", { name: "绑定穿戴设备" }));

    expect(await screen.findByLabelText("设备固定简码")).toHaveValue("");
    expect(screen.queryByText("设备已绑定患者王*。")).not.toBeInTheDocument();
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

    await screen.findByText("0826");
    fireEvent.click(screen.getByRole("button", { name: "解绑设备" }));

    expect(await screen.findByText(/历史研究数据不会删除/)).toBeInTheDocument();
  });

  it("解绑请求待响应时重复确认只发送一次", async () => {
    let resolveUnbind!: (value: { data: unknown }) => void;
    const pendingUnbind = new Promise<{ data: unknown }>((resolve) => {
      resolveUnbind = resolve;
    });
    mockGet.mockResolvedValue({ data: { ...emptyBinding(), binding: binding() } });
    mockPost.mockReturnValue(pendingUnbind);
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "解绑设备" }));
    const confirm = await screen.findByRole("button", { name: /确认解绑/ });
    fireEvent.click(confirm);
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
    fireEvent.click(confirm);

    await act(async () => {
      await Promise.resolve();
      expect(mockPost).toHaveBeenCalledTimes(1);
      expect(confirm).toHaveClass("ant-btn-loading");
      resolveUnbind({ data: { historical_data_preserved: true } });
      await pendingUnbind;
    });
  });

  it("解绑请求 pending 时患者 A 到 B 再回 A 仍只发送一次", async () => {
    let resolveUnbind!: (value: { data: unknown }) => void;
    const pendingUnbind = new Promise<{ data: unknown }>((resolve) => {
      resolveUnbind = resolve;
    });
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/12/")) {
        return Promise.resolve({ data: { ...emptyBinding(12, 101), binding: binding() } });
      }
      if (url.includes("/13/")) {
        return Promise.resolve({
          data: {
            ...emptyBinding(13, 202),
            binding: binding({ id: 44, patient_id: 202, device_id: 8, short_code: "1002" }),
          },
        });
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/bindings/33/unbind/") return pendingUnbind;
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    const { rerenderPanel } = renderPanel(12);

    fireEvent.click(await screen.findByRole("button", { name: "解绑设备" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认解绑" }));
    await waitFor(() => expect(postCount("/wearables/bindings/33/unbind/")).toBe(1));

    rerenderPanel(13);
    expect(await screen.findByText("1002")).toBeInTheDocument();
    rerenderPanel(12);
    expect(await screen.findByText("0826")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "解绑设备" }));
    const confirm = await screen.findByRole("button", { name: /确认解绑/ });
    fireEvent.click(confirm);

    await act(async () => {
      await Promise.resolve();
      expect(postCount("/wearables/bindings/33/unbind/")).toBe(1);
      expect(confirm).toHaveClass("ant-btn-loading");
      resolveUnbind({ data: { historical_data_preserved: true } });
      await pendingUnbind;
    });
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

  it("首次绑定状态查询完成前没有绑定入口且 Provider 拒绝打开或提交", async () => {
    let resolveGet!: (value: { data: ProjectPatientWearableBinding }) => void;
    const pendingGet = new Promise<{ data: ProjectPatientWearableBinding }>((resolve) => {
      resolveGet = resolve;
    });
    mockGet.mockReturnValue(pendingGet);
    renderComposableBinding();

    expect(await screen.findByText("设备绑定状态加载中")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "绑定穿戴设备" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("设备固定简码")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "强制打开绑定" }));
    fireEvent.click(screen.getByRole("button", { name: "强制填入简码" }));
    fireEvent.click(screen.getByRole("button", { name: "强制提交绑定" }));

    expect(screen.queryByRole("dialog", { name: "绑定穿戴设备" })).not.toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();

    await act(async () => {
      resolveGet({ data: emptyBinding() });
      await pendingGet;
    });
    expect(await screen.findByRole("button", { name: "绑定穿戴设备" })).toBeInTheDocument();
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

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));
    fireEvent.change(await screen.findByLabelText("设备固定简码"), {
      target: { value: "0826" },
    });
    void queryClient.invalidateQueries({
      queryKey: ["project-patient-wearable-binding", 12],
    });
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "确认绑定" }));

    expect(await screen.findByText("0826")).toBeInTheDocument();
    expect(queryClient.getQueryData(["project-patient-wearable-binding", 12])).toEqual({
      project_patient_id: 12,
      patient_id: 101,
      binding: binding(),
    });

    await act(async () => {
      resolveStaleGet({ data: emptyBinding() });
      await staleGet;
    });
    expect(screen.getByText("0826")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "绑定穿戴设备" })).not.toBeInTheDocument();
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

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));
    fireEvent.change(await screen.findByLabelText("设备固定简码"), {
      target: { value: "0826" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认绑定" }));
    rerenderPanel(13);

    expect(await screen.findByRole("button", { name: "绑定穿戴设备" })).toBeInTheDocument();
    await act(async () => {
      resolveBind({ data: binding() });
      await pendingBind;
    });

    expect(screen.queryByText("患者设备绑定成功")).not.toBeInTheDocument();
    expect(screen.queryByText("0826")).not.toBeInTheDocument();
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
    expect(await screen.findByRole("button", { name: "绑定穿戴设备" })).toBeInTheDocument();
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

  it("解绑后忽略原绑定迟到的通信成功结果", async () => {
    let resolveStatus!: (value: { data: WearableStatus }) => void;
    const pendingStatus = new Promise<{ data: WearableStatus }>((resolve) => {
      resolveStatus = resolve;
    });
    mockGet
      .mockResolvedValueOnce({
        data: { ...emptyBinding(), binding: binding() },
      })
      .mockResolvedValue({ data: emptyBinding() });
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/devices/7/check-status/") return pendingStatus;
      if (url === "/wearables/bindings/33/unbind/") {
        return Promise.resolve({
          data: {
            binding: binding({ unbound_at: "2026-07-24T11:00:00Z" }),
            historical_data_preserved: true,
          },
        });
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "通信测试" }));
    fireEvent.click(screen.getByRole("button", { name: "解绑设备" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认解绑" }));
    expect(await screen.findByText("设备解绑成功")).toBeInTheDocument();

    await act(async () => {
      resolveStatus({
        data: status({
          online: true,
          last_communication_at: "2026-07-24T02:00:00Z",
          capabilities: { ring: true },
        }),
      });
      await pendingStatus;
    });

    expect(screen.queryByText("设备通信正常")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "让设备响铃" })).not.toBeInTheDocument();
  });

  it("解绑后忽略原绑定迟到的通信失败结果", async () => {
    let rejectStatus!: (reason: unknown) => void;
    const pendingStatus = new Promise<{ data: WearableStatus }>((_resolve, reject) => {
      rejectStatus = reject;
    });
    mockGet
      .mockResolvedValueOnce({
        data: { ...emptyBinding(), binding: binding() },
      })
      .mockResolvedValue({ data: emptyBinding() });
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/devices/7/check-status/") return pendingStatus;
      if (url === "/wearables/bindings/33/unbind/") {
        return Promise.resolve({
          data: {
            binding: binding({ unbound_at: "2026-07-24T11:00:00Z" }),
            historical_data_preserved: true,
          },
        });
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "通信测试" }));
    fireEvent.click(screen.getByRole("button", { name: "解绑设备" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认解绑" }));
    expect(await screen.findByText("设备解绑成功")).toBeInTheDocument();

    await act(async () => {
      rejectStatus({ response: { data: { detail: "原设备通信失败。" } } });
      try {
        await pendingStatus;
      } catch {
        // mutation 会消费该失败；这里仅等待迟到请求完成。
      }
    });

    expect(screen.queryByText("原设备通信失败。")).not.toBeInTheDocument();
  });

  it("绑定对象变化后忽略原绑定迟到的通信结果", async () => {
    let resolveStatus!: (value: { data: WearableStatus }) => void;
    const pendingStatus = new Promise<{ data: WearableStatus }>((resolve) => {
      resolveStatus = resolve;
    });
    mockGet.mockResolvedValue({
      data: { ...emptyBinding(), binding: binding() },
    });
    mockPost.mockReturnValue(pendingStatus);
    const { queryClient } = renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "通信测试" }));
    act(() => {
      queryClient.setQueryData<ProjectPatientWearableBinding>(
        ["project-patient-wearable-binding", 12],
        {
          ...emptyBinding(),
          binding: binding({ id: 44, device_id: 8, short_code: "1002" }),
        },
      );
    });
    expect(await screen.findByText("1002")).toBeInTheDocument();

    await act(async () => {
      resolveStatus({
        data: status({
          online: true,
          last_communication_at: "2026-07-24T02:00:00Z",
          capabilities: { ring: true },
        }),
      });
      await pendingStatus;
    });

    expect(screen.queryByText("设备通信正常")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "让设备响铃" })).not.toBeInTheDocument();
  });

  it("三位简码按回车不会提交绑定", async () => {
    mockPost.mockResolvedValue({ data: binding() });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));
    const input = await screen.findByLabelText("设备固定简码");
    fireEvent.change(input, { target: { value: "082" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", keyCode: 13 });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockPost).not.toHaveBeenCalled();
  });

  it("四位简码连续回车在请求 pending 时只提交一次", async () => {
    let resolveBind!: (value: { data: WearableBinding }) => void;
    const pendingBind = new Promise<{ data: WearableBinding }>((resolve) => {
      resolveBind = resolve;
    });
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/project-patients/12/bind/") return pendingBind;
      if (url === "/wearables/devices/7/check-status/") {
        return Promise.resolve({ data: status() });
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));
    const input = await screen.findByLabelText("设备固定简码");
    fireEvent.change(input, { target: { value: "0826" } });
    await act(async () => {
      fireEvent.keyDown(input, { key: "Enter", code: "Enter", keyCode: 13 });
      fireEvent.keyDown(input, { key: "Enter", code: "Enter", keyCode: 13 });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(postCount("/wearables/project-patients/12/bind/")).toBe(1);
    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: /确认绑定/ })).toBeDisabled();
    await act(async () => {
      resolveBind({ data: binding() });
      await pendingBind;
    });
  });

  it("四位简码回车后立即点击确认在请求 pending 时只提交一次", async () => {
    let resolveBind!: (value: { data: WearableBinding }) => void;
    const pendingBind = new Promise<{ data: WearableBinding }>((resolve) => {
      resolveBind = resolve;
    });
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/project-patients/12/bind/") return pendingBind;
      if (url === "/wearables/devices/7/check-status/") {
        return Promise.resolve({ data: status() });
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "绑定穿戴设备" }));
    const input = await screen.findByLabelText("设备固定简码");
    fireEvent.change(input, { target: { value: "0826" } });
    const confirm = screen.getByRole("button", { name: "确认绑定" });
    await act(async () => {
      fireEvent.keyDown(input, { key: "Enter", code: "Enter", keyCode: 13 });
      fireEvent.click(confirm);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(postCount("/wearables/project-patients/12/bind/")).toBe(1);
    await act(async () => {
      resolveBind({ data: binding() });
      await pendingBind;
    });
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
    expect(screen.getByRole("button", { name: "绑定穿戴设备" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "解绑设备" })).not.toBeInTheDocument();

    await act(async () => {
      resolveRefresh({ data: emptyBinding() });
      await pendingRefresh;
    });
  });
});
