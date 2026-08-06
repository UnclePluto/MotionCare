import { Line } from "@ant-design/charts";
import {
  Space,
  Table,
  Tabs,
  Typography,
  type TableColumnsType,
} from "antd";
import { useMemo } from "react";

import {
  buildTrainingVideoWearableChartConfig,
  type AvailableTrainingVideoWearableWindow,
  type TrainingVideoWearableMetric,
} from "./trainingVideoWearableChartConfig";
import type { TrainingVideoWearableWindowResponse } from "./types";

const METRIC_ORDER: TrainingVideoWearableMetric[] = [
  "heart_rate",
  "blood_pressure",
  "blood_oxygen",
];

const METRIC_LABEL: Record<TrainingVideoWearableMetric, string> = {
  heart_rate: "心率",
  blood_pressure: "血压",
  blood_oxygen: "血氧",
};

type StatisticRow = {
  metric: "heart_rate" | "systolic" | "diastolic";
  label: string;
  average: number;
  maximum: number;
  minimum: number;
  count: number;
};

type Props = {
  data?: TrainingVideoWearableWindowResponse;
};

function hasMetricPoints(
  metrics: AvailableTrainingVideoWearableWindow["metrics"],
  metric: TrainingVideoWearableMetric,
): boolean {
  return (metrics[metric]?.points.length ?? 0) > 0;
}

function buildStatisticRows(
  metrics: AvailableTrainingVideoWearableWindow["metrics"],
): StatisticRow[] {
  const rows: StatisticRow[] = [];
  const heartRate = metrics.heart_rate;
  const bloodPressure = metrics.blood_pressure;

  if (heartRate && hasMetricPoints(metrics, "heart_rate")) {
    rows.push({
      metric: "heart_rate",
      label: "心率（次/分）",
      ...heartRate.statistics,
    });
  }

  if (bloodPressure && hasMetricPoints(metrics, "blood_pressure")) {
    rows.push({
      metric: "systolic",
      label: "收缩压（mmHg）",
      ...bloodPressure.statistics.systolic,
      count: bloodPressure.statistics.count,
    });
    rows.push({
      metric: "diastolic",
      label: "舒张压（mmHg）",
      ...bloodPressure.statistics.diastolic,
      count: bloodPressure.statistics.count,
    });
  }

  return rows;
}

const STATISTIC_COLUMNS: TableColumnsType<StatisticRow> = [
  { title: "指标", dataIndex: "label" },
  { title: "平均", dataIndex: "average" },
  { title: "最高", dataIndex: "maximum" },
  { title: "最低", dataIndex: "minimum" },
  { title: "测量次数", dataIndex: "count" },
];

function AvailableTrainingVideoWearablePanel({
  data,
}: {
  data: AvailableTrainingVideoWearableWindow;
}) {
  const metricTabs = useMemo(
    () =>
      METRIC_ORDER.flatMap((metric) =>
        hasMetricPoints(data.metrics, metric)
          ? [
              {
                key: metric,
                label: METRIC_LABEL[metric],
                children: (
                  <Line
                    {...buildTrainingVideoWearableChartConfig(metric, data)}
                  />
                ),
              },
            ]
          : [],
      ),
    [data],
  );
  const rows = useMemo(() => buildStatisticRows(data.metrics), [data.metrics]);

  if (metricTabs.length === 0) return null;

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Typography.Title level={5}>训练时段穿戴趋势</Typography.Title>
      <Tabs items={metricTabs} />
      {rows.length > 0 ? (
        <>
          <Typography.Title level={5}>训练时段统计</Typography.Title>
          <Table
            rowKey="metric"
            columns={STATISTIC_COLUMNS}
            dataSource={rows}
            pagination={false}
            size="small"
          />
        </>
      ) : null}
    </Space>
  );
}

export function TrainingVideoWearablePanel({ data }: Props) {
  if (!data?.available) return null;
  return <AvailableTrainingVideoWearablePanel data={data} />;
}
