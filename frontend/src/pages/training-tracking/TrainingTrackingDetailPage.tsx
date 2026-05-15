import { DualAxes, type DualAxesConfig } from "@ant-design/charts";
import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Descriptions, Empty, Select, Space, Spin, Statistic, Table, Tabs, Tag } from "antd";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import type {
  GamePerformanceRow,
  PrescriptionCompletionRow,
  RecentTrainingRecord,
  TrainingTrackingCurrentProjectPatient,
  TrainingTrackingDetail,
  TrainingTrackingProjectOption,
  TrainingTrackingRange,
  TrainingTrendPoint,
} from "./types";

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

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";

  const match = value.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  if (!match) return value;
  return `${match[1]} ${match[2]}`;
}

function formatPercent(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
}

function formatNumber(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function projectPatientId(project: TrainingTrackingProjectOption | TrainingTrackingCurrentProjectPatient | null | undefined) {
  if (!project) return undefined;
  return project.project_patient_id ?? project.id;
}

function projectId(project: TrainingTrackingProjectOption | TrainingTrackingCurrentProjectPatient | null | undefined) {
  if (!project) return undefined;
  return project.project_id ?? project.project;
}

function trendLabel(point: TrainingTrendPoint) {
  return point.label ?? point.date ?? point.week_start ?? "";
}

function buildTrendData(points: TrainingTrendPoint[]) {
  return points.map((point) => ({
    label: trendLabel(point),
    completed_count: point.completed_count,
    moving_average: point.moving_average ?? point.completed_count,
  }));
}

function makeTrendChartConfig(points: TrainingTrendPoint[], range: TrainingTrackingRange): DualAxesConfig {
  return {
    height: 280,
    autoFit: true,
    data: buildTrendData(points),
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

function makeCompletionChartConfig(rows: PrescriptionCompletionRow[]): DualAxesConfig {
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
  const [selectedProjectPatientId, setSelectedProjectPatientId] = useState<number | undefined>();

  const queryParams = useMemo(() => {
    const params: { range: TrainingTrackingRange; project_patient?: number } = { range };
    if (selectedProjectPatientId != null) params.project_patient = selectedProjectPatientId;
    return params;
  }, [range, selectedProjectPatientId]);

  const { data, isLoading } = useQuery({
    queryKey: ["training-tracking", "patients", numericPatientId, queryParams],
    queryFn: async () => {
      const response = await apiClient.get<TrainingTrackingDetail>(`/training/tracking/patients/${numericPatientId}/`, {
        params: queryParams,
      });
      return response.data;
    },
    enabled: isValidPatientId,
  });

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

  if (!data) {
    return (
      <Card title="患者训练追踪">
        <Empty description="暂无训练追踪数据" />
      </Card>
    );
  }

  const projectOptions = data.project_options.length > 0 ? data.project_options : data.projects ?? [];
  const currentProject = data.current_project_patient ?? data.current_project;
  const currentProjectPatientId = selectedProjectPatientId ?? projectPatientId(currentProject);
  const currentPrescriptionVersion = data.current_prescription?.version ?? currentProject?.prescription_version ?? null;
  const activeTrendPoints =
    range === "30d" ? data.trends.daily_30d : range === "7d" ? data.trends.daily_7d : data.trends.weekly;

  if (!currentProject || projectOptions.length === 0) {
    return (
      <Card title="患者训练追踪">
        <Empty description="暂无可追踪项目" />
      </Card>
    );
  }

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
              onChange={(value) => setSelectedProjectPatientId(value)}
              options={projectOptions
                .map((project) => {
                  const value = projectPatientId(project);
                  if (value == null) return null;
                  return {
                    value,
                    label: project.project_name,
                    title: project.project_name,
                  };
                })
                .filter((item): item is { value: number; label: string; title: string } => item != null)}
            />
          </Space>

          <Descriptions
            title="患者训练追踪"
            bordered
            size="small"
            column={{ xs: 1, sm: 2, lg: 3 }}
            items={[
              { key: "patient", label: "患者", children: data.patient.name },
              { key: "phone", label: "手机号", children: data.patient.phone },
              { key: "project", label: "当前项目", children: currentProject.project_name },
              { key: "projectId", label: "项目 ID", children: projectId(currentProject) ?? "—" },
              { key: "group", label: "分组", children: currentProject.group_name ?? "—" },
              {
                key: "prescription",
                label: "当前处方版本",
                children: currentPrescriptionVersion ? `当前处方 v${currentPrescriptionVersion}` : "暂无当前处方",
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
            <Table<PrescriptionCompletionRow>
              rowKey="action_id"
              dataSource={data.prescription_completion}
              pagination={false}
              columns={[
                { title: "处方动作", dataIndex: "action_name" },
                { title: "应完成次数", dataIndex: "prescribed_count" },
                { title: "已完成次数", dataIndex: "completed_count" },
                {
                  title: "完成率",
                  dataIndex: "completion_rate",
                  render: (value: number) => formatPercent(value),
                },
              ]}
            />
            <DualAxes {...makeCompletionChartConfig(data.prescription_completion)} />
          </Space>
        )}
      </Card>

      <Card title="训练趋势">
        <Tabs
          activeKey={range}
          onChange={(key) => setRange(key as TrainingTrackingRange)}
          items={(Object.keys(RANGE_LABEL) as TrainingTrackingRange[]).map((key) => ({
            key,
            label: RANGE_LABEL[key],
            children:
              activeTrendPoints.length > 0 ? (
                <DualAxes {...makeTrendChartConfig(activeTrendPoints, range)} />
              ) : (
                <Empty description="暂无趋势数据" />
              ),
          }))}
        />
      </Card>

      <Card title="游戏表现统计">
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Space wrap size={16}>
            <Card size="small">
              <Statistic title="平均得分" value={formatNumber(data.game_summary.average_score)} />
            </Card>
            <Card size="small">
              <Statistic title="平均正确率" value={formatPercent(data.game_summary.average_accuracy)} />
            </Card>
            <Card size="small">
              <Statistic title="总错误次数" value={data.game_summary.total_errors} />
            </Card>
          </Space>
          <Table<GamePerformanceRow>
            rowKey="game_name"
            dataSource={data.game_summary.by_game}
            pagination={false}
            columns={[
              { title: "游戏", dataIndex: "game_name" },
              { title: "完成次数", dataIndex: "completed_count" },
              {
                title: "平均得分",
                dataIndex: "average_score",
                render: (value: number | null) => formatNumber(value),
              },
              {
                title: "平均正确率",
                dataIndex: "average_accuracy",
                render: (value: number | null) => formatPercent(value),
              },
              { title: "总错误次数", dataIndex: "total_errors" },
            ]}
          />
        </Space>
      </Card>

      <Card title="最近训练记录">
        <Table<RecentTrainingRecord>
          rowKey="id"
          dataSource={data.recent_records}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          columns={[
            {
              title: "训练时间",
              dataIndex: "trained_at",
              render: (value: string | null) => formatDateTime(value),
            },
            { title: "动作", dataIndex: "action_name" },
            {
              title: "游戏",
              dataIndex: "game_name",
              render: (value: string | null | undefined) => value ?? "—",
            },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: string) => <Tag>{TRAINING_STATUS_LABEL[value] ?? value}</Tag>,
            },
            {
              title: "得分",
              dataIndex: "score",
              render: (value: number | null | undefined) => formatNumber(value),
            },
            {
              title: "正确率",
              dataIndex: "accuracy",
              render: (value: number | null | undefined) => formatPercent(value),
            },
            {
              title: "错误次数",
              dataIndex: "error_count",
              render: (value: number | null | undefined) => value ?? "—",
            },
          ]}
        />
      </Card>
    </Space>
  );
}
