/** `patient_baseline.demographics.x` → `['demographics','x']`；`subject_id` → `['subject_id']` */
export function baselineStorageToFormName(storage: string): (string | number)[] | null {
  if (!storage.startsWith("patient_baseline.")) return null;
  const tail = storage.slice("patient_baseline.".length);
  if (!tail) return null;
  return tail.split(".");
}
