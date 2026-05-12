import type { RegistryField } from "./types";

export function orderBaselineTableEntries(
  entries: [string, RegistryField[]][],
  order: string[] | undefined,
): [string, RegistryField[]][] {
  if (!order?.length) {
    return [...entries].sort(([a], [b]) => a.localeCompare(b));
  }

  const byKey = new Map(entries);
  const used = new Set<string>();
  const out: [string, RegistryField[]][] = [];

  for (const key of order) {
    if (!byKey.has(key)) continue;
    out.push([key, byKey.get(key)!]);
    used.add(key);
  }

  const rest = entries
    .map(([k]) => k)
    .filter((k) => !used.has(k))
    .sort((a, b) => a.localeCompare(b));

  for (const key of rest) {
    out.push([key, byKey.get(key)!]);
  }

  return out;
}
