import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WearableMetricChart } from "./WearableMetricChart";
import type { WearableMeasurementResponse } from "./types";

vi.mock("@ant-design/charts", () => ({
  DualAxes: (props: Record<string, unknown>) => (
    <pre data-testid="dual-axes-config">{JSON.stringify(props)}</pre>
  ),
  Line: (props: Record<string, unknown>) => (
    <pre data-testid="line-config">{JSON.stringify(props)}</pre>
  ),
}));

function rawResponse(
  items: WearableMeasurementResponse["items"],
): WearableMeasurementResponse {
  return {
    metric_type: "blood_pressure",
    bucket: "raw",
    start: "2026-07-25",
    end: "2026-07-25",
    total: items.length,
    page: 1,
    page_size: 500,
    next_page: null,
    items,
  };
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("WearableMetricChart", () => {
  it("用单个共享 mmHg 轴的 Line 绘制血压长格式双线", () => {
    render(
      <WearableMetricChart
        metricType="blood_pressure"
        data={rawResponse([
          {
            measured_at: "2026-07-24T16:30:00Z",
            systolic: 120,
            diastolic: 80,
          },
          {
            measured_at: "2026-07-24T17:00:00Z",
            systolic: 126,
            diastolic: 84,
          },
        ])}
      />,
    );

    expect(screen.queryByTestId("dual-axes-config")).not.toBeInTheDocument();
    const config = JSON.parse(screen.getByTestId("line-config").textContent ?? "{}");
    expect(config.yField).toBe("value");
    expect(config.colorField).toBe("series");
    expect(config.axis.y.title).toBe("mmHg");
    expect(config.data).toEqual([
      { label: "07-25 00:30", series: "收缩压", value: 120 },
      { label: "07-25 00:30", series: "舒张压", value: 80 },
      { label: "07-25 01:00", series: "收缩压", value: 126 },
      { label: "07-25 01:00", series: "舒张压", value: 84 },
    ]);
  });

  it("心率与血氧仍使用没有 series 维度的单线", () => {
    const response: WearableMeasurementResponse = {
      metric_type: "heart_rate",
      bucket: "5m",
      start: "2026-07-25",
      end: "2026-07-25",
      items: [
        {
          start: "2026-07-24T16:30:00Z",
          end: "2026-07-24T16:35:00Z",
          count: 2,
          heart_rate_avg: 72,
        },
      ],
    };
    const { rerender } = render(
      <WearableMetricChart metricType="heart_rate" data={response} />,
    );
    let config = JSON.parse(screen.getByTestId("line-config").textContent ?? "{}");
    expect(config.colorField).toBeUndefined();
    expect(config.data).toEqual([{ label: "07-25 00:30", value: 72 }]);

    rerender(
      <WearableMetricChart
        metricType="blood_oxygen"
        data={{
          ...response,
          metric_type: "blood_oxygen",
          items: [
            {
              start: "2026-07-24T16:30:00Z",
              end: "2026-07-24T16:35:00Z",
              count: 1,
              blood_oxygen_avg: 98,
            },
          ],
        }}
      />,
    );
    config = JSON.parse(screen.getByTestId("line-config").textContent ?? "{}");
    expect(config.colorField).toBeUndefined();
    expect(config.data).toEqual([{ label: "07-25 00:30", value: 98 }]);
  });
});
