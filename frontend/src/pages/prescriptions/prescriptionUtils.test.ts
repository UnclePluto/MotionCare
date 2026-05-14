import { describe, expect, it } from "vitest";

import {
  formatWeeklyFrequency,
  parseWeeklyFrequencyTimes,
  weeklyFrequencyLabel,
} from "./prescriptionUtils";

describe("weekly frequency helpers", () => {
  it("parses weekly frequency strings from action defaults", () => {
    expect(parseWeeklyFrequencyTimes("3 次/周")).toBe(3);
    expect(parseWeeklyFrequencyTimes("每周 2 次")).toBe(2);
  });

  it("formats weekly frequency from numeric input", () => {
    expect(formatWeeklyFrequency(4)).toBe("4 次/周");
    expect(weeklyFrequencyLabel("4 次/周")).toBe("每周 4 次");
  });
});
