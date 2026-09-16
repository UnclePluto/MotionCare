import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { TrainingHistoryPanel } from "./TrainingHistoryPanel";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../../api/client", () => ({ apiClient: { get: (...args: unknown[]) => get(...args) } }));
afterEach(() => { cleanup(); get.mockReset(); });

it("医生打开作废历史后查看原因与保留的分析结果", async () => {
  get.mockResolvedValue({ data: [{ id: 9, action_name: "坐站转移", training_date: "2026-09-15", invalidated_at: "2026-09-16T08:00:00+08:00", invalidation_reason: "运动处方已切换按组计数，旧模式训练仅保留历史备查", cutover_marker: "marker", video_id: null, motion_total_count: 12, motion_standard_count: 10, motion_nonstandard_count: 2 }] });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><TrainingHistoryPanel projectPatientId={1} /></QueryClientProvider>);
  fireEvent.click(screen.getByRole("button", { name: "查看作废训练历史" }));
  expect(await screen.findByText("坐站转移")).toBeInTheDocument();
  expect(screen.getByText("运动处方已切换按组计数，旧模式训练仅保留历史备查")).toBeInTheDocument();
  expect(screen.getByText("12 / 10 / 2")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "保存训练结果" })).not.toBeInTheDocument();
});

it("按需打开历史原始视频并显示分析状态", async () => {
  get.mockImplementation(async (url: string) => ({ data: url === "/training/history/" ? [{ id: 9, action_name: "坐站转移", training_date: "2026-09-15", invalidated_at: "2026-09-16T08:00:00+08:00", invalidation_reason: "按组切换", cutover_marker: "marker", video_id: 19, motion_total_count: null, motion_standard_count: null, motion_nonstandard_count: null }] : url.includes("download-url") ? { url: "https://example.com/private.mp4" } : { status: "pending", skeleton_available: false } }));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><TrainingHistoryPanel projectPatientId={1} /></QueryClientProvider>);
  fireEvent.click(screen.getByRole("button", { name: "查看作废训练历史" }));
  fireEvent.click(await screen.findByRole("button", { name: "查看历史录像" }));
  expect(await screen.findByText("待分析")).toBeInTheDocument();
  expect(await screen.findByLabelText("历史训练原始视频")).toHaveAttribute("src", "https://example.com/private.mp4");
  fireEvent.click(screen.getByRole("button", { name: "关闭历史录像" }));
  expect(screen.queryByLabelText("历史训练原始视频")).not.toBeInTheDocument();
});
