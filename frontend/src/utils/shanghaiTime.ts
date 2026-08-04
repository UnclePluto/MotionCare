import dayjs, { type ConfigType, type Dayjs } from "dayjs";
import timezone from "dayjs/plugin/timezone";
import utc from "dayjs/plugin/utc";

import type { WearableMetricType } from "../pages/wearables/types";

dayjs.extend(utc);
dayjs.extend(timezone);

export const SHANGHAI_TIME_ZONE = "Asia/Shanghai";

export function inShanghai(value?: ConfigType): Dayjs {
  return dayjs(value).tz(SHANGHAI_TIME_ZONE);
}

export function formatShanghaiDate(
  value: ConfigType | null | undefined,
  fallback = "—",
): string {
  if (value == null || value === "") return fallback;
  const parsed = inShanghai(value);
  return parsed.isValid() ? parsed.format("YYYY-MM-DD") : fallback;
}

export function formatShanghaiDateTime(
  value: ConfigType | null | undefined,
  fallback = "—",
): string {
  if (value == null || value === "") return fallback;
  const parsed = inShanghai(value);
  return parsed.isValid() ? parsed.format("YYYY-MM-DD HH:mm") : fallback;
}

export function formatShanghaiChartTime(
  value: ConfigType | null | undefined,
  fallback = "—",
): string {
  if (value == null || value === "") return fallback;
  const parsed = inShanghai(value);
  return parsed.isValid() ? parsed.format("MM-DD HH:mm") : fallback;
}

export function shanghaiToday(): Dayjs {
  return inShanghai().startOf("day");
}

export function shanghaiDateStart(value: string): Dayjs {
  return dayjs.tz(value, SHANGHAI_TIME_ZONE).startOf("day");
}

function shanghaiCalendarDay(value: Dayjs): Dayjs {
  return dayjs.tz(value.format("YYYY-MM-DD"), SHANGHAI_TIME_ZONE).startOf("day");
}

export function healthRangeDays(metricType: WearableMetricType): number {
  return metricType === "steps" ? 366 : 31;
}

export function isOutsideHealthRange(
  candidate: Dayjs,
  anchor: Dayjs | undefined,
  metricType: WearableMetricType,
): boolean {
  if (!anchor) return false;
  const distance = Math.abs(
    shanghaiCalendarDay(candidate).diff(shanghaiCalendarDay(anchor), "day"),
  );
  return distance >= healthRangeDays(metricType);
}

export function clampHealthDateRange(
  range: [Dayjs, Dayjs],
  metricType: WearableMetricType,
): [Dayjs, Dayjs] {
  const start = shanghaiCalendarDay(range[0]);
  const end = shanghaiCalendarDay(range[1]);
  const maxDays = healthRangeDays(metricType);
  if (end.diff(start, "day") + 1 <= maxDays) return [start, end];
  return [end.subtract(maxDays - 1, "day"), end];
}
