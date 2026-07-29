import { Line } from "@ant-design/charts";
import { Empty } from "antd";

import type {
  WearableDailySummaryResponse,
  WearableMeasurementResponse,
  WearableMetricType,
} from "./types";
import {
  buildWearableMetricChartConfig,
  buildWearableStepsChartConfig,
} from "./wearableMetricChartConfig";

type Props = {
  metricType: Exclude<WearableMetricType, "steps">;
  data: WearableMeasurementResponse | undefined;
};

export function WearableMetricChart({ metricType, data }: Props) {
  const items = data?.items ?? [];
  if (items.length === 0) return <Empty description="所选日期暂无趋势数据" />;
  return <Line {...buildWearableMetricChartConfig(metricType, data)} />;
}

export function WearableStepsChart({
  data,
}: {
  data: WearableDailySummaryResponse | undefined;
}) {
  const config = buildWearableStepsChartConfig(data);
  if (config.data.length === 0) {
    return <Empty description="所选日期暂无步数趋势数据" />;
  }
  return <Line {...config} />;
}
