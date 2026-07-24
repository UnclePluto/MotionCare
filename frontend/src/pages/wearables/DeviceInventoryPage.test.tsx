import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DeviceInventoryPage } from "./DeviceInventoryPage";

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

describe("DeviceInventoryPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockResolvedValue({ data: [] });
  });

  afterEach(() => cleanup());

  it("录入设备后保留固定四位简码的前导零", async () => {
    mockPost.mockResolvedValue({
      data: {
        id: 7,
        provider: "miwitracker",
        external_device_id: "device-001",
        identifier_type: "device_id",
        model: "M1",
        short_code: "0826",
        enabled: true,
        last_communication_at: null,
      },
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
});
