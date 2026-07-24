import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WearableBindingPanel } from "./WearableBindingPanel";

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
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <WearableBindingPanel projectPatientId={12} />
    </QueryClientProvider>,
  );
}

describe("WearableBindingPanel", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockResolvedValue({ data: { project_patient_id: 12, patient_id: 101, binding: null } });
  });

  afterEach(() => cleanup());

  it("按固定简码绑定后展示本地成功与通信测试结果", async () => {
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/project-patients/12/bind/") {
        return Promise.resolve({
          data: { id: 33, patient_id: 101, device_id: 7, short_code: "0826", bound_at: "2026-07-24T10:00:00Z" },
        });
      }
      if (url === "/wearables/devices/7/check-status/") {
        return Promise.resolve({ data: { device_id: 7, online: false, battery_level: 30, last_communication_at: null } });
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    renderPanel();

    fireEvent.change(await screen.findByLabelText("设备固定简码"), { target: { value: "0826" } });
    fireEvent.click(screen.getByRole("button", { name: "绑定设备" }));

    expect(await screen.findByText("患者设备绑定成功")).toBeInTheDocument();
    expect(await screen.findByText("设备通信异常")).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith("/wearables/project-patients/12/bind/", { short_code: "0826" });
    expect(mockPost).toHaveBeenCalledWith("/wearables/devices/7/check-status/");
  });

  it("直接显示后端返回的脱敏绑定冲突信息", async () => {
    mockPost.mockRejectedValue({ response: { data: { detail: "设备已绑定患者王*" } } });
    renderPanel();

    fireEvent.change(await screen.findByLabelText("设备固定简码"), { target: { value: "0826" } });
    fireEvent.click(screen.getByRole("button", { name: "绑定设备" }));

    expect(await screen.findByText("设备已绑定患者王*")).toBeInTheDocument();
  });

  it("解绑确认明确保留历史研究数据", async () => {
    mockGet.mockResolvedValue({
      data: {
        project_patient_id: 12,
        patient_id: 101,
        binding: { id: 33, patient_id: 101, device_id: 7, short_code: "0826", bound_at: "2026-07-24T10:00:00Z" },
      },
    });
    renderPanel();

    await screen.findByText("当前设备");
    fireEvent.click(screen.getByRole("button", { name: "解绑设备" }));

    expect(await screen.findByText(/历史研究数据不会删除/)).toBeInTheDocument();
  });
});
