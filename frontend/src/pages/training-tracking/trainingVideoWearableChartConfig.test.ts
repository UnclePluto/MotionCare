import { describe, expect, it } from "vitest";

import {
  buildTrainingVideoWearableChartConfig,
  type AvailableTrainingVideoWearableWindow,
} from "./trainingVideoWearableChartConfig";

const wearableResponse: AvailableTrainingVideoWearableWindow = {
  available: true,
  window_started_at: "2026-08-06T01:32:14Z",
  window_ended_at: "2026-08-06T01:40:14Z",
  expected_duration_seconds: 180,
  buffer_seconds: 300,
  metrics: {
    heart_rate: {
      points: [{ measured_at: "2026-08-06T01:33:00Z", value: 86 }],
      statistics: { average: 86, maximum: 86, minimum: 86, count: 1 },
    },
    blood_pressure: {
      points: [
        {
          measured_at: "2026-08-06T01:34:00Z",
          systolic: 126,
          diastolic: 78,
        },
      ],
      statistics: {
        systolic: { average: 126, maximum: 126, minimum: 126 },
        diastolic: { average: 78, maximum: 78, minimum: 78 },
        count: 1,
      },
    },
    blood_oxygen: {
      points: [{ measured_at: "2026-08-06T01:35:00Z", value: 97 }],
    },
  },
};

describe("buildTrainingVideoWearableChartConfig", () => {
  it("builds one heart-rate series on the fixed health observation window", () => {
    const config = buildTrainingVideoWearableChartConfig(
      "heart_rate",
      wearableResponse,
    );

    expect(config.data).toEqual([
      {
        timestamp: Date.parse("2026-08-06T01:33:00Z"),
        label: "2026-08-06 09:33:00",
        series: "心率",
        value: 86,
      },
    ]);
    expect(config.scale?.x?.domainMin).toBe(
      Date.parse("2026-08-06T01:32:14Z"),
    );
    expect(config.scale?.x?.domainMax).toBe(
      Date.parse("2026-08-06T01:40:14Z"),
    );
    expect(config.axis?.y?.title).toBe("次/分");
  });

  it("builds paired systolic and diastolic series", () => {
    const config = buildTrainingVideoWearableChartConfig(
      "blood_pressure",
      wearableResponse,
    );

    expect(config.data.map((point) => point.series)).toEqual([
      "收缩压",
      "舒张压",
    ]);
    expect(config.legend).toEqual({ color: { title: false } });
    expect(config.axis?.y?.title).toBe("mmHg");
  });

  it("uses percent as the blood-oxygen unit", () => {
    const config = buildTrainingVideoWearableChartConfig(
      "blood_oxygen",
      wearableResponse,
    );

    expect(config.axis?.y?.title).toBe("%");
    expect(config.data).toEqual([
      expect.objectContaining({ series: "血氧", value: 97 }),
    ]);
  });

  it("formats chart axis and tooltip labels in Shanghai time", () => {
    const config = buildTrainingVideoWearableChartConfig(
      "heart_rate",
      wearableResponse,
    );

    expect(config.axis?.x.labelFormatter("2026-08-06T01:33:00Z")).toBe(
      "08-06 09:33",
    );
    expect(config.tooltip.title).toEqual({ field: "label" });
    expect(config.data[0].label).toBe("2026-08-06 09:33:00");
  });

  it("keeps same-minute tooltip titles distinct down to seconds", () => {
    const config = buildTrainingVideoWearableChartConfig("heart_rate", {
      ...wearableResponse,
      metrics: {
        heart_rate: {
          points: [
            { measured_at: "2026-08-06T01:33:05Z", value: 86 },
            { measured_at: "2026-08-06T01:33:45Z", value: 88 },
          ],
          statistics: {
            average: 87,
            maximum: 88,
            minimum: 86,
            count: 2,
          },
        },
      },
    });

    expect(config.data.map((point) => point.label)).toEqual([
      "2026-08-06 09:33:05",
      "2026-08-06 09:33:45",
    ]);
  });

  it.each([
    {
      metric: "heart_rate" as const,
      pointIndex: 0,
      expected: { name: "心率（次/分）", value: "86 次/分" },
    },
    {
      metric: "blood_pressure" as const,
      pointIndex: 0,
      expected: { name: "收缩压（mmHg）", value: "126 mmHg" },
    },
    {
      metric: "blood_pressure" as const,
      pointIndex: 1,
      expected: { name: "舒张压（mmHg）", value: "78 mmHg" },
    },
    {
      metric: "blood_oxygen" as const,
      pointIndex: 0,
      expected: { name: "血氧（%）", value: "97%" },
    },
  ])(
    "labels $metric tooltip values with the metric name and unit",
    ({ metric, pointIndex, expected }) => {
      const config = buildTrainingVideoWearableChartConfig(
        metric,
        wearableResponse,
      );

      expect(config.tooltip.items[0](config.data[pointIndex])).toEqual(
        expected,
      );
    },
  );
});
