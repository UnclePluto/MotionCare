export function parseWeeklyFrequencyTimes(value: string | null | undefined): number | null {
  if (!value) return null;
  const match = value.match(/(\d+)\s*次\s*(?:\/|每)?\s*周|每周\s*(\d+)\s*次/);
  const raw = match?.[1] ?? match?.[2];
  if (!raw) return null;
  const times = Number(raw);
  return Number.isSafeInteger(times) && times > 0 ? times : null;
}

export function formatWeeklyFrequency(times: number | null | undefined): string {
  return times ? `${times} 次/周` : "";
}

export function weeklyFrequencyLabel(value: string | null | undefined): string {
  const times = parseWeeklyFrequencyTimes(value);
  return times ? `每周 ${times} 次` : value || "—";
}
