import { DualAxes, type DualAxesConfig } from "@ant-design/charts";
import { ExperimentOutlined, HeartOutlined, LineChartOutlined, PlayCircleOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Segmented,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { formatShanghaiDate } from "../../utils/shanghaiTime";
import { WearableHealthTab } from "../wearables/WearableHealthTab";
import { TrainingVideoWearablePanel } from "./TrainingVideoWearablePanel";
import type {
  TrackingDailyTrendPoint,
  TrackingDetail,
  TrackingGameSummaryRow,
  TrackingMovingAveragePoint,
  TrackingPendingVideo,
  TrackingPrescriptionCompletionRow,
  TrackingRecentRecord,
  TrackingWeeklyTrendPoint,
  TrainingTrackingRange,
  TrainingVideoWearableWindowResponse,
} from "./types";
import "./TrainingTrackingDetailPage.css";

type ChartTrendPoint = {
  label: string;
  completed_count: number;
  moving_average: number;
};

type MotionAnalysisJobStatus = "pending" | "running" | "succeeded" | "failed";

type MotionAnalysisJob = {
  id: number;
  training_video: number;
  training_record: number | null;
  status: MotionAnalysisJobStatus;
  algorithm_name: string;
  algorithm_version: string;
  rule_version: string;
  total_count: number | null;
  standard_count: number | null;
  nonstandard_count: number | null;
  result_payload: Record<string, unknown>;
  failure_reason: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

const TRAINING_STATUS_LABEL: Record<string, string> = {
  completed: "已完成",
  partial: "部分完成",
  missed: "未完成",
};

const PENDING_VIDEO_PROCESSING_STATUSES = new Set(["queued", "assembling", "uploading_qiniu"]);
const SHOULDER_PRESS_SOURCE_KEY = "motion-resistance-shoulder-press";

const VIDEO_STATUS_LABEL: Record<string, string> = {
  attached: "已上传",
  queued: "视频处理中",
  assembling: "视频处理中",
  uploading_qiniu: "视频处理中",
  failed: "处理失败",
};

const ANALYSIS_STATUS_LABEL: Record<MotionAnalysisJobStatus, string> = {
  pending: "待分析",
  running: "分析中",
  succeeded: "分析完成",
  failed: "分析失败",
};

const RANGE_LABEL: Record<TrainingTrackingRange, string> = {
  "30d": "近 30 天",
  "7d": "近 7 天",
  weekly: "按周",
};

const UPLOAD_MODE_LABEL: Record<string, string> = {
  direct: "实时上传",
  retry: "补传",
};

function isGameRecord(record: TrackingRecentRecord) {
  return record.internal_type === "game";
}

function isShoulderPressRecord(record: TrackingRecentRecord) {
  return record.action_source_key === SHOULDER_PRESS_SOURCE_KEY;
}

function canUseVideoActions(record: TrackingRecentRecord) {
  return record.video_id != null && record.video_status === "attached" && isShoulderPressRecord(record);
}

function isActiveAnalysisStatus(status: MotionAnalysisJobStatus | null | undefined) {
  return status === "pending" || status === "running";
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";

  const match = value.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  if (!match) return value;
  return `${match[1]} ${match[2]}`;
}

function formatTrendDateLabel(value: string) {
  const match = value.match(/^\d{4}-(\d{2})-(\d{2})$/);
  if (!match) return value;
  return `${match[1]}-${match[2]}`;
}

function errorMessage(error: unknown, fallback = "加载训练追踪数据失败") {
  if (error && typeof error === "object" && "response" in error) {
    const data = (error as { response?: { data?: unknown } }).response?.data;
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim() && !containsSensitiveErrorText(detail)) return detail;
    }
  }
  return fallback;
}

function containsSensitiveErrorText(value: string) {
  return /https?:\/\//i.test(value) ||
    /signature|token|secret|credential|authorization|raw response|access[_-]?key/i.test(value) ||
    /\b(?:AK|SK)\b\s*[:=]/.test(value);
}

function formatPercent(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
}

function formatNumber(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function renderPendingVideoStatus(status: TrackingPendingVideo["status"]) {
  if (PENDING_VIDEO_PROCESSING_STATUSES.has(status)) {
    return <Tag color="processing">视频处理中</Tag>;
  }
  return <Tag color={status === "failed" ? "red" : undefined}>{VIDEO_STATUS_LABEL[status] ?? status}</Tag>;
}

function renderPendingFailureReason(value: string, record: TrackingPendingVideo) {
  if (record.status !== "failed") return "—";
  const summary = value || "处理失败";
  return (
    <Typography.Text
      aria-label={summary}
      ellipsis={{ tooltip: summary }}
      style={{ display: "inline-block", maxWidth: 280 }}
      title={summary}
    >
      {summary}
    </Typography.Text>
  );
}

function buildDailyTrendData(
  daily: TrackingDailyTrendPoint[],
  movingAverage: TrackingMovingAveragePoint[],
): ChartTrendPoint[] {
  const movingAverageByDate = new Map(movingAverage.map((point) => [point.date, point.completed_count_avg]));
  return daily.map((point) => ({
    label: formatTrendDateLabel(point.date),
    completed_count: point.completed_count,
    moving_average: movingAverageByDate.get(point.date) ?? point.completed_count,
  }));
}

function buildWeeklyTrendData(weekly: TrackingWeeklyTrendPoint[]): ChartTrendPoint[] {
  return weekly.map((point) => ({
    label: `${formatTrendDateLabel(point.week_start)} 至 ${formatTrendDateLabel(point.week_end)}`,
    completed_count: point.completed_count,
    moving_average: point.completed_count,
  }));
}

function makeTrendChartConfig(data: ChartTrendPoint[], range: TrainingTrackingRange): DualAxesConfig {
  return {
    height: 280,
    autoFit: true,
    data,
    xField: "label",
    children: [
      {
        type: "interval",
        yField: "completed_count",
        colorField: () => "#1677ff",
        axis: { y: { title: "完成次数" } },
      },
      {
        type: "line",
        yField: "moving_average",
        shapeField: "smooth",
        style: { lineWidth: 2, stroke: "#fa8c16" },
        axis: { y: { position: "right", title: range === "weekly" ? "周汇总" : "7 日移动平均" } },
      },
    ],
    tooltip: { shared: true },
    legend: false,
  };
}

function makeCompletionChartConfig(rows: TrackingPrescriptionCompletionRow[]): DualAxesConfig {
  const data = rows.map((row) => ({
    action_name: row.action_name,
    completion_rate: row.completion_rate,
    completed_count: row.completed_count,
  }));

  return {
    height: 240,
    autoFit: true,
    data,
    xField: "action_name",
    children: [
      {
        type: "interval",
        yField: "completion_rate",
        colorField: () => "#52c41a",
        axis: { y: { title: "完成率" } },
      },
      {
        type: "line",
        yField: "completed_count",
        style: { lineWidth: 2, stroke: "#1677ff" },
        axis: { y: { position: "right", title: "完成次数" } },
      },
    ],
    tooltip: { shared: true },
    legend: false,
  };
}

export function TrainingTrackingDetailPage() {
  const { patientId } = useParams<{ patientId: string }>();
  const queryClient = useQueryClient();
  const numericPatientId = Number(patientId);
  const isValidPatientId = Number.isSafeInteger(numericPatientId) && numericPatientId > 0;
  const [range, setRange] = useState<TrainingTrackingRange>("30d");
  const [activeTab, setActiveTab] = useState<"training" | "wearable">("training");
  const [selectedProjectPatient, setSelectedProjectPatient] = useState<{
    patientId: number;
    projectPatientId: number;
  } | null>(null);
  const [videoDrawerRecord, setVideoDrawerRecord] = useState<TrackingRecentRecord | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const selectedProjectPatientId =
    selectedProjectPatient?.patientId === numericPatientId ? selectedProjectPatient.projectPatientId : undefined;
  const drawerOpen = videoDrawerRecord !== null;
  const selectedVideoId = videoDrawerRecord?.video_id ?? null;
  const selectedVideoSupportsAnalysis = videoDrawerRecord ? isShoulderPressRecord(videoDrawerRecord) : false;

  useEffect(() => {
    setSelectedProjectPatient(null);
    setActiveTab("training");
    setVideoDrawerRecord(null);
    setDownloadUrl(null);
    setDownloadLoading(false);
    setDownloadError(null);
  }, [numericPatientId]);

  const queryParams = useMemo(() => {
    const params: { range: TrainingTrackingRange; project_patient?: number } = { range };
    if (selectedProjectPatientId != null) params.project_patient = selectedProjectPatientId;
    return params;
  }, [range, selectedProjectPatientId]);

  const detailQueryKey = useMemo(
    () => ["training-tracking", "patients", numericPatientId, queryParams] as const,
    [numericPatientId, queryParams],
  );

  const { data, isLoading, isFetching, isError, error } = useQuery({
    queryKey: detailQueryKey,
    queryFn: async () => {
      const response = await apiClient.get<TrackingDetail>(`/training/tracking/patients/${numericPatientId}/`, {
        params: queryParams,
      });
      return response.data;
    },
    enabled: isValidPatientId,
    placeholderData: (previousData, previousQuery) =>
      previousQuery?.queryKey[2] === numericPatientId ? previousData : undefined,
  });

  const latestAnalysisQuery = useQuery({
    queryKey: ["training-video-analysis-latest", selectedVideoId],
    queryFn: async () => {
      const response = await apiClient.get<MotionAnalysisJob | null>(
        `/training/videos/${selectedVideoId}/analysis-jobs/latest/`,
      );
      return response.data;
    },
    enabled: drawerOpen && selectedVideoId != null && selectedVideoSupportsAnalysis,
    refetchInterval: (query) => (isActiveAnalysisStatus(query.state.data?.status) ? 2000 : false),
  });

  const wearableWindowQuery = useQuery({
    queryKey: ["training-video-wearable-window", selectedVideoId],
    queryFn: async () => {
      const response = await apiClient.get<TrainingVideoWearableWindowResponse>(
        `/training/videos/${selectedVideoId}/wearable-window/`,
      );
      return response.data;
    },
    enabled: drawerOpen && selectedVideoId != null,
    staleTime: 0,
    refetchOnMount: "always",
  });

  const createAnalysisMutation = useMutation({
    mutationFn: async (videoId: number) => {
      const response = await apiClient.post<MotionAnalysisJob>(`/training/videos/${videoId}/analysis-jobs/`);
      return response.data;
    },
    onSuccess: async (job, videoId) => {
      queryClient.setQueryData(["training-video-analysis-latest", videoId], job);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["training-tracking", "patients", numericPatientId] }),
        queryClient.invalidateQueries({ queryKey: ["training-video-analysis-latest", videoId] }),
      ]);
    },
  });

  const stopAndUnloadVideo = () => {
    const node = videoRef.current;
    if (!node) return;
    node.pause();
    node.removeAttribute("src");
    node.load();
  };

  const closeVideoDrawer = () => {
    stopAndUnloadVideo();
    setVideoDrawerRecord(null);
    setDownloadUrl(null);
    setDownloadLoading(false);
    setDownloadError(null);
    createAnalysisMutation.reset();
  };

  const openVideoDrawer = (record: TrackingRecentRecord) => {
    setVideoDrawerRecord(record);
    setDownloadUrl(null);
    setDownloadError(null);
    createAnalysisMutation.reset();
  };

  useEffect(() => {
    if (!drawerOpen || selectedVideoId == null) return undefined;

    let active = true;
    setDownloadUrl(null);
    setDownloadError(null);
    setDownloadLoading(true);

    apiClient
      .get<{ url: string }>(`/training/videos/${selectedVideoId}/download-url/`)
      .then((response) => {
        if (active) setDownloadUrl(response.data.url);
      })
      .catch(() => {
        if (active) setDownloadError("获取视频地址失败");
      })
      .finally(() => {
        if (active) setDownloadLoading(false);
      });

    return () => {
      active = false;
      setDownloadUrl(null);
      setDownloadLoading(false);
      setDownloadError(null);
    };
  }, [drawerOpen, selectedVideoId]);

  if (!isValidPatientId) {
    return <Alert type="error" message="无效的患者 ID" />;
  }

  if (isLoading) {
    return (
      <Card>
        <Spin />
      </Card>
    );
  }

  if (isError) {
    return (
      <Card title="患者训练追踪">
        <Alert type="error" showIcon message={errorMessage(error)} />
      </Card>
    );
  }

  if (!data) {
    return (
      <Card title="患者训练追踪">
        <Empty description="暂无训练追踪数据" />
      </Card>
    );
  }

  if (data.project_patients.length === 0 || !data.selected_project_patient) {
    return (
      <Card title="患者训练追踪">
        <Empty description="暂无可追踪项目" />
      </Card>
    );
  }

  const currentProjectPatientId = selectedProjectPatientId ?? data.selected_project_patient.id;
  const currentProject =
    data.project_patients.find((projectPatient) => projectPatient.id === currentProjectPatientId) ??
    data.selected_project_patient;
  const currentProjectDataReady = data.selected_project_patient.id === currentProjectPatientId;
  const activeTrendData =
    range === "weekly"
      ? buildWeeklyTrendData(data.trend.weekly)
      : buildDailyTrendData(data.trend.daily, data.trend.moving_average);
  const trendChartKey = `${range}:${activeTrendData.map((point) => point.label).join("|")}`;
  const latestAnalysisJob = latestAnalysisQuery.data;
  const analysisStatus = latestAnalysisJob?.status ?? videoDrawerRecord?.latest_analysis_status ?? null;
  const analysisTotalCount = latestAnalysisJob?.total_count ?? videoDrawerRecord?.analysis_total_count ?? null;
  const analysisStandardCount =
    latestAnalysisJob?.standard_count ?? videoDrawerRecord?.analysis_standard_count ?? null;
  const analysisNonstandardCount =
    latestAnalysisJob?.nonstandard_count ?? videoDrawerRecord?.analysis_nonstandard_count ?? null;
  const analysisFailureReason = latestAnalysisJob?.failure_reason || "";
  const analysisInProgress = isActiveAnalysisStatus(analysisStatus) || createAnalysisMutation.isPending;
  const analysisActionLabel = analysisInProgress ? "分析处理中" : analysisStatus ? "重新分析" : "开始动作分析";

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Space wrap align="center">
            <span>项目</span>
            <Select
              aria-label="切换项目"
              style={{ minWidth: 260 }}
              value={currentProjectPatientId}
              onChange={(value) => setSelectedProjectPatient({ patientId: numericPatientId, projectPatientId: value })}
              options={data.project_patients.map((projectPatient) => ({
                value: projectPatient.id,
                label: projectPatient.project_name,
                title: projectPatient.project_name,
              }))}
            />
          </Space>

          <Descriptions
            title="患者训练与健康"
            bordered
            size="small"
            column={{ xs: 1, sm: 2, lg: 3 }}
            items={[
              { key: "patient", label: "患者", children: data.patient.name },
              { key: "phone", label: "手机号", children: data.patient.phone_masked },
              { key: "project", label: "当前项目", children: currentProject.project_name },
              { key: "projectId", label: "项目 ID", children: currentProject.project },
              { key: "group", label: "分组", children: currentProject.group_name ?? "—" },
              {
                key: "period",
                label: "研究周期",
                children: `研究周期：${formatShanghaiDate(currentProject.enrolled_at)} 至 ${
                  currentProject.project_completed_at
                    ? formatShanghaiDate(currentProject.project_completed_at)
                    : "进行中"
                }`,
              },
              {
                key: "prescription",
                label: "当前处方版本",
                children: data.current_prescription ? `当前处方 v${data.current_prescription.version}` : "暂无当前处方",
              },
            ]}
          />
        </Space>
      </Card>

      <Tabs
        rootClassName="training-health-tabs"
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as "training" | "wearable")}
        items={[
          {
            key: "training",
            label: (
              <Space size={8}>
                <LineChartOutlined aria-hidden="true" />
                训练跟踪
              </Space>
            ),
            children: (
              <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card title="处方完成情况">
        {data.prescription_completion.length === 0 ? (
          <Empty description="暂无处方完成数据" />
        ) : (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <Table<TrackingPrescriptionCompletionRow>
              rowKey="prescription_action"
              dataSource={data.prescription_completion}
              pagination={false}
              columns={[
                { title: "处方动作", dataIndex: "action_name" },
                { title: "动作类型", dataIndex: "action_type" },
                { title: "目标次数", dataIndex: "target_count" },
                { title: "已完成次数", dataIndex: "completed_count" },
                {
                  title: "完成率",
                  dataIndex: "completion_rate",
                  render: (value: number) => formatPercent(value),
                },
                {
                  title: "最近完成",
                  dataIndex: "recent_record_at",
                  render: (value: string | null) => formatDateTime(value),
                },
              ]}
            />
            <DualAxes {...makeCompletionChartConfig(data.prescription_completion)} />
          </Space>
        )}
      </Card>

      <Card title="训练趋势" extra={isFetching ? <Spin size="small" /> : null}>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Segmented
            value={range}
            onChange={(value) => setRange(value as TrainingTrackingRange)}
            options={(Object.keys(RANGE_LABEL) as TrainingTrackingRange[]).map((key) => ({
              label: RANGE_LABEL[key],
              value: key,
            }))}
          />
          <div style={{ width: "100%", minHeight: 280 }}>
            {activeTrendData.length > 0 ? (
              <DualAxes key={trendChartKey} {...makeTrendChartConfig(activeTrendData, range)} />
            ) : (
              <Empty description="暂无趋势数据" />
            )}
          </div>
        </Space>
      </Card>

      <Card title="游戏表现统计">
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Space wrap size={16}>
            <Card size="small">
              <Statistic title="平均得分" value={formatNumber(data.game_summary.average_score)} />
            </Card>
            <Card size="small">
              <Statistic title="平均正确率" value={formatPercent(data.game_summary.average_accuracy_rate)} />
            </Card>
            <Card size="small">
              <Statistic title="总错误次数" value={data.game_summary.total_error_count} />
            </Card>
          </Space>
          <Table<TrackingGameSummaryRow>
            rowKey="prescription_action"
            dataSource={data.game_summary.by_game}
            pagination={false}
            columns={[
              { title: "游戏动作", dataIndex: "action_name" },
              { title: "记录次数", dataIndex: "record_count" },
              {
                title: "平均得分",
                dataIndex: "average_score",
                render: (value: number | null) => formatNumber(value),
              },
              {
                title: "平均正确率",
                dataIndex: "average_accuracy_rate",
                render: (value: number | null) => formatPercent(value),
              },
              {
                title: "最近记录",
                dataIndex: "recent_record_at",
                render: (value: string | null) => formatDateTime(value),
              },
            ]}
          />
        </Space>
      </Card>

      <Card title="待处理视频">
        <Table<TrackingPendingVideo>
          rowKey="id"
          dataSource={data.pending_training_videos}
          pagination={false}
          locale={{ emptyText: "暂无待处理视频" }}
          columns={[
            { title: "训练日期", dataIndex: "training_date" },
            { title: "动作", dataIndex: "action_name" },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: TrackingPendingVideo["status"]) => renderPendingVideoStatus(value),
            },
            {
              title: "失败摘要",
              dataIndex: "failure_reason",
              width: 320,
              ellipsis: true,
              render: (value: string, record) => renderPendingFailureReason(value, record),
            },
            {
              title: "创建时间",
              dataIndex: "created_at",
              render: (value: string) => formatDateTime(value),
            },
          ]}
        />
      </Card>

      <Card title="最近训练记录">
        <Table<TrackingRecentRecord>
          rowKey="id"
          dataSource={data.recent_records}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          columns={[
            { title: "训练日期", dataIndex: "training_date" },
            { title: "动作", dataIndex: "action_name" },
            { title: "动作类型", dataIndex: "action_type" },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: string) => <Tag>{TRAINING_STATUS_LABEL[value] ?? value}</Tag>,
            },
            { title: "处方版本", dataIndex: "prescription_version" },
            {
              title: "时长",
              dataIndex: "actual_duration_minutes",
              render: (value: number | null) => value ?? "—",
            },
            {
              title: "得分",
              dataIndex: "score",
              render: (value: number | null) => formatNumber(value),
            },
            {
              title: "正确率",
              dataIndex: "game_accuracy_rate",
              render: (value: number | null) => formatPercent(value),
            },
            {
              title: "错误次数",
              dataIndex: "game_error_count",
              render: (value: number | null) => value ?? "—",
            },
            {
              title: "难度",
              dataIndex: "game_difficulty",
              render: (value: string | null) => value ?? "—",
            },
            {
              title: "结束方式",
              dataIndex: "game_ended_early",
              render: (value: boolean | null, record) =>
                isGameRecord(record) && value != null ? (
                  value ? (
                    <Tag color="orange">提前结束</Tag>
                  ) : (
                    <Tag color="green">到时完成</Tag>
                  )
                ) : (
                  "—"
                ),
            },
            {
              title: "上传方式",
              dataIndex: "game_upload_mode",
              render: (value: string | null, record) =>
                isGameRecord(record) && value ? (UPLOAD_MODE_LABEL[value] ?? value) : "—",
            },
            {
              title: "补传次数",
              dataIndex: "game_total_retry_count",
              render: (value: number | null, record) =>
                isGameRecord(record) && value != null ? `${value} 次` : "—",
            },
            {
              title: "调难原因",
              dataIndex: "game_difficulty_adjust_reason",
              render: (value: string | null, record) => (isGameRecord(record) ? (value || "—") : "—"),
            },
            {
              title: "视频",
              render: (_: unknown, record) =>
                canUseVideoActions(record) ? (
                  <Space size={4}>
                    <Tooltip title="播放视频">
                      <Button
                        aria-label="播放训练视频"
                        icon={<PlayCircleOutlined />}
                        size="small"
                        type="text"
                        onClick={() => openVideoDrawer(record)}
                      />
                    </Tooltip>
                    <Tooltip title="动作分析">
                      <Button
                        aria-label="动作分析"
                        icon={<ExperimentOutlined />}
                        size="small"
                        type="text"
                        onClick={() => openVideoDrawer(record)}
                      />
                    </Tooltip>
                  </Space>
                ) : (
                  "—"
                ),
            },
            {
              title: "备注",
              dataIndex: "note",
              render: (value: string) => value || "—",
            },
          ]}
        />
      </Card>

      <Drawer
        destroyOnClose
        title="训练视频"
        open={drawerOpen}
        width={720}
        onClose={closeVideoDrawer}
      >
        {videoDrawerRecord ? (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <Descriptions
              bordered
              size="small"
              column={1}
              items={[
                { key: "date", label: "训练日期", children: videoDrawerRecord.training_date },
                { key: "action", label: "动作", children: videoDrawerRecord.action_name },
                {
                  key: "videoStatus",
                  label: "视频状态",
                  children: (
                    <Tag color="green">{VIDEO_STATUS_LABEL[videoDrawerRecord.video_status ?? ""] ?? "已上传"}</Tag>
                  ),
                },
              ]}
            />

            <div style={{ width: "100%", minHeight: 360 }}>
              {downloadLoading ? (
                <Spin />
              ) : downloadError ? (
                <Alert type="error" showIcon message={downloadError} />
              ) : downloadUrl ? (
                <video
                  ref={videoRef}
                  aria-label="训练视频播放器"
                  controls
                  preload="metadata"
                  src={downloadUrl}
                  style={{
                    width: "100%",
                    maxWidth: "100%",
                    height: 360,
                    background: "#000",
                    borderRadius: 4,
                  }}
                />
              ) : null}
            </div>

            {selectedVideoSupportsAnalysis ? (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Space wrap align="center">
                  <span>动作分析</span>
                  {analysisStatus ? <Tag>{ANALYSIS_STATUS_LABEL[analysisStatus]}</Tag> : <Tag>暂无结果</Tag>}
                  <Button
                    type="primary"
                    size="small"
                    loading={createAnalysisMutation.isPending}
                    disabled={analysisInProgress || selectedVideoId == null}
                    onClick={() => {
                      if (selectedVideoId != null) createAnalysisMutation.mutate(selectedVideoId);
                    }}
                  >
                    {analysisActionLabel}
                  </Button>
                </Space>

                {latestAnalysisQuery.isFetching && analysisStatus == null ? <Spin size="small" /> : null}

                {latestAnalysisQuery.isError ? (
                  <Alert
                    type="error"
                    showIcon
                    message={errorMessage(latestAnalysisQuery.error, "加载动作分析结果失败")}
                    action={
                      <Button aria-label="重试" size="small" onClick={() => latestAnalysisQuery.refetch()}>
                        重试
                      </Button>
                    }
                  />
                ) : isActiveAnalysisStatus(analysisStatus) ? (
                  <Alert type="info" showIcon message="动作分析处理中" />
                ) : analysisStatus === "succeeded" ? (
                  <Space wrap>
                    <Tag color="blue">总数 {formatNumber(analysisTotalCount)}</Tag>
                    <Tag color="green">标准 {formatNumber(analysisStandardCount)}</Tag>
                    <Tag color="orange">不标准 {formatNumber(analysisNonstandardCount)}</Tag>
                  </Space>
                ) : analysisStatus === "failed" ? (
                  <Alert
                    type="error"
                    showIcon
                    message={analysisFailureReason || "动作分析失败，请稍后重试"}
                  />
                ) : (
                  <span>暂无动作分析结果</span>
                )}

                {createAnalysisMutation.isError ? (
                  <Alert
                    type="error"
                    showIcon
                    message={errorMessage(createAnalysisMutation.error, "动作分析请求失败")}
                  />
                ) : null}
              </Space>
            ) : null}

            {!wearableWindowQuery.isFetching &&
            !wearableWindowQuery.isError &&
            wearableWindowQuery.data?.available ? (
              <TrainingVideoWearablePanel data={wearableWindowQuery.data} />
            ) : null}
          </Space>
        ) : null}
      </Drawer>
              </Space>
            ),
          },
          {
            key: "wearable",
            label: (
              <Space size={8}>
                <HeartOutlined aria-hidden="true" />
                穿戴健康
              </Space>
            ),
            children: currentProjectDataReady ? (
              <WearableHealthTab patientId={numericPatientId} projectPatientId={currentProjectPatientId} />
            ) : (
              <Card>
                <Spin />
              </Card>
            ),
          },
        ]}
      />
    </Space>
  );
}
