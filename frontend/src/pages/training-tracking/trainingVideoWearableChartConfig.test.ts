import { describe, expect, it } from "vitest";

import {
  buildTrainingVideoWearableChartConfig,
  type AvailableTrainingVideoWearableWindow,
} from "./trainingVideoWearableChartConfig";

const wearableResponse: AvailableTrainingVideoWearableWindow = {
  available: true,
  training_started_at: "2026-08-06T01:32:14Z",
  training_ended_at: "2026-08-06T01:41:27Z",
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
  it("builds one heart-rate series on the exact training time domain", () => {
    const config = buildTrainingVideoWearableChartConfig(
      "heart_rate",
      wearableResponse,
    );

    expect(config.data).toEqual([
      {
        timestamp: Date.parse("2026-08-06T01:33:00Z"),
        label: "08-06 09:33",
        series: "心率",
        value: 86,
      },
    ]);
    expect(config.scale?.x?.domainMin).toBe(
      Date.parse("2026-08-06T01:32:14Z"),
    );
    expect(config.scale?.x?.domainMax).toBe(
      Date.parse("2026-08-06T01:41:27Z"),
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
    expect(config.tooltip).toEqual({ title: { field: "label" } });
    expect(config.data[0].label).toBe("08-06 09:33");
  });
});
