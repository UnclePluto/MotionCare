import { Line } from "@ant-design/charts";
import { Empty } from "antd";

import {
  formatShanghaiChartTime,
  formatShanghaiDate,
} from "../../utils/shanghaiTime";
import type {
  WearableDailySummaryResponse,
  WearableMeasurementResponse,
  WearableMetricType,
} from "./types";

type Props = {
  metricType: Exclude<WearableMetricType, "steps">;
  data: WearableMeasurementResponse | undefined;
};

function label(item: Record<string, string | number | null>) {
  return formatShanghaiChartTime(String(item.measured_at ?? item.start ?? ""));
}

function value(item: Record<string, string | number | null>, field: string) {
  const result = item[field];
  return typeof result === "number" ? result : null;
}

export function WearableMetricChart({ metricType, data }: Props) {
  const items = data?.items ?? [];
  if (items.length === 0) return <Empty description="所选日期暂无趋势数据" />;

  if (metricType === "blood_pressure") {
    const points = items.flatMap((item) => {
      const timestamp = label(item);
      const systolic = value(item, "systolic") ?? value(item, "systolic_avg");
      const diastolic = value(item, "diastolic") ?? value(item, "diastolic_avg");
      return [
        ...(systolic == null
          ? []
          : [{ label: timestamp, series: "收缩压", value: systolic }]),
        ...(diastolic == null
          ? []
          : [{ label: timestamp, series: "舒张压", value: diastolic }]),
      ];
    });
    return (
      <Line
        height={280}
        data={points}
        xField="label"
        yField="value"
        colorField="series"
        axis={{ y: { title: "mmHg" } }}
        legend={{ color: { title: false } }}
        smooth
      />
    );
  }

  const field = metricType === "heart_rate" ? "heart_rate" : "blood_oxygen";
  const averageField = `${field}_avg`;
  const points = items.map((item) => ({
    label: label(item),
    value: value(item, field) ?? value(item, averageField),
  }));
  return <Line height={280} data={points} xField="label" yField="value" smooth />;
}

export function WearableStepsChart({
  data,
}: {
  data: WearableDailySummaryResponse | undefined;
}) {
  const points = (data?.items ?? [])
    .filter((item) => item.steps != null)
    .map((item) => ({
      label: formatShanghaiDate(item.record_date).slice(5),
      value: item.steps,
    }));
  if (points.length === 0) {
    return <Empty description="所选日期暂无步数趋势数据" />;
  }
  return (
    <Line
      height={280}
      data={points}
      xField="label"
      yField="value"
      axis={{ y: { title: "步数" } }}
      smooth
    />
  );
}
