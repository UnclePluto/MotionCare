import dayjs from "dayjs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ageFromBirthDate } from "./ageFromBirthDate";

describe("ageFromBirthDate", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns full years before birthday this year", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-15"));
    expect(ageFromBirthDate(dayjs("2000-06-20"))).toBe(25);
  });

  it("returns full years on or after birthday this year", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-20"));
    expect(ageFromBirthDate(dayjs("2000-06-20"))).toBe(26);
  });
});
