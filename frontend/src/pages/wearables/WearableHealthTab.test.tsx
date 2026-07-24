import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WearableHealthTab } from "./WearableHealthTab";

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

vi.mock("@ant-design/charts", () => ({
  DualAxes: () => <div data-testid="wearable-chart" />,
  Line: () => <div data-testid="wearable-chart" />,
}));

const capabilities = {
  ring: false,
  measure_heart_rate: true,
  measure_blood_pressure: true,
  measure_blood_oxygen: true,
  configure_heart_rate_interval: false,
  configure_blood_pressure_interval: false,
  configure_blood_oxygen_interval: false,
  configure_step_switch: false,
};

function renderTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <WearableHealthTab patientId={201} projectPatientId={9001} />
    </QueryClientProvider>,
  );
}

describe("WearableHealthTab", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            device_id: 7,
            model: "M1",
            device_short_code: "0826",
            capabilities,
            last_sync_at: "2026-07-24T02:00:00Z",
            metrics: [],
          },
        });
      }
      if (url.includes("measurements")) return Promise.resolve({ data: { items: [] } });
      if (url.includes("daily-summaries")) return Promise.resolve({ data: { items: [{ record_date: "2026-07-23", steps: 6000 }] } });
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    mockPost.mockResolvedValue({ data: { status: "queued" } });
  });

  afterEach(() => cleanup());

  it("加载绑定摘要、健康筛选、趋势和日汇总，且不自动发起通信测试", async () => {
    renderTab();

    expect(await screen.findByText("设备 0826")).toBeInTheDocument();
    expect(screen.getByTitle("心率")).toBeInTheDocument();
    expect(screen.getByTitle("原始")).toBeInTheDocument();
    expect(screen.getByText("日汇总")).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(
      "/wearables/patients/201/measurements/",
      expect.objectContaining({ params: expect.objectContaining({ project_patient: 9001, metric_type: "heart_rate", bucket: "raw" }) }),
    ));
  });

  it("步数只展示日总量并隐藏日内间隔与主动测量", async () => {
    renderTab();
    await screen.findByText("设备 0826");
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "健康指标" }));
    fireEvent.click(await screen.findByTitle("步数"));

    expect(screen.queryByLabelText("图表间隔")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "主动测量" })).not.toBeInTheDocument();
    expect(await screen.findByText("6000")).toBeInTheDocument();
  });

  it("未绑定时显示绑定引导且不显示主动测量", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) return Promise.resolve({ data: { is_bound: false, metrics: [] } });
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    renderTab();

    expect(await screen.findByText("请先在患者接入中绑定穿戴设备。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "主动测量" })).not.toBeInTheDocument();
  });

  it("未验证型号会禁用主动测量并说明原因", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({
          data: {
            is_bound: true,
            device_id: 7,
            model: "UNKNOWN",
            device_short_code: "0826",
            capabilities: { ...capabilities, measure_heart_rate: false },
            last_sync_at: null,
            metrics: [],
          },
        });
      }
      if (url.includes("measurements") || url.includes("daily-summaries")) return Promise.resolve({ data: { items: [] } });
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    renderTab();

    expect(await screen.findByText("该型号能力尚未验证")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "主动测量" })).toBeDisabled();
  });
});
