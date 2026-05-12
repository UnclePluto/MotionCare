import { crfNameInitialsFour } from "./nameInitials";

export type PatientPrefillSource = {
  name: string;
  gender: string;
  birth_date: string | null;
  age: number | null;
};

function isEmpty(v: unknown): boolean {
  if (v === null || v === undefined) return true;
  if (typeof v === "string") return v.trim() === "";
  return false;
}

/** 仅填空：不覆盖 baseline 中已有非空值（API 层）。 */
export function mergePatientIntoBaselineApiPayload(
  patient: PatientPrefillSource,
  baselineApi: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {
    ...baselineApi,
    demographics: { ...((baselineApi.demographics as object) ?? {}) },
  };
  const demo = out.demographics as Record<string, unknown>;

  if (isEmpty(out.name_initials) && patient.name?.trim()) {
    out.name_initials = crfNameInitialsFour(patient.name);
  }
  if (isEmpty(demo.birth_date) && patient.birth_date) {
    demo.birth_date = patient.birth_date;
  }
  if (isEmpty(demo.age_years) && patient.age != null) {
    demo.age_years = patient.age;
  }
  if (isEmpty(demo.gender)) {
    if (patient.gender === "male") demo.gender = "男";
    else if (patient.gender === "female") demo.gender = "女";
  }
  return out;
}
