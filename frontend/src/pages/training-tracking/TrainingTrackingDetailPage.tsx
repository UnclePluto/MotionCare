import { DualAxes, type DualAxesConfig } from "@ant-design/charts";
import { ExperimentOutlined, PlayCircleOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Drawer, Empty, Segmented, Select, Space, Spin, Statistic, Table, Tag } from "antd";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import type {
  TrackingDailyTrendPoint,
  TrackingDetail,
  TrackingGameSummaryRow,
  TrackingMovingAveragePoint,
  MotionAnalysisJob,
  TrackingPrescriptionCompletionRow,
  TrackingRecentRecord,
  TrackingWeeklyTrendPoint,
  TrainingTrackingRange,
} from "./types";

type ChartTrendPoint = {
  label: string;
  completed_count: number;
  moving_average: number;
};

const TRAINING_STATUS_LABEL: Record<string, string> = {
  completed: "已完成",
  partial: "部分完成",
  missed: "未完成",
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

const ANALYSIS_STATUS_LABEL: Record<string, string> = {
  pending: "待分析",
  running: "分析中",
  succeeded: "分析完成",
  failed: "分析失败",
};

const ANALYSIS_STATUS_COLOR: Record<string, string> = {
  pending: "default",
  running: "processing",
  succeeded: "success",
  failed: "error",
};

function isGameRecord(record: TrackingRecentRecord) {
  return record.internal_type === "game";
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

function errorMessage(error: unknown) {
  if (error && typeof error === "object" && "response" in error) {
    const data = (error as { response?: { data?: unknown } }).response?.data;
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) return detail;
    }
  }
  return "加载训练追踪数据失败";
}

function formatPercent(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
}

function formatNumber(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
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
  const numericPatientId = Number(patientId);
  const isValidPatientId = Number.isSafeInteger(numericPatientId) && numericPatientId > 0;
  const [range, setRange] = useState<TrainingTrackingRange>("30d");
  const [videoRecord, setVideoRecord] = useState<TrackingRecentRecord | null>(null);
  const [videoUrl, setVideoUrl] = useState("");
  const [videoLoading, setVideoLoading] = useState(false);
  const [videoError, setVideoError] = useState("");
  const [analysisError, setAnalysisError] = useState("");
  const queryClient = useQueryClient();
  const [selectedProjectPatient, setSelectedProjectPatient] = useState<{
    patientId: number;
    projectPatientId: number;
  } | null>(null);
  const selectedProjectPatientId =
    selectedProjectPatient?.patientId === numericPatientId ? selectedProjectPatient.projectPatientId : undefined;

  useEffect(() => {
    setSelectedProjectPatient(null);
  }, [numericPatientId]);

  const queryParams = useMemo(() => {
    const params: { range: TrainingTrackingRange; project_patient?: number } = { range };
    if (selectedProjectPatientId != null) params.project_patient = selectedProjectPatientId;
    return params;
  }, [range, selectedProjectPatientId]);

  const { data, isLoading, isFetching, isError, error } = useQuery({
    queryKey: ["training-tracking", "patients", numericPatientId, queryParams],
    queryFn: async () => {
      const response = await apiClient.get<TrackingDetail>(`/training/tracking/patients/${numericPatientId}/`, {
        params: queryParams,
      });
      return response.data;
    },
    enabled: isValidPatientId,
    placeholderData: (previousData) => previousData,
  });

  const latestAnalysisQuery = useQuery({
    queryKey: ["training-video-analysis", videoRecord?.video_id],
    queryFn: async () => {
      const response = await apiClient.get<MotionAnalysisJob | null>(
        `/training/videos/${videoRecord!.video_id}/analysis-jobs/latest/`,
      );
      return response.data;
    },
    enabled: Boolean(videoRecord?.video_id),
    refetchInterval: (query) =>
      query.state.data?.status === "pending" || query.state.data?.status === "running" ? 2000 : false,
  });

  const analysisMutation = useMutation({
    mutationFn: async (videoId: number) => {
      const response = await apiClient.post<MotionAnalysisJob>(`/training/videos/${videoId}/analysis-jobs/`);
      return response.data;
    },
    onMutate: () => setAnalysisError(""),
    onError: (reason) => setAnalysisError(errorMessage(reason).replace("加载训练追踪数据失败", "动作分析请求失败")),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["training-video-analysis"] }),
        queryClient.invalidateQueries({ queryKey: ["training-tracking", "patients", numericPatientId] }),
      ]);
    },
  });

  async function openVideo(record: TrackingRecentRecord) {
    if (!record.video_id) return;
    setVideoRecord(record);
    setVideoUrl("");
    setVideoError("");
    setVideoLoading(true);
    try {
      const response = await apiClient.get<{ url: string }>(`/training/videos/${record.video_id}/download-url/`);
      setVideoUrl(response.data.url);
    } catch (reason) {
      setVideoError(errorMessage(reason).replace("加载训练追踪数据失败", "视频地址获取失败"));
    } finally {
      setVideoLoading(false);
    }
  }

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

  const currentProject = data.selected_project_patient;
  const currentProjectPatientId = selectedProjectPatientId ?? currentProject.id;
  const activeTrendData =
    range === "weekly"
      ? buildWeeklyTrendData(data.trend.weekly)
      : buildDailyTrendData(data.trend.daily, data.trend.moving_average);
  const trendChartKey = `${range}:${activeTrendData.map((point) => point.label).join("|")}`;

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
            title="患者训练追踪"
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
                key: "prescription",
                label: "当前处方版本",
                children: data.current_prescription ? `当前处方 v${data.current_prescription.version}` : "暂无当前处方",
              },
            ]}
          />
        </Space>
      </Card>

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

      <Card title="最近训练记录">
        {analysisError ? <Alert type="error" showIcon message={analysisError} style={{ marginBottom: 16 }} /> : null}
        <Table<TrackingRecentRecord>
          rowKey="id"
          dataSource={data.recent_records}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          scroll={{ x: 1900 }}
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
              title: "录像与分析",
              key: "video-analysis",
              width: 240,
              render: (_, record) =>
                record.video_id ? (
                  <Space direction="vertical" size={6}>
                    <Space wrap size={6}>
                      <Button
                        size="small"
                        icon={<PlayCircleOutlined />}
                        onClick={() => void openVideo(record)}
                      >
                        查看视频
                      </Button>
                      <Button
                        size="small"
                        icon={<ExperimentOutlined />}
                        loading={analysisMutation.isPending && analysisMutation.variables === record.video_id}
                        disabled={["pending", "running"].includes(record.latest_analysis_status ?? "")}
                        onClick={() => analysisMutation.mutate(record.video_id!)}
                      >
                        动作分析
                      </Button>
                    </Space>
                    {record.latest_analysis_status ? (
                      <Space wrap size={4}>
                        <Tag color={ANALYSIS_STATUS_COLOR[record.latest_analysis_status]}>
                          {ANALYSIS_STATUS_LABEL[record.latest_analysis_status] ?? record.latest_analysis_status}
                        </Tag>
                        {record.latest_analysis_status === "succeeded" ? (
                          <span>
                            总 {record.analysis_total_count ?? 0} / 标准 {record.analysis_standard_count ?? 0} /
                            不标准 {record.analysis_nonstandard_count ?? 0}
                          </span>
                        ) : null}
                      </Space>
                    ) : (
                      <span>尚未分析</span>
                    )}
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
        title={videoRecord ? `${videoRecord.action_name}训练录像` : "训练录像"}
        width={680}
        open={Boolean(videoRecord)}
        onClose={() => {
          setVideoRecord(null);
          setVideoUrl("");
          setVideoError("");
        }}
      >
        {videoLoading ? <Spin /> : null}
        {videoError ? <Alert type="error" showIcon message={videoError} /> : null}
        {videoUrl ? (
          <video controls playsInline src={videoUrl} style={{ display: "block", width: "100%", background: "#000" }} />
        ) : null}
        {videoRecord ? (
          <Descriptions
            bordered
            size="small"
            column={1}
            style={{ marginTop: 16 }}
            items={[
              { key: "date", label: "训练日期", children: videoRecord.training_date },
              { key: "action", label: "动作", children: videoRecord.action_name },
              { key: "version", label: "处方版本", children: `v${videoRecord.prescription_version}` },
            ]}
          />
        ) : null}
        <Card
          size="small"
          title="动作分析"
          style={{ marginTop: 16 }}
          extra={
            videoRecord?.video_id ? (
              <Button
                icon={<ExperimentOutlined />}
                loading={analysisMutation.isPending}
                disabled={["pending", "running"].includes(latestAnalysisQuery.data?.status ?? "")}
                onClick={() => analysisMutation.mutate(videoRecord.video_id!)}
              >
                {latestAnalysisQuery.data?.status === "failed" ? "重新分析" : "动作分析"}
              </Button>
            ) : null
          }
        >
          {analysisMutation.isError ? <Alert type="error" showIcon message={errorMessage(analysisMutation.error)} /> : null}
          {latestAnalysisQuery.isLoading ? <Spin size="small" /> : null}
          {latestAnalysisQuery.data ? (
            <Descriptions
              size="small"
              column={1}
              items={[
                {
                  key: "status",
                  label: "状态",
                  children: (
                    <Tag color={ANALYSIS_STATUS_COLOR[latestAnalysisQuery.data.status]}>
                      {ANALYSIS_STATUS_LABEL[latestAnalysisQuery.data.status]}
                    </Tag>
                  ),
                },
                { key: "total", label: "总次数", children: latestAnalysisQuery.data.total_count ?? "—" },
                { key: "standard", label: "标准次数", children: latestAnalysisQuery.data.standard_count ?? "—" },
                { key: "nonstandard", label: "不标准次数", children: latestAnalysisQuery.data.nonstandard_count ?? "—" },
                {
                  key: "failure",
                  label: "失败原因",
                  children: latestAnalysisQuery.data.failure_reason || "—",
                },
              ]}
            />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未分析" />
          )}
        </Card>
      </Drawer>
    </Space>
  );
}
