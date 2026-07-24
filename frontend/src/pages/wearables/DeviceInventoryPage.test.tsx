import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DeviceInventoryPage } from "./DeviceInventoryPage";
import type { WearableDevice } from "./types";

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

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DeviceInventoryPage />
    </QueryClientProvider>,
  );
}

type DeviceFixture = WearableDevice & {
  is_bound: boolean;
  current_patient_name: string | null;
  last_sync_at: string | null;
};

function device(overrides: Partial<DeviceFixture> = {}): DeviceFixture {
  return {
    id: 7,
    provider: "miwitracker",
    external_device_id: "device-001",
    identifier_type: "device_id",
    model: "M1",
    short_code: "0826",
    enabled: true,
    is_bound: false,
    current_patient_name: null,
    last_communication_at: null,
    last_status_checked_at: null,
    last_sync_at: null,
    ...overrides,
  };
}

describe("DeviceInventoryPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockResolvedValue({ data: [] });
  });

  afterEach(() => cleanup());

  it("录入设备后保留固定四位简码的前导零", async () => {
    mockPost.mockResolvedValue({
      data: device(),
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "新增设备" }));
    fireEvent.change(screen.getByLabelText("厂商"), { target: { value: "miwitracker" } });
    fireEvent.change(screen.getByLabelText("厂商设备标识"), { target: { value: "device-001" } });
    fireEvent.change(screen.getByLabelText("标识类型"), { target: { value: "device_id" } });
    fireEvent.change(screen.getByLabelText("设备型号"), { target: { value: "M1" } });
    fireEvent.click(screen.getByRole("button", { name: "录入设备" }));

    expect(await screen.findByText("0826")).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith("/wearables/devices/", {
      provider: "miwitracker",
      external_device_id: "device-001",
      identifier_type: "device_id",
      model: "M1",
    });
  });

  it("使用后端权威绑定状态筛选并区分无患者访问权限的绑定", async () => {
    mockGet.mockResolvedValue({
      data: [
        device({
          id: 7,
          short_code: "0826",
          is_bound: true,
          current_patient_name: "王*",
        }),
        device({
          id: 8,
          short_code: "1002",
          external_device_id: "device-002",
          is_bound: true,
          current_patient_name: null,
        }),
        device({
          id: 9,
          short_code: "1003",
          external_device_id: "device-003",
          is_bound: false,
        }),
      ],
    });
    renderPage();

    expect(await screen.findByText("已绑定（无访问权限）")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "设备绑定状态" }));
    fireEvent.click(await screen.findByText("已绑定"));

    await waitFor(() => {
      expect(screen.getByText("0826")).toBeInTheDocument();
      expect(screen.getByText("1002")).toBeInTheDocument();
      expect(screen.queryByText("1003")).not.toBeInTheDocument();
    });
  });

  it("通信测试成功后展示安全结果摘要", async () => {
    mockGet.mockResolvedValue({
      data: [device({ last_communication_at: "2026-07-24T02:00:00Z" })],
    });
    mockPost.mockResolvedValue({
      data: {
        device_id: 7,
        model: "M1",
        online: true,
        battery_level: 82,
        last_communication_at: "2026-07-24T02:00:00Z",
        capabilities: { ring: false },
      },
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "通信测试" }));

    expect(await screen.findByText("设备通信正常")).toBeInTheDocument();
    expect(
      screen.getByText((content) =>
        content.includes("最近通信：") && content.includes("电量：82%"),
      ),
    ).toBeInTheDocument();
  });

  it("通信测试失败展示 Warning 反馈且停用设备禁止测试", async () => {
    mockGet.mockResolvedValue({
      data: [
        device(),
        device({
          id: 8,
          short_code: "1008",
          external_device_id: "device-008",
          enabled: false,
        }),
      ],
    });
    mockPost.mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: "厂商暂时不可用。" } },
    });
    renderPage();

    const disabledCode = await screen.findByText("1008");
    const disabledRow = disabledCode.closest("tr");
    expect(disabledRow).not.toBeNull();
    expect(within(disabledRow!).getByRole("button", { name: "通信测试" })).toBeDisabled();

    const activeRow = screen.getByText("0826").closest("tr");
    expect(activeRow).not.toBeNull();
    fireEvent.click(within(activeRow!).getByRole("button", { name: "通信测试" }));

    expect(await screen.findByText("厂商暂时不可用。")).toBeInTheDocument();
  });
});
