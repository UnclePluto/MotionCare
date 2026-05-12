import type { Dayjs } from "dayjs";
import dayjs from "dayjs";

/** 按「今天」公历周岁，与后端 PatientSerializer._age_from_birth 语义对齐 */
export function ageFromBirthDate(birth: Dayjs): number {
  const today = dayjs();
  let years = today.year() - birth.year();
  if (today.month() < birth.month() || (today.month() === birth.month() && today.date() < birth.date())) {
    years -= 1;
  }
  return years;
}
