import dayjs from "dayjs";
import { describe, expect, it } from "vitest";

import type { WearableMetricType } from "../pages/wearables/types";
import {
  clampHealthDateRange,
  formatShanghaiChartTime,
  formatShanghaiDate,
  formatShanghaiDateTime,
  healthRangeDays,
  isOutsideHealthRange,
} from "./shanghaiTime";

describe("上海时区与穿戴日期范围", () => {
  it("把 UTC 跨日时间统一显示为上海自然日", () => {
    expect(formatShanghaiDate("2026-07-24T16:30:00Z")).toBe("2026-07-25");
    expect(formatShanghaiDateTime("2026-07-24T16:30:00Z")).toBe(
      "2026-07-25 00:30",
    );
    expect(formatShanghaiChartTime("2026-07-24T16:30:00Z")).toBe(
      "07-25 00:30",
    );
  });

  it.each<[WearableMetricType, number]>([
    ["heart_rate", 31],
    ["blood_pressure", 31],
    ["blood_oxygen", 31],
    ["steps", 366],
  ])("%s 最多允许 %s 个上海自然日", (metricType, days) => {
    expect(healthRangeDays(metricType)).toBe(days);
    const start = dayjs("2025-01-01");
    const allowedEnd = start.add(days - 1, "day");
    const rejectedEnd = start.add(days, "day");

    expect(isOutsideHealthRange(allowedEnd, start, metricType)).toBe(false);
    expect(isOutsideHealthRange(rejectedEnd, start, metricType)).toBe(true);
  });

  it("从步数切回非步数时保留结束日并收窄到 31 日", () => {
    const [start, end] = clampHealthDateRange(
      [dayjs("2025-01-01"), dayjs("2025-12-31")],
      "heart_rate",
    );

    expect(start.format("YYYY-MM-DD")).toBe("2025-12-01");
    expect(end.format("YYYY-MM-DD")).toBe("2025-12-31");
  });
});
