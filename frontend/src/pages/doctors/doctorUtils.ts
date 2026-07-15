import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";

import type { DoctorGender } from "./types";

dayjs.extend(utc);

export const doctorGenderLabel: Record<DoctorGender, string> = {
  male: "男",
  female: "女",
  unknown: "未知",
};

export function isValidMainlandPhone(value: string): boolean {
  return /^1[3-9]\d{9}$/.test(value.trim());
}

export function formatDoctorDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = dayjs(value);
  return d.isValid() ? d.utcOffset(8).format("YYYY-MM-DD HH:mm") : "—";
}
