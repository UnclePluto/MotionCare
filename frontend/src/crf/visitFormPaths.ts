/** Form store keeps visit_date alongside assessments/crf, including its separate partial representation. */
export function visitRegistryStorageToFormName(storage: string): (string | number)[] | null {
  if (storage === "visit.visit_date") return ["visit_date"];
  if (storage.startsWith("visit.form_data.")) return storage.slice("visit.form_data.".length).split(".");
  if (storage.startsWith("patient_baseline.")) return storage.split(".");
  return null;
}
