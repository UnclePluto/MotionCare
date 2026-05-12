/** `visit.form_data.assessments.*` → `['assessments', ...]`；`visit.form_data.crf.*` → `['crf', ...]` */
export function visitRegistryStorageToFormName(storage: string): (string | number)[] | null {
  if (storage.startsWith("visit.form_data.assessments.")) {
    return ["assessments", ...storage.slice("visit.form_data.assessments.".length).split(".")];
  }
  if (storage.startsWith("visit.form_data.crf.")) {
    return ["crf", ...storage.slice("visit.form_data.crf.".length).split(".")];
  }
  return null;
}
