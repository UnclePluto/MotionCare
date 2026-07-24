import { DualAxes, Line } from "@ant-design/charts";
import { Empty } from "antd";

import type { WearableMeasurementResponse, WearableMetricType } from "./types";

type Props = {
  metricType: Exclude<WearableMetricType, "steps">;
  data: WearableMeasurementResponse | undefined;
};

function label(item: Record<string, string | number | null>) {
  return String(item.measured_at ?? item.start ?? "");
}

function value(item: Record<string, string | number | null>, field: string) {
  const result = item[field];
  return typeof result === "number" ? result : null;
}

export function WearableMetricChart({ metricType, data }: Props) {
  const items = data?.items ?? [];
  if (items.length === 0) return <Empty description="所选日期暂无趋势数据" />;

  if (metricType === "blood_pressure") {
    const points = items.map((item) => ({
      label: label(item),
      systolic: value(item, "systolic") ?? value(item, "systolic_avg"),
      diastolic: value(item, "diastolic") ?? value(item, "diastolic_avg"),
    }));
    return (
      <DualAxes
        height={280}
        data={[points, points]}
        xField="label"
        children={[
          { type: "line", yField: "systolic", style: { stroke: "#1677ff" } },
          { type: "line", yField: "diastolic", style: { stroke: "#52c41a" } },
        ]}
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
