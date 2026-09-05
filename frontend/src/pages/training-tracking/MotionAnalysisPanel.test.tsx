import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MotionAnalysisPanel } from "./MotionAnalysisPanel";
import type { TrackingRecentRecord } from "./types";

const { mockPatch } = vi.hoisted(() => ({ mockPatch: vi.fn() }));

vi.mock("../../api/client", () => ({
  apiClient: {
    patch: (...args: unknown[]) => mockPatch(...args),
  },
}));

function record(overrides: Partial<TrackingRecentRecord> = {}): TrackingRecentRecord {
  return {
    id: 7000,
    training_date: "2026-05-14",
    status: "completed",
    prescription: 501,
    prescription_version: 3,
    prescription_action: 1000,
    action_name: "肩部推举",
    action_source_key: "motion-resistance-shoulder-press",
    analysis_available: true,
    internal_type: "motion",
    action_type: "抗阻训练",
    actual_duration_minutes: 15,
    score: null,
    game_accuracy_rate: null,
    game_error_count: null,
    game_difficulty: null,
    game_ended_early: null,
    game_difficulty_adjust_reason: null,
    game_upload_mode: null,
    game_retry_count: null,
    game_total_retry_count: null,
    note: "",
    video_id: 8101,
    video_status: "attached",
    training_started_at: null,
    training_ended_at: null,
    motion_total_count: null,
    motion_standard_count: null,
    motion_nonstandard_count: null,
    motion_quality_data: {},
    motion_result_source: "",
    motion_result_updated_by: null,
    motion_result_updated_at: null,
    analysis_status: "failed",
    analysis_failure_message: "自动分析未完成，请填写训练结果",
    skeleton_available: false,
    ...overrides,
  };
}

function renderPanel(
  value: TrackingRecentRecord,
  onSaved = vi.fn(),
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <MotionAnalysisPanel record={value} onSaved={onSaved} />
    </QueryClientProvider>,
  );
  return {
    invalidateSpy,
    onSaved,
    rerenderRecord: (next: TrackingRecentRecord) => rendered.rerender(
      <QueryClientProvider client={queryClient}>
        <MotionAnalysisPanel record={next} onSaved={onSaved} />
      </QueryClientProvider>,
    ),
  };
}

describe("MotionAnalysisPanel", () => {
  beforeEach(() => mockPatch.mockReset());
  afterEach(cleanup);

  it.each(["pending", "running"] as const)("%s 时只展示等待状态且禁止编辑", (analysisStatus) => {
    renderPanel(record({ analysis_status: analysisStatus }));

    expect(screen.queryByRole("button", { name: /开始|重新分析|重试分析/ })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "总次数" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "保存训练结果" })).toBeDisabled();
    expect(screen.getByText(analysisStatus === "pending" ? /进入自动分析队列/ : /正在分析/)).toBeInTheDocument();
  });

  it.each(["failed", "succeeded", "unsupported"] as const)("%s 时允许医生填写当前结果", (analysisStatus) => {
    renderPanel(record({ analysis_status: analysisStatus }));

    expect(screen.getByRole("textbox", { name: "总次数" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "保存训练结果" })).toBeEnabled();
  });

  it("只展示安全失败文案，不渲染内部错误信息", () => {
    renderPanel(record({ analysis_status: "failed" }));

    expect(screen.getByText("自动分析未完成，请填写训练结果")).toBeInTheDocument();
    expect(screen.queryByText(/Traceback|raw\.mp4|token=/)).not.toBeInTheDocument();
  });

  it("在前端明确校验总次数守恒", async () => {
    renderPanel(record());

    fireEvent.change(screen.getByRole("textbox", { name: "总次数" }), { target: { value: "90" } });
    fireEvent.change(screen.getByRole("textbox", { name: "标准次数" }), { target: { value: "70" } });
    fireEvent.change(screen.getByRole("textbox", { name: "不标准次数" }), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "保存训练结果" }));

    expect(await screen.findByText("总次数必须等于标准次数与不标准次数之和")).toBeInTheDocument();
    expect(mockPatch).not.toHaveBeenCalled();
  });

  it.each(["1e3", " 1", "1 ", "-0", "+1", "01", "1.5", "-1", "中文", "2147483648"])("拒绝非法原始文本 %s 且 blur 后不静默改值", async (invalidValue) => {
    renderPanel(record());

    const total = screen.getByRole("textbox", { name: "总次数" });
    fireEvent.paste(total, { clipboardData: { getData: () => invalidValue } });
    fireEvent.input(total, { target: { value: invalidValue } });
    fireEvent.blur(total);
    fireEvent.change(screen.getByRole("textbox", { name: "标准次数" }), { target: { value: "0" } });
    fireEvent.change(screen.getByRole("textbox", { name: "不标准次数" }), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "保存训练结果" }));

    expect(await screen.findByText("请输入 0 至 2147483647 之间的整数")).toBeInTheDocument();
    expect(total).toHaveValue(invalidValue);
    expect(mockPatch).not.toHaveBeenCalled();
  });

  it("空计数显示必填错误且保留其它输入", async () => {
    renderPanel(record());
    fireEvent.change(screen.getByRole("textbox", { name: "标准次数" }), { target: { value: "0" } });
    fireEvent.change(screen.getByRole("textbox", { name: "不标准次数" }), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "保存训练结果" }));

    expect(await screen.findByText("请输入总次数")).toBeInTheDocument();
    expect(mockPatch).not.toHaveBeenCalled();
  });

  it("非有限输入显示明确错误且不提交", async () => {
    renderPanel(record());
    fireEvent.change(screen.getByRole("textbox", { name: "总次数" }), { target: { value: "Infinity" } });
    fireEvent.change(screen.getByRole("textbox", { name: "标准次数" }), { target: { value: "0" } });
    fireEvent.change(screen.getByRole("textbox", { name: "不标准次数" }), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "保存训练结果" }));

    expect(await screen.findByText(/请输入总次数|请输入 0 至 2147483647 之间的整数/)).toBeInTheDocument();
    expect(mockPatch).not.toHaveBeenCalled();
  });

  it("接受 int4 上界且不改变数值", async () => {
    mockPatch.mockResolvedValue({ data: {} });
    renderPanel(record());
    fireEvent.change(screen.getByRole("textbox", { name: "总次数" }), { target: { value: "2147483647" } });
    fireEvent.change(screen.getByRole("textbox", { name: "标准次数" }), { target: { value: "2147483647" } });
    fireEvent.change(screen.getByRole("textbox", { name: "不标准次数" }), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "保存训练结果" }));

    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith(
      "/training/7000/motion-result/",
      expect.objectContaining({ total_count: 2147483647, standard_count: 2147483647, nonstandard_count: 0 }),
    ));
  });

  it("保存时只提交四个允许字段，刷新两类查询并显示医生修正状态", async () => {
    mockPatch.mockResolvedValue({ data: {} });
    const onSaved = vi.fn();
    const { invalidateSpy } = renderPanel(record(), onSaved);

    fireEvent.change(screen.getByRole("textbox", { name: "总次数" }), { target: { value: "90" } });
    fireEvent.change(screen.getByRole("textbox", { name: "标准次数" }), { target: { value: "72" } });
    fireEvent.change(screen.getByRole("textbox", { name: "不标准次数" }), { target: { value: "18" } });
    fireEvent.change(screen.getByRole("textbox", { name: "质量备注" }), {
      target: { value: "动作基本稳定" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存训练结果" }));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith("/training/7000/motion-result/", {
        total_count: 90,
        standard_count: 72,
        nonstandard_count: 18,
        quality_note: "动作基本稳定",
      });
    });
    expect(await screen.findByText("医生已修正")).toBeInTheDocument();
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["training-tracking"] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["latest-analysis", 8101] });
  });

  it("保存失败时使用固定文案，不泄露后端敏感详情", async () => {
    mockPatch
      .mockRejectedValueOnce(new Error("token=secret /tmp/video.mp4"))
      .mockResolvedValue({ data: {} });
    renderPanel(record({ motion_total_count: 90, motion_standard_count: 72, motion_nonstandard_count: 18 }));

    fireEvent.click(screen.getByRole("button", { name: "保存训练结果" }));

    expect(await screen.findByText("网络连接异常，输入已保留，请重试保存")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "保存训练结果" })).toBeEnabled());
    expect(mockPatch).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/token=secret|video\.mp4/)).not.toBeInTheDocument();
  });

  it.each([
    [400, "输入内容未通过校验，请检查后重试", false],
    [401, "登录状态已失效，请重新登录后再修改", true],
    [403, "当前账号无权修改这条训练记录", true],
    [409, "分析状态已变化，系统正在分析视频，请等待完成", true],
    [404, "训练记录已不可用，请刷新页面后重新选择", true],
  ] as const)("PATCH %s 使用安全分支文案并按需禁止编辑", async (status, message, disabled) => {
    mockPatch
      .mockRejectedValueOnce({ response: { status, data: { detail: "token=secret /tmp/raw.mp4" } } })
      .mockResolvedValue({ data: {} });
    const { invalidateSpy } = renderPanel(record({
      motion_total_count: 90,
      motion_standard_count: 72,
      motion_nonstandard_count: 18,
      motion_result_source: "doctor",
    }));

    fireEvent.click(screen.getByRole("button", { name: "保存训练结果" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByText("医生已修正")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存训练结果" })).toHaveProperty("disabled", disabled);
    expect(screen.queryByText(/token=secret|raw\.mp4/)).not.toBeInTheDocument();
    if (status === 409 || status === 404) {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["training-tracking"] });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["latest-analysis", 8101] });
    }
  });

  it("网络错误保留医生来源和输入并允许重试", async () => {
    mockPatch
      .mockRejectedValueOnce(new Error("Network Error token=secret"))
      .mockResolvedValue({ data: {} });
    renderPanel(record({
      motion_total_count: 90,
      motion_standard_count: 72,
      motion_nonstandard_count: 18,
      motion_result_source: "doctor",
    }));

    fireEvent.change(screen.getByRole("textbox", { name: "总次数" }), { target: { value: "91" } });
    fireEvent.change(screen.getByRole("textbox", { name: "标准次数" }), { target: { value: "73" } });
    fireEvent.click(screen.getByRole("button", { name: "保存训练结果" }));

    expect(await screen.findByText("网络连接异常，输入已保留，请重试保存")).toBeInTheDocument();
    expect(screen.getByText("医生已修正")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "总次数" })).toHaveValue("91");
    expect(screen.getByRole("button", { name: "保存训练结果" })).toBeEnabled();
  });

  it("旧记录 PATCH 晚返回时不会污染新记录状态或触发成功副作用", async () => {
    let resolveOld: (() => void) | undefined;
    mockPatch.mockReturnValue(new Promise((resolve) => { resolveOld = () => resolve({ data: {} }); }));
    const onSaved = vi.fn();
    const { invalidateSpy, rerenderRecord } = renderPanel(record({
      motion_total_count: 10,
      motion_standard_count: 8,
      motion_nonstandard_count: 2,
    }), onSaved);
    fireEvent.click(screen.getByRole("button", { name: "保存训练结果" }));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledTimes(1));

    rerenderRecord(record({
      id: 7004,
      video_id: 8103,
      motion_total_count: 20,
      motion_standard_count: 15,
      motion_nonstandard_count: 5,
      motion_result_source: "",
    }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "总次数" })).toHaveValue("20"));
    resolveOld?.();

    await Promise.resolve();
    expect(screen.queryByText("医生已修正")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /保存训练结果/ })).not.toHaveClass("ant-btn-loading");
    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("面板卸载后 PATCH 晚返回不会刷新查询或触发成功回调", async () => {
    let resolveOld: (() => void) | undefined;
    mockPatch.mockReturnValue(new Promise((resolve) => { resolveOld = () => resolve({ data: {} }); }));
    const onSaved = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const rendered = render(
      <QueryClientProvider client={queryClient}>
        <MotionAnalysisPanel record={record({
          motion_total_count: 10,
          motion_standard_count: 8,
          motion_nonstandard_count: 2,
        })} onSaved={onSaved} />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "保存训练结果" }));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledTimes(1));

    rendered.unmount();
    resolveOld?.();
    await Promise.resolve();

    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });
});
