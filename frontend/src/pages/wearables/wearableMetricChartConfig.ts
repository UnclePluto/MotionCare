import {
  formatShanghaiChartTime,
  formatShanghaiDate,
  inShanghai,
  shanghaiDateStart,
} from "../../utils/shanghaiTime";
import type {
  WearableDailySummaryResponse,
  WearableMeasurementItem,
  WearableMeasurementResponse,
  WearableMetricType,
} from "./types";

type MetricPoint = {
  timestamp: number;
  label: string;
  value: number | null;
  series?: string;
};

type LineChartConfig = {
  height: number;
  data: MetricPoint[];
  xField: "timestamp" | "label";
  yField: "value";
  colorField?: "series";
  scale?: {
    x?: {
      type: "time";
      domainMin: number;
      domainMax: number;
    };
    y?: {
      domainMin: number;
      domainMax: number;
      nice?: boolean;
    };
  };
  axis?: {
    x: { labelFormatter: (value: number | string) => string };
    y?: {
      title?: string;
      tickMethod?: (
        start: number | Date,
        end: number | Date,
        tickCount: number,
      ) => number[];
    };
  };
  legend?: { color: { title: false } };
  tooltip?: {
    title?: { field: "label" };
    items?: Array<{ field: "value"; name: string }>;
  };
  smooth: true;
};

function label(item: WearableMeasurementItem) {
  return formatShanghaiChartTime(String(item.measured_at ?? item.start ?? ""));
}

function value(item: WearableMeasurementItem, field: string) {
  const result = item[field];
  return typeof result === "number" ? result : null;
}

function timestamp(item: WearableMeasurementItem) {
  return inShanghai(
    String(item.measured_at ?? item.start ?? ""),
  ).valueOf();
}

function timeRange(start: string | undefined, end: string | undefined) {
  if (!start || !end || start !== end) return undefined;
  return {
    x: {
      type: "time" as const,
      domainMin: shanghaiDateStart(start).valueOf(),
      domainMax: shanghaiDateStart(end).add(1, "day").valueOf(),
    },
  };
}

function bloodOxygenScale(values: Array<number | null>) {
  const validValues = values.filter(
    (item): item is number => typeof item === "number" && Number.isFinite(item),
  );
  if (validValues.length === 0) return undefined;
  const minimum = Math.min(...validValues);
  return {
    y: {
      domainMin: Math.max(0, Math.floor((minimum - 5) / 5) * 5),
      domainMax: 100,
      nice: false,
    },
  };
}

function bloodOxygenTicks(
  start: number | Date,
  end: number | Date,
  tickCount: number,
) {
  const minimum = Number(start);
  const maximum = Number(end);
  if (
    !Number.isFinite(minimum) ||
    !Number.isFinite(maximum) ||
    minimum > maximum
  ) {
    return [];
  }
  if (minimum === maximum) return [minimum];

  const count = Number.isFinite(tickCount)
    ? Math.max(2, Math.floor(tickCount))
    : 5;
  const rawStep = (maximum - minimum) / (count - 1);
  const step = Math.max(5, Math.ceil(rawStep / 5) * 5);
  const ticks = [minimum];
  let tick = Math.ceil(minimum / step) * step;
  if (Math.abs(tick - minimum) < step * 1e-10) tick += step;
  for (; tick < maximum; tick += step) {
    ticks.push(Number(tick.toPrecision(12)));
  }
  ticks.push(maximum);
  return ticks;
}

function timeAxis(start: string | undefined, end: string | undefined) {
  const singleDayEnd =
    start && end && start === end
      ? shanghaiDateStart(end).add(1, "day").valueOf()
      : null;
  return {
    labelFormatter: (value: number | string) =>
      singleDayEnd != null && Number(value) === singleDayEnd
        ? `${formatShanghaiDate(end!).slice(5)} 24:00`
        : formatShanghaiChartTime(value),
  };
}

export function buildWearableMetricChartConfig(
  metricType: Exclude<WearableMetricType, "steps">,
  data: WearableMeasurementResponse | undefined,
): LineChartConfig {
  const items = data?.items ?? [];
  if (metricType === "blood_pressure") {
    const points = items.flatMap((item) => {
      const pointTimestamp = timestamp(item);
      const pointLabel = label(item);
      const systolic = value(item, "systolic") ?? value(item, "systolic_avg");
      const diastolic =
        value(item, "diastolic") ?? value(item, "diastolic_avg");
      return [
        ...(systolic == null
          ? []
          : [{
              timestamp: pointTimestamp,
              label: pointLabel,
              series: "收缩压",
              value: systolic,
            }]),
        ...(diastolic == null
          ? []
          : [{
              timestamp: pointTimestamp,
              label: pointLabel,
              series: "舒张压",
              value: diastolic,
            }]),
      ];
    });
    return {
      height: 280,
      data: points,
      xField: "timestamp",
      yField: "value",
      colorField: "series",
      scale: timeRange(data?.start, data?.end),
      axis: {
        x: timeAxis(data?.start, data?.end),
        y: { title: "mmHg" },
      },
      legend: { color: { title: false } },
      tooltip: { title: { field: "label" } },
      smooth: true,
    };
  }

  const field = metricType === "heart_rate" ? "heart_rate" : "blood_oxygen";
  const averageField = `${field}_avg`;
  const metricName = metricType === "heart_rate" ? "心率" : "血氧";
  const points = items.map((item) => ({
    timestamp: timestamp(item),
    label: label(item),
    value: value(item, field) ?? value(item, averageField),
  }));
  const xScale = timeRange(data?.start, data?.end);
  const yScale =
    metricType === "blood_oxygen"
      ? bloodOxygenScale(points.map((point) => point.value))
      : undefined;
  const scale =
    xScale || yScale
      ? { ...xScale, ...yScale }
      : undefined;
  return {
    height: 280,
    data: points,
    xField: "timestamp",
    yField: "value",
    scale,
    axis: {
      x: timeAxis(data?.start, data?.end),
      ...(metricType === "blood_oxygen"
        ? { y: { tickMethod: bloodOxygenTicks } }
        : {}),
    },
    tooltip: {
      title: { field: "label" },
      items: [{ field: "value", name: metricName }],
    },
    smooth: true,
  };
}

export function buildWearableStepsChartConfig(
  data: WearableDailySummaryResponse | undefined,
): LineChartConfig {
  const items = data?.items ?? [];
  const stepValues = items.flatMap((item) =>
    typeof item.steps === "number" ? [item.steps] : [],
  );
  const xScale = timeRange(data?.start, data?.end);
  const allStepsAreZero =
    stepValues.length > 0 && stepValues.every((steps) => steps === 0);
  const singleDay =
    data?.start != null && data.end != null && data.start === data.end;
  const scale =
    xScale || allStepsAreZero
      ? {
          ...xScale,
          ...(allStepsAreZero
            ? { y: { domainMin: 0, domainMax: 1000 } }
            : {}),
        }
      : undefined;
  return {
    height: 280,
    data: items
      .filter((item) => item.steps != null)
      .map((item) => ({
        timestamp: shanghaiDateStart(item.record_date).valueOf(),
        label: formatShanghaiDate(item.record_date).slice(5),
        value: item.steps ?? null,
      })),
    xField: singleDay ? "timestamp" : "label",
    yField: "value",
    scale,
    axis: {
      x: singleDay
        ? timeAxis(data?.start, data?.end)
        : { labelFormatter: (value) => String(value) },
      y: { title: "步数" },
    },
    tooltip: {
      title: { field: "label" },
      items: [{ field: "value", name: "步数" }],
    },
    smooth: true,
  };
}
