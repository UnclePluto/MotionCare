import { describe, expect, it } from "vitest";

import type { WearableMeasurementResponse } from "./types";
import {
  buildWearableMetricChartConfig,
  buildWearableStepsChartConfig,
} from "./wearableMetricChartConfig";

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

    const rangeStart = Date.UTC(2026, 6, 24, 16);
    const rangeEnd = Date.UTC(2026, 6, 25, 16);

    expect(config.xField).toBe("timestamp");
    expect(config.scale?.x).toEqual({
      type: "time",
      domainMin: rangeStart,
      domainMax: rangeEnd,
    });
    expect(config.axis?.x?.labelFormatter(rangeStart)).toBe("07-25 00:00");
    expect(config.axis?.x?.labelFormatter(rangeEnd)).toBe("07-25 24:00");
    expect(config.yField).toBe("value");
    expect(config.colorField).toBe("series");
    expect(config.axis?.y?.title).toBe("mmHg");
    expect(config.data.map((point) => point.series)).toContain("收缩压");
    expect(config.data.map((point) => point.series)).toContain("舒张压");
    expect(config.data).toEqual([
      {
        timestamp: Date.parse("2026-07-24T16:30:00Z"),
        label: "07-25 00:30",
        series: "收缩压",
        value: 120,
      },
      {
        timestamp: Date.parse("2026-07-24T16:30:00Z"),
        label: "07-25 00:30",
        series: "舒张压",
        value: 80,
      },
      {
        timestamp: Date.parse("2026-07-24T17:00:00Z"),
        label: "07-25 01:00",
        series: "收缩压",
        value: 126,
      },
      {
        timestamp: Date.parse("2026-07-24T17:00:00Z"),
        label: "07-25 01:00",
        series: "舒张压",
        value: 84,
      },
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
    expect(heartRateConfig.tooltip).toEqual({
      title: { field: "label" },
      items: [{ field: "value", name: "心率" }],
    });
    expect(heartRateConfig.data).toEqual([
      {
        timestamp: Date.parse("2026-07-24T16:30:00Z"),
        label: "07-25 00:30",
        value: 72,
      },
    ]);
    expect(bloodOxygenConfig.colorField).toBeUndefined();
    expect(bloodOxygenConfig.tooltip).toEqual({
      title: { field: "label" },
      items: [{ field: "value", name: "血氧" }],
    });
    expect(bloodOxygenConfig.data).toEqual([
      {
        timestamp: Date.parse("2026-07-24T16:30:00Z"),
        label: "07-25 00:30",
        value: 98,
      },
    ]);
  });

  it("为步数配置全天时间轴和业务名称 Tooltip", () => {
    const stepsConfig = buildWearableStepsChartConfig({
      start: "2026-07-25",
      end: "2026-07-25",
      items: [{ record_date: "2026-07-25", steps: 6000 }],
    });

    expect(stepsConfig.xField).toBe("timestamp");
    expect(stepsConfig.scale?.x).toEqual({
      type: "time",
      domainMin: Date.UTC(2026, 6, 24, 16),
      domainMax: Date.UTC(2026, 6, 25, 16),
    });
    expect(stepsConfig.tooltip).toEqual({
      title: { field: "label" },
      items: [{ field: "value", name: "步数" }],
    });
  });

  it("多日趋势使用实际数据范围，避免有数据曲线被压缩在左侧", () => {
    const config = buildWearableMetricChartConfig("heart_rate", {
      metric_type: "heart_rate",
      bucket: "raw",
      start: "2026-07-28",
      end: "2026-08-03",
      total: 2,
      page: 1,
      page_size: 500,
      next_page: null,
      items: [
        { measured_at: "2026-07-27T18:03:57Z", heart_rate: 90 },
        { measured_at: "2026-07-28T03:25:49Z", heart_rate: 100 },
      ],
    });

    expect(config.scale?.x).toBeUndefined();
  });

  it("多日步数全为零时使用正常步数刻度，不显示成 0 到 1", () => {
    const config = buildWearableStepsChartConfig({
      start: "2026-07-28",
      end: "2026-08-03",
      items: [
        { record_date: "2026-07-28", steps: 0 },
        { record_date: "2026-07-29", steps: 0 },
      ],
    });

    expect(config.xField).toBe("label");
    expect(config.scale?.x).toBeUndefined();
    expect(config.scale?.y).toEqual({
      domainMin: 0,
      domainMax: 1000,
    });
    expect(config.data.map((point) => point.label)).toEqual([
      "07-28",
      "07-29",
    ]);
  });

  it.each([
    { minimum: 99, expectedMin: 90, expectedTicks: [90, 95, 100] },
    { minimum: 96, expectedMin: 90, expectedTicks: [90, 95, 100] },
    { minimum: 92, expectedMin: 85, expectedTicks: [85, 90, 95, 100] },
  ])(
    "血氧最低值 $minimum 时下界为 $expectedMin",
    ({ minimum, expectedMin, expectedTicks }) => {
      const config = buildWearableMetricChartConfig("blood_oxygen", {
        metric_type: "blood_oxygen",
        bucket: "raw",
        start: "2026-07-28",
        end: "2026-07-28",
        total: 1,
        page: 1,
        page_size: 500,
        next_page: null,
        items: [
          {
            measured_at: "2026-07-27T18:00:00Z",
            blood_oxygen: minimum,
          },
        ],
      });

      expect(config.scale?.y).toEqual({
        domainMin: expectedMin,
        domainMax: 100,
        nice: false,
      });
      expect(config.axis?.y?.tickMethod?.(expectedMin, 100, 5)).toEqual(
        expectedTicks,
      );
    },
  );

  it("血氧接近零时纵轴下界不小于零", () => {
    const config = buildWearableMetricChartConfig("blood_oxygen", {
      metric_type: "blood_oxygen",
      bucket: "raw",
      start: "2026-07-28",
      end: "2026-07-28",
      total: 1,
      page: 1,
      page_size: 500,
      next_page: null,
      items: [
        { measured_at: "2026-07-27T18:00:00Z", blood_oxygen: 3 },
      ],
    });

    expect(config.scale?.y?.domainMin).toBe(0);
    expect(config.axis?.y?.tickMethod?.(0, 100, 5)).toEqual([
      0, 25, 50, 75, 100,
    ]);
  });

  it("血氧没有有限数值时不设置强制纵轴", () => {
    const config = buildWearableMetricChartConfig("blood_oxygen", {
      metric_type: "blood_oxygen",
      bucket: "raw",
      start: "2026-07-28",
      end: "2026-07-28",
      total: 2,
      page: 1,
      page_size: 500,
      next_page: null,
      items: [
        { measured_at: "2026-07-27T18:00:00Z", blood_oxygen: Number.NaN },
        {
          measured_at: "2026-07-27T19:00:00Z",
          blood_oxygen: Number.POSITIVE_INFINITY,
        },
      ],
    });

    expect(config.scale?.y).toBeUndefined();
  });

  it("血氧纵轴忽略非有限数值", () => {
    const config = buildWearableMetricChartConfig("blood_oxygen", {
      metric_type: "blood_oxygen",
      bucket: "raw",
      start: "2026-07-28",
      end: "2026-07-28",
      total: 3,
      page: 1,
      page_size: 500,
      next_page: null,
      items: [
        { measured_at: "2026-07-27T18:00:00Z", blood_oxygen: 96 },
        { measured_at: "2026-07-27T19:00:00Z", blood_oxygen: Number.NaN },
        {
          measured_at: "2026-07-27T20:00:00Z",
          blood_oxygen: Number.NEGATIVE_INFINITY,
        },
      ],
    });

    expect(config.scale?.y).toEqual({
      domainMin: 90,
      domainMax: 100,
      nice: false,
    });
  });
});
