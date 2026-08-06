import { formatShanghaiChartTime } from "../../utils/shanghaiTime";
import type { TrainingVideoWearableWindowResponse } from "./types";

export type AvailableTrainingVideoWearableWindow = Extract<
  TrainingVideoWearableWindowResponse,
  { available: true }
>;

export type TrainingVideoWearableMetric = keyof
  AvailableTrainingVideoWearableWindow["metrics"];

type TrainingVideoWearableChartPoint = {
  timestamp: number;
  label: string;
  series: string;
  value: number;
};

type TrainingVideoWearableChartConfig = {
  height: number;
  data: TrainingVideoWearableChartPoint[];
  xField: "timestamp";
  yField: "value";
  colorField: "series" | undefined;
  scale: {
    x: {
      type: "time";
      domainMin: number;
      domainMax: number;
    };
  };
  axis: {
    x: {
      labelFormatter: (value: number | string) => string;
    };
    y: {
      title: string;
    };
  };
  legend: { color: { title: false } } | undefined;
  tooltip: {
    title: {
      field: "label";
    };
  };
  smooth: true;
};

function buildMetricPoints(
  metric: TrainingVideoWearableMetric,
  response: AvailableTrainingVideoWearableWindow,
): TrainingVideoWearableChartPoint[] {
  if (metric === "heart_rate") {
    return (response.metrics.heart_rate?.points ?? []).map((point) => ({
      timestamp: new Date(point.measured_at).valueOf(),
      label: formatShanghaiChartTime(point.measured_at),
      series: "心率",
      value: point.value,
    }));
  }

  if (metric === "blood_pressure") {
    return (response.metrics.blood_pressure?.points ?? []).flatMap((point) => [
      {
        timestamp: new Date(point.measured_at).valueOf(),
        label: formatShanghaiChartTime(point.measured_at),
        series: "收缩压",
        value: point.systolic,
      },
      {
        timestamp: new Date(point.measured_at).valueOf(),
        label: formatShanghaiChartTime(point.measured_at),
        series: "舒张压",
        value: point.diastolic,
      },
    ]);
  }

  return (response.metrics.blood_oxygen?.points ?? []).map((point) => ({
    timestamp: new Date(point.measured_at).valueOf(),
    label: formatShanghaiChartTime(point.measured_at),
    series: "血氧",
    value: point.value,
  }));
}

export function buildTrainingVideoWearableChartConfig(
  metric: TrainingVideoWearableMetric,
  response: AvailableTrainingVideoWearableWindow,
): TrainingVideoWearableChartConfig {
  const unitByMetric = {
    heart_rate: "次/分",
    blood_pressure: "mmHg",
    blood_oxygen: "%",
  } satisfies Record<TrainingVideoWearableMetric, string>;

  return {
    height: 280,
    data: buildMetricPoints(metric, response),
    xField: "timestamp",
    yField: "value",
    colorField: metric === "blood_pressure" ? "series" : undefined,
    scale: {
      x: {
        type: "time",
        domainMin: new Date(response.training_started_at).valueOf(),
        domainMax: new Date(response.training_ended_at).valueOf(),
      },
    },
    axis: {
      x: { labelFormatter: (value) => formatShanghaiChartTime(value) },
      y: { title: unitByMetric[metric] },
    },
    legend:
      metric === "blood_pressure" ? { color: { title: false } } : undefined,
    tooltip: { title: { field: "label" } },
    smooth: true,
  };
}
