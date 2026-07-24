import { describe, expect, it } from "vitest";

import type { WearableMeasurementResponse } from "./types";
import { buildWearableMetricChartConfig } from "./wearableMetricChartConfig";

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

describe("buildWearableMetricChartConfig", () => {
  it("为血压生成单个共享 mmHg 轴的长格式双线配置", () => {
    const config = buildWearableMetricChartConfig(
      "blood_pressure",
      rawResponse([
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
      ]),
    );

    expect(config.yField).toBe("value");
    expect(config.colorField).toBe("series");
    expect(config.axis?.y.title).toBe("mmHg");
    expect(config.data).toEqual([
      { label: "07-25 00:30", series: "收缩压", value: 120 },
      { label: "07-25 00:30", series: "舒张压", value: 80 },
      { label: "07-25 01:00", series: "收缩压", value: 126 },
      { label: "07-25 01:00", series: "舒张压", value: 84 },
    ]);
  });

  it("为心率与血氧生成没有 series 维度的单线配置", () => {
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
    const heartRateConfig = buildWearableMetricChartConfig(
      "heart_rate",
      response,
    );
    const bloodOxygenConfig = buildWearableMetricChartConfig(
      "blood_oxygen",
      {
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
      },
    );

    expect(heartRateConfig.colorField).toBeUndefined();
    expect(heartRateConfig.data).toEqual([
      { label: "07-25 00:30", value: 72 },
    ]);
    expect(bloodOxygenConfig.colorField).toBeUndefined();
    expect(bloodOxygenConfig.data).toEqual([
      { label: "07-25 00:30", value: 98 },
    ]);
  });
});
