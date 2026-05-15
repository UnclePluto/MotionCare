import { describe, expect, it } from "vitest";

import { formatDoctorDateTime, isValidMainlandPhone } from "./doctorUtils";

describe("doctorUtils", () => {
  it("validates mainland mobile phone numbers", () => {
    expect(isValidMainlandPhone("13812345678")).toBe(true);
    expect(isValidMainlandPhone("12812345678")).toBe(false);
    expect(isValidMainlandPhone("1381234567")).toBe(false);
  });

  it("formats date time for list display", () => {
    expect(formatDoctorDateTime("2026-05-15T10:20:00+08:00")).toBe("2026-05-15 10:20");
    expect(formatDoctorDateTime("")).toBe("—");
    expect(formatDoctorDateTime(null)).toBe("—");
    expect(formatDoctorDateTime("not-a-date")).toBe("—");
  });
});
