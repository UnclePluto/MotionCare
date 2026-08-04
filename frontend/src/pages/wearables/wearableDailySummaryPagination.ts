import type { Dayjs } from "dayjs";

import { inShanghai, shanghaiDateStart } from "../../utils/shanghaiTime";
import type {
  WearableDailySummary,
  WearableDailySummaryResponse,
} from "./types";

export type DailySummaryWindow = {
  start: string;
  end: string;
};

function bindingDay(boundAt: string): Dayjs {
  return inShanghai(boundAt).startOf("day");
}

function effectiveBindingDay(boundAt: string, end: Dayjs): Dayjs {
  const bound = bindingDay(boundAt);
  return bound.isAfter(end, "day") ? end : bound;
}

function windowEndingAt(end: Dayjs, boundAt: string): DailySummaryWindow {
  const normalizedEnd = end.startOf("day");
  const bound = effectiveBindingDay(boundAt, normalizedEnd);
  const candidateStart = normalizedEnd.subtract(4, "day");
  const start = candidateStart.isBefore(bound, "day") ? bound : candidateStart;

  return {
    start: start.format("YYYY-MM-DD"),
    end: normalizedEnd.format("YYYY-MM-DD"),
  };
}

export function firstDailySummaryWindow(
  boundAt: string,
  today: Dayjs,
): DailySummaryWindow {
  return windowEndingAt(today, boundAt);
}

export function nextDailySummaryWindow(
  current: DailySummaryWindow,
  boundAt: string,
): DailySummaryWindow | null {
  const currentStart = shanghaiDateStart(current.start);
  const previousEnd = currentStart.subtract(1, "day");
  const bound = bindingDay(boundAt);

  if (previousEnd.isBefore(bound, "day")) return null;
  return windowEndingAt(previousEnd, boundAt);
}

export function mergeDailySummaryPages(
  pages: WearableDailySummaryResponse[],
): WearableDailySummary[] {
  const byDate = new Map<string, WearableDailySummary>();

  for (const page of pages) {
    for (const item of page.items) {
      if (!byDate.has(item.record_date)) {
        byDate.set(item.record_date, item);
      }
    }
  }

  return [...byDate.values()].sort((left, right) =>
    right.record_date.localeCompare(left.record_date),
  );
}
