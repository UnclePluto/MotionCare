import {
  formatShanghaiChartTime,
  formatShanghaiDate,
} from "../../utils/shanghaiTime";
import type {
  WearableDailySummaryResponse,
  WearableMeasurementItem,
  WearableMeasurementResponse,
  WearableMetricType,
} from "./types";

type MetricPoint = {
  label: string;
  value: number | null;
  series?: string;
};

type LineChartConfig = {
  height: number;
  data: MetricPoint[];
  xField: "label";
  yField: "value";
  colorField?: "series";
  axis?: { y: { title: string } };
  legend?: { color: { title: false } };
  smooth: true;
};

function label(item: WearableMeasurementItem) {
  return formatShanghaiChartTime(String(item.measured_at ?? item.start ?? ""));
}

function value(item: WearableMeasurementItem, field: string) {
  const result = item[field];
  return typeof result === "number" ? result : null;
}

export function buildWearableMetricChartConfig(
  metricType: Exclude<WearableMetricType, "steps">,
  data: WearableMeasurementResponse | undefined,
): LineChartConfig {
  const items = data?.items ?? [];
  if (metricType === "blood_pressure") {
    const points = items.flatMap((item) => {
      const timestamp = label(item);
      const systolic = value(item, "systolic") ?? value(item, "systolic_avg");
      const diastolic =
        value(item, "diastolic") ?? value(item, "diastolic_avg");
      return [
        ...(systolic == null
          ? []
          : [{ label: timestamp, series: "收缩压", value: systolic }]),
        ...(diastolic == null
          ? []
          : [{ label: timestamp, series: "舒张压", value: diastolic }]),
      ];
    });
    return {
      height: 280,
      data: points,
      xField: "label",
      yField: "value",
      colorField: "series",
      axis: { y: { title: "mmHg" } },
      legend: { color: { title: false } },
      smooth: true,
    };
  }

  const field = metricType === "heart_rate" ? "heart_rate" : "blood_oxygen";
  const averageField = `${field}_avg`;
  return {
    height: 280,
    data: items.map((item) => ({
      label: label(item),
      value: value(item, field) ?? value(item, averageField),
    })),
    xField: "label",
    yField: "value",
    smooth: true,
  };
}

export function buildWearableStepsChartConfig(
  data: WearableDailySummaryResponse | undefined,
): LineChartConfig {
  return {
    height: 280,
    data: (data?.items ?? [])
      .filter((item) => item.steps != null)
      .map((item) => ({
        label: formatShanghaiDate(item.record_date).slice(5),
        value: item.steps ?? null,
      })),
    xField: "label",
    yField: "value",
    axis: { y: { title: "步数" } },
    smooth: true,
  };
}
