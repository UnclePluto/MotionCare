import { describe, expect, it } from "vitest";

import { mergePatientIntoBaselineApiPayload } from "./baselinePrefill";

describe("mergePatientIntoBaselineApiPayload", () => {
  it("does not overwrite existing name_initials", () => {
    const base = { name_initials: "ABCD", demographics: {} };
    const r = mergePatientIntoBaselineApiPayload(
      { name: "新名字", gender: "male", birth_date: null, age: null },
      base,
    );
    expect(r.name_initials).toBe("ABCD");
  });

  it("fills name_initials when empty", () => {
    const base = { name_initials: "", demographics: {} };
    const r = mergePatientIntoBaselineApiPayload(
      { name: "王五", gender: "male", birth_date: null, age: null },
      base,
    );
    expect(typeof r.name_initials).toBe("string");
    expect((r.name_initials as string).length).toBe(4);
  });

  it("does not overwrite demographics when already set", () => {
    const base = {
      name_initials: "",
      demographics: { gender: "女", birth_date: "1990-01-01", age_years: 35 },
    };
    const r = mergePatientIntoBaselineApiPayload(
      { name: "赵六", gender: "male", birth_date: "2000-01-01", age: 99 },
      base,
    );
    expect((r.demographics as { gender: string }).gender).toBe("女");
    expect((r.demographics as { birth_date: string }).birth_date).toBe("1990-01-01");
    expect((r.demographics as { age_years: number }).age_years).toBe(35);
  });
});
