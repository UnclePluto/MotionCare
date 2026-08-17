import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

  it("只填写十五位IMEI即可录入并展示系统固定简码", async () => {
    mockPost.mockResolvedValue({
      data: device({ external_device_id: "860123456789012", identifier_type: "imei" }),
    });
    renderPage();

    expect(await screen.findByText("设备管理")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "新增设备" }));
    expect(screen.queryByLabelText("厂商")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("标识类型")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("设备型号")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("IMEI"), {
      target: { value: "860123456789012" },
    });
    fireEvent.click(screen.getByRole("button", { name: "录入设备" }));

    expect(await screen.findByText("0826")).toBeInTheDocument();
    expect(screen.getByText("860123456789012")).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith("/wearables/devices/", {
      imei: "860123456789012",
    });
  });

  it("拒绝非十五位数字IMEI", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "新增设备" }));
    fireEvent.change(screen.getByLabelText("IMEI"), { target: { value: "1234A" } });
    fireEvent.click(screen.getByRole("button", { name: "录入设备" }));

    expect(await screen.findByText("IMEI 必须是 15 位数字")).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("允许粘贴带首尾空格的十五位 IMEI 并按去空格值提交", async () => {
    mockPost.mockResolvedValue({
      data: device({ external_device_id: "860123456789012", identifier_type: "imei" }),
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "新增设备" }));
    const imeiInput = screen.getByLabelText("IMEI");

    expect(imeiInput).not.toHaveAttribute("maxLength");
    fireEvent.change(imeiInput, { target: { value: " 860123456789012 " } });
    fireEvent.click(screen.getByRole("button", { name: "录入设备" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/wearables/devices/", {
        imei: "860123456789012",
      });
    });
    expect(screen.queryByText("IMEI 必须是 15 位数字")).not.toBeInTheDocument();
  });

  it("历史非 IMEI 标识在 IMEI 列显示为空", async () => {
    mockGet.mockResolvedValue({
      data: [device({ external_device_id: "legacy-device-001", identifier_type: "device_id" })],
    });
    renderPage();

    const row = (await screen.findByText("0826")).closest("tr");
    expect(row).not.toBeNull();
    expect(row!.querySelectorAll("td")[1]).toHaveTextContent("—");
    expect(screen.queryByText("legacy-device-001")).not.toBeInTheDocument();
  });

  it("设备列表加载失败时展示固定提示", async () => {
    mockGet.mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: "服务暂时不可用。" } },
    });
    renderPage();

    expect(await screen.findByText("设备管理加载失败")).toBeInTheDocument();
    expect(screen.queryByText("服务暂时不可用。")).not.toBeInTheDocument();
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

    expect(await screen.findByText("设备 0826 通信正常")).toBeInTheDocument();
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

    expect(await screen.findByText("设备 0826 通信测试失败")).toBeInTheDocument();
    expect(await screen.findByText("厂商暂时不可用。")).toBeInTheDocument();
  });

  it("连续测试两台设备时忽略前一台迟到的成功结果", async () => {
    let resolveFirst!: (value: { data: WearableStatus }) => void;
    const firstStatus = new Promise<{ data: WearableStatus }>((resolve) => {
      resolveFirst = resolve;
    });
    mockGet.mockResolvedValue({
      data: [
        device(),
        device({
          id: 8,
          short_code: "1002",
          external_device_id: "device-002",
        }),
      ],
    });
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/devices/7/check-status/") return firstStatus;
      if (url === "/wearables/devices/8/check-status/") {
        return Promise.resolve({
          data: {
            device_id: 8,
            model: "M2",
            online: false,
            battery_level: 21,
            last_communication_at: null,
            capabilities: { ring: false },
          },
        });
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    renderPage();

    const firstRow = (await screen.findByText("0826")).closest("tr");
    const secondRow = screen.getByText("1002").closest("tr");
    expect(firstRow).not.toBeNull();
    expect(secondRow).not.toBeNull();
    fireEvent.click(within(firstRow!).getByRole("button", { name: "通信测试" }));
    fireEvent.click(within(secondRow!).getByRole("button", { name: "通信测试" }));

    expect(await screen.findByText(/设备.*通信异常/)).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("电量：21%"))).toBeInTheDocument();

    await act(async () => {
      resolveFirst({
        data: {
          device_id: 7,
          model: "M1",
          online: true,
          battery_level: 82,
          last_communication_at: "2026-07-24T02:00:00Z",
          capabilities: { ring: false },
        },
      });
      await firstStatus;
    });

    expect(screen.getByText("设备 1002 通信异常")).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes("电量：21%"))).toBeInTheDocument();
    expect(screen.queryByText("设备 0826 通信正常")).not.toBeInTheDocument();
  });

  it("连续测试两台设备时忽略前一台迟到的失败结果", async () => {
    let rejectFirst!: (reason: unknown) => void;
    const firstStatus = new Promise<{ data: WearableStatus }>((_resolve, reject) => {
      rejectFirst = reject;
    });
    mockGet.mockResolvedValue({
      data: [
        device(),
        device({
          id: 8,
          short_code: "1002",
          external_device_id: "device-002",
        }),
      ],
    });
    mockPost.mockImplementation((url: string) => {
      if (url === "/wearables/devices/7/check-status/") return firstStatus;
      if (url === "/wearables/devices/8/check-status/") {
        return Promise.resolve({
          data: {
            device_id: 8,
            model: "M2",
            online: true,
            battery_level: 66,
            last_communication_at: "2026-07-24T03:00:00Z",
            capabilities: { ring: false },
          },
        });
      }
      return Promise.reject(new Error(`unexpected POST ${url}`));
    });
    renderPage();

    const firstRow = (await screen.findByText("0826")).closest("tr");
    const secondRow = screen.getByText("1002").closest("tr");
    expect(firstRow).not.toBeNull();
    expect(secondRow).not.toBeNull();
    fireEvent.click(within(firstRow!).getByRole("button", { name: "通信测试" }));
    fireEvent.click(within(secondRow!).getByRole("button", { name: "通信测试" }));
    expect(await screen.findByText(/设备.*通信正常/)).toBeInTheDocument();

    await act(async () => {
      rejectFirst({
        isAxiosError: true,
        response: { data: { detail: "前一台设备通信失败。" } },
      });
      try {
        await firstStatus;
      } catch {
        // mutation 会消费该失败；这里仅等待迟到请求完成。
      }
    });

    expect(screen.getByText("设备 1002 通信正常")).toBeInTheDocument();
    expect(screen.queryByText("前一台设备通信失败。")).not.toBeInTheDocument();
  });

  it("响铃按钮调用设备响铃接口", async () => {
    mockGet.mockResolvedValue({ data: [device()] });
    mockPost.mockResolvedValue({ data: {} });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "响铃" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/wearables/devices/7/ring/");
    });
  });
});
