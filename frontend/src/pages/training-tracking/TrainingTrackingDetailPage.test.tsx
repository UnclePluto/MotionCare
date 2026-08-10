import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TrainingTrackingDetailPage } from "./TrainingTrackingDetailPage";
import type {
  TrackingDetail,
  TrainingVideoWearableWindowResponse,
} from "./types";

const { mockGet, mockPost, mockDualAxesProps } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDualAxesProps: [] as Array<Record<string, unknown>>,
}));

type TooltipConfig = {
  channel: string;
  name: string;
  valueFormatter: (value: number) => string;
};

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

vi.mock("@ant-design/charts", () => ({
  DualAxes: (props: Record<string, unknown>) => {
    mockDualAxesProps.push(props);
    return (
      <pre data-testid="dual-axes-chart">
        {JSON.stringify(props, (_key, value) => (typeof value === "function" ? "[function]" : value))}
      </pre>
    );
  },
  Line: (props: Record<string, unknown>) => (
    <pre data-testid="line-chart">{JSON.stringify(props, (_key, value) => (typeof value === "function" ? "[function]" : value))}</pre>
  ),
}));

vi.mock("../wearables/WearableHealthTab", () => ({
  WearableHealthTab: ({ patientId, projectPatientId }: { patientId: number; projectPatientId: number }) => (
    <div>穿戴健康面板：{patientId}/{projectPatientId}</div>
  ),
}));

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const rendered = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/training-tracking/patients/:patientId" element={<TrainingTrackingDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...rendered, queryClient: qc };
}

function RouteSwitcher() {
  const navigate = useNavigate();
  return (
    <>
      <button type="button" onClick={() => navigate("/training-tracking/patients/202")}>
        切换患者
      </button>
      <Routes>
        <Route path="/training-tracking/patients/:patientId" element={<TrainingTrackingDetailPage />} />
      </Routes>
    </>
  );
}

function renderWithRouteSwitcher(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <RouteSwitcher />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const trackingDetail = {
  patient: {
    id: 201,
    name: "训练患者甲",
    phone_masked: "138****0201",
  },
  project_patients: [
    {
      id: 9001,
      project: 1,
      project_name: "研究项目 A",
      project_status: "active",
      group: 10,
      group_name: "试验组",
      enrolled_at: "2026-05-01T09:00:00+08:00",
      project_completed_at: "2026-06-01T09:00:00+08:00",
    },
    {
      id: 9002,
      project: 2,
      project_name: "研究项目 B",
      project_status: "active",
      group: 20,
      group_name: "对照组",
      enrolled_at: "2026-05-02T09:00:00+08:00",
      project_completed_at: null,
    },
  ],
  selected_project_patient: {
    id: 9001,
    project: 1,
    project_name: "研究项目 A",
    project_status: "active",
    group: 10,
    group_name: "试验组",
    enrolled_at: "2026-05-01T09:00:00+08:00",
    project_completed_at: "2026-06-01T09:00:00+08:00",
  },
  current_prescription: {
    id: 501,
    version: 3,
    status: "active",
    effective_at: "2026-05-03T10:00:00+08:00",
  },
  prescription_completion: [
    {
      prescription_action: 1001,
      action_name: "坐站转移训练",
      internal_type: "motion",
      action_type: "下肢训练",
      target_count: 16,
      completed_count: 12,
      completion_rate: 75,
      recent_record_at: "2026-05-14",
    },
  ],
  trend: {
    daily: [
      { date: "2026-05-13", completed_count: 1, duration_minutes: 20, game_average_score: 86 },
      { date: "2026-05-14", completed_count: 2, duration_minutes: 35, game_average_score: 92 },
    ],
    moving_average: [
      { date: "2026-05-13", completed_count_avg: 0.7, duration_minutes_avg: 18 },
      { date: "2026-05-14", completed_count_avg: 1.1, duration_minutes_avg: 23 },
    ],
    weekly: [
      {
        week_start: "2026-05-11",
        week_end: "2026-05-17",
        completed_count: 5,
        duration_minutes: 120,
        game_average_score: 88.5,
      },
    ],
  },
  game_summary: {
    average_score: 88.5,
    average_accuracy_rate: 91,
    total_error_count: 6,
    by_game: [
      {
        prescription_action: 1002,
        action_name: "认知卡片",
        record_count: 4,
        average_score: 88.5,
        average_accuracy_rate: 91,
        recent_record_at: "2026-05-14",
      },
    ],
  },
  pending_training_videos: [
    {
      id: 9101,
      training_date: "2026-05-14",
      action_name: "肩部推举",
      status: "queued",
      failure_reason: "",
      created_at: "2026-05-14T08:00:00+08:00",
    },
    {
      id: 9102,
      training_date: "2026-05-14",
      action_name: "肩部推举",
      status: "assembling",
      failure_reason: "",
      created_at: "2026-05-14T08:01:00+08:00",
    },
    {
      id: 9103,
      training_date: "2026-05-14",
      action_name: "肩部推举",
      status: "uploading_qiniu",
      failure_reason: "",
      created_at: "2026-05-14T08:02:00+08:00",
    },
    {
      id: 9104,
      training_date: "2026-05-14",
      action_name: "肩部推举",
      status: "failed",
      failure_reason: "视频合并失败，请重新上传",
      created_at: "2026-05-14T08:03:00+08:00",
    },
  ],
  recent_records: [
    {
      id: 7000,
      training_date: "2026-05-14",
      prescription: 501,
      prescription_version: 3,
      prescription_action: 1000,
      action_name: "肩部推举",
      action_source_key: "motion-resistance-shoulder-press",
      internal_type: "motion",
      action_type: "抗阻训练",
      status: "completed",
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
      note: "肩推视频已上传",
      video_id: 8101,
      video_status: "attached",
      training_started_at: "2026-08-06T01:32:14Z",
      training_ended_at: "2026-08-06T01:41:27Z",
      latest_analysis_status: null,
      analysis_total_count: null,
      analysis_standard_count: null,
      analysis_nonstandard_count: null,
    },
    {
      id: 7001,
      training_date: "2026-05-14",
      prescription: 501,
      prescription_version: 3,
      prescription_action: 1001,
      action_name: "坐站转移训练",
      action_source_key: "motion-balance-sit-stand",
      internal_type: "game",
      action_type: "认知训练",
      status: "completed",
      actual_duration_minutes: 18,
      score: 92,
      game_accuracy_rate: 95,
      game_error_count: 1,
      game_difficulty: "中",
      game_ended_early: true,
      game_difficulty_adjust_reason: "今天状态不佳",
      game_upload_mode: "retry",
      game_retry_count: 2,
      game_total_retry_count: 12,
      note: "完成顺利",
      video_id: null,
      video_status: null,
      training_started_at: null,
      training_ended_at: null,
      latest_analysis_status: null,
      analysis_total_count: null,
      analysis_standard_count: null,
      analysis_nonstandard_count: null,
    },
    {
      id: 7002,
      training_date: "2026-05-13",
      prescription: 501,
      prescription_version: 3,
      prescription_action: 1002,
      action_name: "旧游戏记录",
      action_source_key: null,
      internal_type: "game",
      action_type: "认知训练",
      status: "completed",
      actual_duration_minutes: 10,
      score: 80,
      game_accuracy_rate: 90,
      game_error_count: 2,
      game_difficulty: "易",
      game_ended_early: null,
      game_difficulty_adjust_reason: null,
      game_upload_mode: null,
      game_retry_count: null,
      game_total_retry_count: null,
      note: "旧版明细缺失",
      video_id: null,
      video_status: null,
      training_started_at: null,
      training_ended_at: null,
      latest_analysis_status: null,
      analysis_total_count: null,
      analysis_standard_count: null,
      analysis_nonstandard_count: null,
    },
    {
      id: 7003,
      training_date: "2026-05-13",
      prescription: 501,
      prescription_version: 3,
      prescription_action: 1003,
      action_name: "坐站训练",
      action_source_key: "motion-balance-sit-stand",
      internal_type: "motion",
      action_type: "下肢训练",
      status: "completed",
      actual_duration_minutes: 12,
      score: null,
      game_accuracy_rate: null,
      game_error_count: null,
      game_difficulty: null,
      game_ended_early: true,
      game_difficulty_adjust_reason: "不应展示",
      game_upload_mode: "retry",
      game_retry_count: 8,
      game_total_retry_count: 88,
      note: "非游戏记录",
      video_id: 8102,
      video_status: "attached",
      training_started_at: null,
      training_ended_at: null,
      latest_analysis_status: null,
      analysis_total_count: null,
      analysis_standard_count: null,
      analysis_nonstandard_count: null,
    },
  ],
};

function chartProps() {
  return screen.getAllByTestId("dual-axes-chart").map((node) => JSON.parse(node.textContent ?? "{}") as { data?: unknown[] });
}

function trendChartData() {
  const chart = chartProps().find((props) => {
    const first = Array.isArray(props.data) ? (props.data[0] as Record<string, unknown> | undefined) : undefined;
    return typeof first?.label === "string";
  });
  return (chart?.data ?? []) as Array<Record<string, unknown>>;
}

function cloneTrackingDetail(): TrackingDetail {
  return JSON.parse(JSON.stringify(trackingDetail)) as TrackingDetail;
}

const wearableWindowResponse: TrainingVideoWearableWindowResponse = {
  available: true,
  window_started_at: "2026-08-06T01:32:14Z",
  window_ended_at: "2026-08-06T01:40:14Z",
  expected_duration_seconds: 180,
  buffer_seconds: 300,
  metrics: {
    heart_rate: {
      points: [{ measured_at: "2026-08-06T01:33:00Z", value: 86 }],
      statistics: { average: 86, maximum: 86, minimum: 86, count: 1 },
    },
  },
};

function videoDrawerGet(
  url: string,
  wearableResult: TrainingVideoWearableWindowResponse | Error =
    wearableWindowResponse,
  detail: TrackingDetail = trackingDetail as TrackingDetail,
) {
  if (url === "/training/tracking/patients/201/") {
    return Promise.resolve({ data: detail });
  }
  if (url === "/training/videos/8101/download-url/") {
    return Promise.resolve({ data: { url: "https://cdn.example.com/video.mp4" } });
  }
  if (url === "/training/videos/8101/analysis-jobs/latest/") {
    return Promise.resolve({ data: null });
  }
  if (url === "/training/videos/8101/wearable-window/") {
    return wearableResult instanceof Error
      ? Promise.reject(wearableResult)
      : Promise.resolve({ data: wearableResult });
  }
  return Promise.reject(new Error(`unexpected GET ${url}`));
}

async function waitForWearableQueryToSettle(
  queryClient: QueryClient,
  status: "success" | "error",
) {
  await waitFor(() => {
    expect(
      queryClient.getQueryState([
        "training-video-wearable-window",
        8101,
      ]),
    ).toMatchObject({ status, fetchStatus: "idle" });
  });
}

describe("TrainingTrackingDetailPage", () => {
  beforeEach(() => {
    mockDualAxesProps.length = 0;
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url === "/training/tracking/patients/201/") {
        return Promise.resolve({ data: trackingDetail });
      }
      if (url === "/training/videos/8101/analysis-jobs/latest/") {
        return Promise.resolve({ data: null });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it("展示项目下拉、当前处方、完成率、趋势图、游戏摘要和最近记录", async () => {
    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "训练跟踪" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "穿戴健康" })).toBeInTheDocument();
    expect(screen.queryByText("设备在线")).not.toBeInTheDocument();
    expect(screen.getByText(/研究周期：2026-05-01 至 2026-06-01/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "切换项目" })).toBeInTheDocument();
    expect(screen.getAllByText("研究项目 A").length).toBeGreaterThan(0);
    expect(screen.getByText("试验组")).toBeInTheDocument();
    expect(screen.getByText("当前处方 v3")).toBeInTheDocument();
    expect(screen.getAllByText("坐站转移训练").length).toBeGreaterThan(0);
    expect(screen.getAllByText("16").length).toBeGreaterThan(0);
    expect(screen.getAllByText("75%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2026-05-14").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("dual-axes-chart").length).toBeGreaterThan(0);
    expect(screen.getAllByText("平均得分").length).toBeGreaterThan(0);
    expect(screen.getAllByText("88.5").length).toBeGreaterThan(0);
    expect(screen.getAllByText("平均正确率").length).toBeGreaterThan(0);
    expect(screen.getAllByText("91%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("总错误次数").length).toBeGreaterThan(0);
    expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    expect(screen.getAllByText("认知卡片").length).toBeGreaterThan(0);
    expect(screen.getAllByText("4").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2026-05-14").length).toBeGreaterThan(0);
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(screen.getByText("中")).toBeInTheDocument();
    expect(screen.getByText("提前结束")).toBeInTheDocument();
    expect(screen.getByText("补传")).toBeInTheDocument();
    expect(screen.getByText("12 次")).toBeInTheDocument();
    expect(screen.getByText("今天状态不佳")).toBeInTheDocument();
    expect(screen.getByText("完成顺利")).toBeInTheDocument();
    expect(screen.getByText("肩推视频已上传")).toBeInTheDocument();
    expect(screen.queryByText("到时完成")).not.toBeInTheDocument();
    expect(screen.queryByText("88 次")).not.toBeInTheDocument();
    expect(screen.queryByText("不应展示")).not.toBeInTheDocument();
  });

  it("图表悬浮提示使用业务指标名称和格式化数值", async () => {
    renderAt("/training-tracking/patients/201");
    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();

    const configs = mockDualAxesProps.filter((props) => Array.isArray(props.children));
    const completion = configs.find((props) =>
      Array.isArray(props.data) && (props.data[0] as { action_name?: string } | undefined)?.action_name,
    );
    const trend = configs.find((props) =>
      Array.isArray(props.data) && (props.data[0] as { label?: string } | undefined)?.label,
    );
    const completionChildren = completion?.children as Array<{ tooltip: TooltipConfig }>;
    const trendChildren = trend?.children as Array<{ tooltip: TooltipConfig }>;

    expect(trendChildren[0]).not.toHaveProperty("colorField");
    expect(trendChildren[0]).toMatchObject({ style: { fill: "#1677ff" } });
    expect(completionChildren[0]).not.toHaveProperty("colorField");
    expect(completionChildren[0]).toMatchObject({ style: { fill: "#52c41a" } });

    expect(completionChildren[0].tooltip.name).toBe("完成率");
    expect(completionChildren[0].tooltip.valueFormatter(75)).toBe("75%");
    expect(completionChildren[1].tooltip.name).toBe("完成次数");
    expect(completionChildren[1].tooltip.valueFormatter(12)).toBe("12 次");
    expect(trendChildren[0].tooltip.name).toBe("完成次数");
    expect(trendChildren[0].tooltip.valueFormatter(3)).toBe("3 次");
    expect(trendChildren[1].tooltip.name).toBe("7 日移动平均");
    expect(trendChildren[1].tooltip.valueFormatter(1.4)).toBe("1.4 次");

    fireEvent.click(screen.getByText("按周"));

    await waitFor(() => {
      const latestTrend = [...mockDualAxesProps]
        .reverse()
        .find((props) =>
          Array.isArray(props.data) && (props.data[0] as { label?: string } | undefined)?.label,
        );
      const children = latestTrend?.children as Array<{ tooltip: TooltipConfig }>;
      expect(children[1].tooltip.name).toBe("周汇总");
      expect(children[1].tooltip.valueFormatter(3)).toBe("3 次");
    });
  });

  it("可在训练跟踪与穿戴健康页签间切换并保留训练功能", async () => {
    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();
    const trainingTab = screen.getByRole("tab", { name: "训练跟踪" });
    const wearableTab = screen.getByRole("tab", { name: "穿戴健康" });

    expect(trainingTab.closest(".training-health-tabs")).not.toBeNull();
    expect(trainingTab.querySelector(".anticon-line-chart")).not.toBeNull();
    expect(wearableTab.querySelector(".anticon-heart")).not.toBeNull();
    expect(trainingTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("处方完成情况");

    fireEvent.click(wearableTab);
    expect(wearableTab).toHaveAttribute("aria-selected", "true");
    expect(trainingTab).toHaveAttribute("aria-selected", "false");
    expect(await screen.findByText("穿戴健康面板：201/9001")).toBeInTheDocument();
    expect(screen.getByRole("tabpanel")).toHaveTextContent("穿戴健康面板：201/9001");
    expect(screen.queryAllByTestId("dual-axes-chart")).toHaveLength(0);

    fireEvent.click(trainingTab);
    expect(await screen.findByRole("tabpanel")).toHaveTextContent("处方完成情况");
    expect(screen.getAllByTestId("dual-axes-chart")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "播放训练视频" })).toBeInTheDocument();
  });

  it("展示 attached 肩推视频操作，待处理视频只展示状态和安全失败摘要", async () => {
    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "播放训练视频" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "动作分析" })).toBeInTheDocument();
    expect(screen.getAllByText("视频处理中")).toHaveLength(3);
    expect(screen.getByText("视频合并失败，请重新上传")).toBeInTheDocument();
    expect(screen.getByText("非游戏记录")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "播放训练视频" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "动作分析" })).toHaveLength(1);
  });

  it("使用稳定 source_key 判断肩推视频入口而不是动作显示名", async () => {
    const renamedDetail = cloneTrackingDetail();
    renamedDetail.recent_records[0].action_name = "肩推训练改名";
    renamedDetail.recent_records[0].action_source_key = "motion-resistance-shoulder-press";
    renamedDetail.recent_records[3].action_name = "肩部推举";
    renamedDetail.recent_records[3].action_source_key = "motion-balance-sit-stand";
    mockGet.mockImplementation((url: string) => {
      if (url === "/training/tracking/patients/201/") {
        return Promise.resolve({ data: renamedDetail });
      }
      if (url === "/training/videos/8101/download-url/") {
        return Promise.resolve({ data: { url: "https://signed.example.com/video.mp4?token=secret" } });
      }
      if (url === "/training/videos/8101/analysis-jobs/latest/") {
        return Promise.resolve({ data: null });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("肩推训练改名")).toBeInTheDocument();
    expect(screen.getAllByText("肩部推举").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "播放训练视频" })).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "播放训练视频" }));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/videos/8101/download-url/");
    });
    expect(mockGet).not.toHaveBeenCalledWith("/training/videos/8102/download-url/");
  });

  it("latest 动作分析查询失败时展示安全错误和重试按钮", async () => {
    let latestCallCount = 0;
    mockGet.mockImplementation((url: string) => {
      if (url === "/training/tracking/patients/201/") {
        return Promise.resolve({ data: trackingDetail });
      }
      if (url === "/training/videos/8101/download-url/") {
        return Promise.resolve({ data: { url: "https://signed.example.com/video.mp4?token=secret" } });
      }
      if (url === "/training/videos/8101/analysis-jobs/latest/") {
        latestCallCount += 1;
        if (latestCallCount === 1) {
          return Promise.reject({
            response: {
              data: {
                detail: "动作分析失败 access_key=ak-value",
              },
            },
          });
        }
        return Promise.resolve({ data: null });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "动作分析" }));

    expect(await screen.findByText("加载动作分析结果失败")).toBeInTheDocument();
    expect(screen.queryByText(/ak-value/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重试" }));

    await waitFor(() => {
      expect(latestCallCount).toBe(2);
    });
    expect(await screen.findByText("暂无动作分析结果")).toBeInTheDocument();
  });

  it("待处理失败视频摘要使用固定宽度省略并保留完整安全摘要", async () => {
    const detailWithLongFailure = cloneTrackingDetail();
    const longFailure = "视频合并失败，已经安全截断；请重新上传。".repeat(12);
    detailWithLongFailure.pending_training_videos[3].failure_reason = longFailure;
    mockGet.mockResolvedValue({ data: detailWithLongFailure });

    renderAt("/training-tracking/patients/201");

    const failureSummary = await screen.findByLabelText(longFailure);
    expect(failureSummary).toHaveStyle({ maxWidth: "280px" });
    expect(failureSummary).toHaveAttribute("title", longFailure);
  });

  it("打开视频 Drawer 后才请求下载地址，关闭时卸载视频并清理短效 URL", async () => {
    const pauseSpy = vi.spyOn(window.HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    const loadSpy = vi.spyOn(window.HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
    mockGet.mockImplementation((url: string) => {
      if (url === "/training/tracking/patients/201/") {
        return Promise.resolve({ data: trackingDetail });
      }
      if (url === "/training/videos/8101/download-url/") {
        return Promise.resolve({ data: { url: "https://signed.example.com/video.mp4?token=secret" } });
      }
      if (url === "/training/videos/8101/analysis-jobs/latest/") {
        return Promise.resolve({ data: null });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalledWith("/training/videos/8101/download-url/");

    fireEvent.click(screen.getByRole("button", { name: "播放训练视频" }));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/videos/8101/download-url/");
    });
    const video = document.querySelector("video");
    expect(video).toBeTruthy();
    expect(video).toHaveAttribute("controls");
    expect(video).toHaveAttribute("preload", "metadata");
    expect(video).toHaveAttribute("src", "https://signed.example.com/video.mp4?token=secret");
    expect(screen.queryByText(/token=secret/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Close|关闭/ }));

    await waitFor(() => {
      expect(document.querySelector("video")).toBeNull();
    });
    expect(pauseSpy).toHaveBeenCalled();
    expect(loadSpy).toHaveBeenCalled();
  });

  it("实际结束时间缺失时仍查询固定穿戴窗口且不展示实际训练时段", async () => {
    const detailWithoutTrainingEnd = cloneTrackingDetail();
    detailWithoutTrainingEnd.recent_records[0].training_ended_at = null;
    mockGet.mockImplementation((url: string) =>
      videoDrawerGet(url, wearableWindowResponse, detailWithoutTrainingEnd),
    );

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalledWith(
      "/training/videos/8101/wearable-window/",
    );

    fireEvent.click(screen.getByRole("button", { name: "播放训练视频" }));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/training/videos/8101/wearable-window/",
      );
    });
    expect(await screen.findByText("训练时段穿戴趋势")).toBeInTheDocument();
    expect(screen.queryByText("训练时段")).not.toBeInTheDocument();
  });

  it("穿戴窗口不可用时完全隐藏穿戴区", async () => {
    mockGet.mockImplementation((url: string) =>
      videoDrawerGet(url, { available: false }),
    );

    const { queryClient } = renderAt("/training-tracking/patients/201");
    fireEvent.click(
      await screen.findByRole("button", { name: "播放训练视频" }),
    );

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/training/videos/8101/wearable-window/",
      );
    });
    await waitForWearableQueryToSettle(queryClient, "success");
    expect(
      await screen.findByLabelText("训练视频播放器"),
    ).toBeInTheDocument();
    expect(screen.getByText("动作分析")).toBeInTheDocument();
    expect(screen.queryByText("训练时段穿戴趋势")).not.toBeInTheDocument();
  });

  it("穿戴窗口请求失败时保留视频和动作分析且不展示错误", async () => {
    const detailWithoutTrainingEnd = cloneTrackingDetail();
    detailWithoutTrainingEnd.recent_records[0].training_ended_at = null;
    mockGet.mockImplementation((url: string) =>
      videoDrawerGet(
        url,
        new Error("wearable failed"),
        detailWithoutTrainingEnd,
      ),
    );

    const { queryClient } = renderAt("/training-tracking/patients/201");
    fireEvent.click(
      await screen.findByRole("button", { name: "播放训练视频" }),
    );

    await waitForWearableQueryToSettle(queryClient, "error");
    expect(
      await screen.findByLabelText("训练视频播放器"),
    ).toBeInTheDocument();
    expect(screen.getByText("动作分析")).toBeInTheDocument();
    expect(screen.queryByText("wearable failed")).not.toBeInTheDocument();
    expect(screen.queryByText("训练时段穿戴趋势")).not.toBeInTheDocument();
  });

  it("同一视频抽屉重新打开时重新查询穿戴窗口", async () => {
    mockGet.mockImplementation((url: string) => videoDrawerGet(url));

    renderAt("/training-tracking/patients/201");
    fireEvent.click(
      await screen.findByRole("button", { name: "播放训练视频" }),
    );
    expect(await screen.findByText("训练时段穿戴趋势")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Close|关闭/ }));
    await waitFor(() => {
      expect(screen.queryByText("训练时段穿戴趋势")).not.toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "播放训练视频" }));

    await waitFor(() => {
      expect(
        mockGet.mock.calls.filter(
          ([url]) => url === "/training/videos/8101/wearable-window/",
        ),
      ).toHaveLength(2);
    });
  });

  it("同一视频重开请求失败时不展示上次成功的穿戴数据", async () => {
    let wearableCallCount = 0;
    mockGet.mockImplementation((url: string) => {
      if (url === "/training/videos/8101/wearable-window/") {
        wearableCallCount += 1;
        return wearableCallCount === 1
          ? Promise.resolve({ data: wearableWindowResponse })
          : Promise.reject(new Error("wearable failed"));
      }
      return videoDrawerGet(url);
    });

    const { queryClient } = renderAt("/training-tracking/patients/201");
    fireEvent.click(
      await screen.findByRole("button", { name: "播放训练视频" }),
    );
    expect(await screen.findByText("训练时段穿戴趋势")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Close|关闭/ }));
    await waitFor(() => {
      expect(screen.queryByText("训练时段穿戴趋势")).not.toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "播放训练视频" }));

    expect(screen.queryByText("训练时段穿戴趋势")).not.toBeInTheDocument();
    await waitFor(() => expect(wearableCallCount).toBe(2));
    await waitForWearableQueryToSettle(queryClient, "error");
    expect(
      await screen.findByLabelText("训练视频播放器"),
    ).toBeInTheDocument();
    expect(screen.getByText("动作分析")).toBeInTheDocument();
    expect(screen.queryByText("wearable failed")).not.toBeInTheDocument();
    expect(screen.queryByText("训练时段穿戴趋势")).not.toBeInTheDocument();
  });

  it("实际开始时间缺失时仍查询且以后端不可用响应隐藏穿戴区", async () => {
    const detailWithoutTrainingStart = cloneTrackingDetail();
    detailWithoutTrainingStart.recent_records[0].training_started_at = null;
    mockGet.mockImplementation((url: string) =>
      videoDrawerGet(
        url,
        { available: false },
        detailWithoutTrainingStart,
      ),
    );

    const { queryClient } = renderAt("/training-tracking/patients/201");
    fireEvent.click(
      await screen.findByRole("button", { name: "播放训练视频" }),
    );

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/training/videos/8101/wearable-window/",
      );
    });
    await waitForWearableQueryToSettle(queryClient, "success");
    expect(
      await screen.findByLabelText("训练视频播放器"),
    ).toBeInTheDocument();
    expect(screen.getByText("动作分析")).toBeInTheDocument();
    expect(screen.queryByText("训练时段")).not.toBeInTheDocument();
    expect(screen.queryByText("训练时段穿戴趋势")).not.toBeInTheDocument();
  });

  it("三个穿戴指标都为空时完全隐藏穿戴区", async () => {
    mockGet.mockImplementation((url: string) =>
      videoDrawerGet(url, {
        available: true,
        window_started_at: "2026-08-06T01:32:14Z",
        window_ended_at: "2026-08-06T01:40:14Z",
        expected_duration_seconds: 180,
        buffer_seconds: 300,
        metrics: {
          heart_rate: {
            points: [],
            statistics: {
              average: 0,
              maximum: 0,
              minimum: 0,
              count: 0,
            },
          },
          blood_pressure: {
            points: [],
            statistics: {
              systolic: { average: 0, maximum: 0, minimum: 0 },
              diastolic: { average: 0, maximum: 0, minimum: 0 },
              count: 0,
            },
          },
          blood_oxygen: { points: [] },
        },
      }),
    );

    const { queryClient } = renderAt("/training-tracking/patients/201");
    fireEvent.click(
      await screen.findByRole("button", { name: "播放训练视频" }),
    );

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/training/videos/8101/wearable-window/",
      );
    });
    await waitForWearableQueryToSettle(queryClient, "success");
    expect(
      await screen.findByLabelText("训练视频播放器"),
    ).toBeInTheDocument();
    expect(screen.getByText("动作分析")).toBeInTheDocument();
    expect(screen.queryByText("训练时段穿戴趋势")).not.toBeInTheDocument();
  });

  it("手动创建动作分析任务，进行中禁用重复触发并每 2 秒轮询到成功计数后停止", async () => {
    const latestResponses = [
      null,
      {
        id: 9201,
        training_video: 8101,
        training_record: 7000,
        status: "pending",
        algorithm_name: "pp-tiny-pose",
        algorithm_version: "",
        rule_version: "shoulder-press-v1",
        total_count: null,
        standard_count: null,
        nonstandard_count: null,
        result_payload: {},
        failure_reason: "",
        started_at: null,
        finished_at: null,
        created_at: "2026-05-14T09:00:00+08:00",
      },
      {
        id: 9201,
        training_video: 8101,
        training_record: 7000,
        status: "succeeded",
        algorithm_name: "pp-tiny-pose",
        algorithm_version: "",
        rule_version: "shoulder-press-v1",
        total_count: 8,
        standard_count: 6,
        nonstandard_count: 2,
        result_payload: {},
        failure_reason: "",
        started_at: "2026-05-14T09:00:01+08:00",
        finished_at: "2026-05-14T09:00:05+08:00",
        created_at: "2026-05-14T09:00:00+08:00",
      },
    ];
    let latestCallCount = 0;
    mockGet.mockImplementation((url: string) => {
      if (url === "/training/tracking/patients/201/") {
        return Promise.resolve({ data: trackingDetail });
      }
      if (url === "/training/videos/8101/download-url/") {
        return Promise.resolve({ data: { url: "https://signed.example.com/video.mp4?token=secret" } });
      }
      if (url === "/training/videos/8101/analysis-jobs/latest/") {
        const data = latestResponses[Math.min(latestCallCount, latestResponses.length - 1)];
        latestCallCount += 1;
        return Promise.resolve({ data });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    mockPost.mockResolvedValue({
      data: {
        id: 9201,
        training_video: 8101,
        training_record: 7000,
        status: "pending",
        algorithm_name: "pp-tiny-pose",
        algorithm_version: "",
        rule_version: "shoulder-press-v1",
        total_count: null,
        standard_count: null,
        nonstandard_count: null,
        result_payload: {},
        failure_reason: "",
        started_at: null,
        finished_at: null,
        created_at: "2026-05-14T09:00:00+08:00",
      },
    });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "动作分析" }));
    expect(await screen.findByRole("button", { name: "开始动作分析" })).toBeEnabled();

    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "开始动作分析" }));

    await vi.waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/training/videos/8101/analysis-jobs/");
    });
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "分析处理中" })).toBeDisabled();
    });

    await vi.advanceTimersByTimeAsync(2000);

    await vi.waitFor(() => {
      expect(screen.getByText("总数 8")).toBeInTheDocument();
    });
    expect(screen.getByText("标准 6")).toBeInTheDocument();
    expect(screen.getByText("不标准 2")).toBeInTheDocument();
    const callsAfterSucceeded = latestCallCount;

    await vi.advanceTimersByTimeAsync(2200);

    expect(latestCallCount).toBe(callsAfterSucceeded);
  });

  it("动作分析失败时展示安全摘要并允许重试", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === "/training/tracking/patients/201/") {
        return Promise.resolve({ data: trackingDetail });
      }
      if (url === "/training/videos/8101/download-url/") {
        return Promise.resolve({ data: { url: "https://signed.example.com/video.mp4?token=secret" } });
      }
      if (url === "/training/videos/8101/analysis-jobs/latest/") {
        return Promise.resolve({
          data: {
            id: 9202,
            training_video: 8101,
            training_record: 7000,
            status: "failed",
            algorithm_name: "pp-tiny-pose",
            algorithm_version: "",
            rule_version: "shoulder-press-v1",
            total_count: null,
            standard_count: null,
            nonstandard_count: null,
            result_payload: {},
            failure_reason: "动作分析失败，请稍后重试",
            started_at: "2026-05-14T09:00:01+08:00",
            finished_at: "2026-05-14T09:00:05+08:00",
            created_at: "2026-05-14T09:00:00+08:00",
          },
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    mockPost.mockResolvedValue({
      data: {
        id: 9203,
        training_video: 8101,
        training_record: 7000,
        status: "pending",
      },
    });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "动作分析" }));

    expect(await screen.findByText("动作分析失败，请稍后重试")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新分析" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/training/videos/8101/analysis-jobs/");
    });
  });

  it("初次请求不带 project_patient，并按 range 切换趋势图数据", async () => {
    renderAt("/training-tracking/patients/201");

    await screen.findByText("训练患者甲");
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/tracking/patients/201/", { params: { range: "30d" } });
    });
    await waitFor(() => expect(screen.getAllByTestId("dual-axes-chart").length).toBeGreaterThan(0));
    expect(trendChartData()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "05-14", completed_count: 2, moving_average: 1.1 }),
      ]),
    );

    fireEvent.click(screen.getByText("近 7 天"));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/tracking/patients/201/", { params: { range: "7d" } });
    });
    await waitFor(() => expect(screen.getAllByTestId("dual-axes-chart").length).toBeGreaterThan(0));
    expect(trendChartData()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "05-14", completed_count: 2, moving_average: 1.1 }),
      ]),
    );

    fireEvent.click(screen.getByText("按周"));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/tracking/patients/201/", { params: { range: "weekly" } });
    });
    await waitFor(() => expect(screen.getAllByTestId("dual-axes-chart").length).toBeGreaterThan(0));
    expect(trendChartData()).toEqual([
      expect.objectContaining({
        label: "05-11 至 05-17",
        completed_count: 5,
        moving_average: 5,
      }),
    ]);
  });

  it("切换日期范围重新请求时保留详情页内容", async () => {
    let resolveRangeRequest: ((value: { data: typeof trackingDetail }) => void) | undefined;
    mockGet.mockImplementation((_url: string, config?: unknown) => {
      const params = (config as { params?: Record<string, unknown> } | undefined)?.params;
      if (params?.range === "7d") {
        return new Promise((resolve) => {
          resolveRangeRequest = resolve;
        });
      }
      return Promise.resolve({ data: trackingDetail });
    });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("训练患者甲")).toBeInTheDocument();
    fireEvent.click(screen.getByText("近 7 天"));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/tracking/patients/201/", { params: { range: "7d" } });
    });
    expect(screen.getByText("训练患者甲")).toBeInTheDocument();
    expect(screen.getByText("处方完成情况")).toBeInTheDocument();

    resolveRangeRequest?.({ data: trackingDetail });
  });

  it("切换项目后用 project_patient 重新请求", async () => {
    renderAt("/training-tracking/patients/201");

    await screen.findByText("训练患者甲");
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "切换项目" }));
    const option = await screen.findByTitle("研究项目 B");
    fireEvent.click(option);

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/training/tracking/patients/201/",
        expect.objectContaining({ params: expect.objectContaining({ project_patient: 9002 }) }),
      );
    });
  });

  it("切换患者路由时不沿用上一个患者的项目选择", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === "/training/tracking/patients/201/" || url === "/training/tracking/patients/202/") {
        return Promise.resolve({ data: trackingDetail });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    renderWithRouteSwitcher("/training-tracking/patients/201");

    await screen.findByText("训练患者甲");
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "切换项目" }));
    fireEvent.click(await screen.findByTitle("研究项目 B"));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/training/tracking/patients/201/",
        expect.objectContaining({ params: expect.objectContaining({ project_patient: 9002 }) }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "切换患者" }));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith("/training/tracking/patients/202/", { params: { range: "30d" } });
    });
    expect(
      mockGet.mock.calls.some(([url, config]) => {
        const params = (config as { params?: Record<string, unknown> } | undefined)?.params;
        return url === "/training/tracking/patients/202/" && params?.project_patient === 9002;
      }),
    ).toBe(false);
  });

  it("无效 patientId 不请求接口", () => {
    renderAt("/training-tracking/patients/not-a-number");

    expect(screen.getByText("无效的患者 ID")).toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("无可访问项目时展示空状态", async () => {
    mockGet.mockResolvedValue({ data: { ...trackingDetail, project_patients: [], selected_project_patient: null } });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("暂无可追踪项目")).toBeInTheDocument();
  });

  it("请求失败时展示后端错误而不是空态", async () => {
    mockGet.mockRejectedValueOnce({ response: { data: { detail: "患者不存在或无权访问" } } });

    renderAt("/training-tracking/patients/201");

    expect(await screen.findByText("患者不存在或无权访问")).toBeInTheDocument();
    expect(screen.queryByText("暂无训练追踪数据")).not.toBeInTheDocument();
  });
});
