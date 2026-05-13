export type RandomGroupInput = { id: number; target_ratio: number };
export type LocalAssignment = { patientId: number; groupId: number };

export function balancePercents(groupIds: number[]): Record<number, number> {
  if (!groupIds.length) return {};
  const base = Math.floor(100 / groupIds.length);
  const remainder = 100 - base * groupIds.length;
  return Object.fromEntries(groupIds.map((id, index) => [id, base + (index < remainder ? 1 : 0)]));
}

export function getPercentValidationError(percents: number[]): string | null {
  if (!percents.length) return "没有启用分组，不能确认分组。";
  if (percents.some((percent) => !Number.isFinite(percent) || !Number.isInteger(percent) || percent <= 0)) {
    return "每个启用组占比必须为大于 0 的整数。";
  }
  const total = percents.reduce((sum, percent) => sum + percent, 0);
  if (total !== 100) return `启用组占比合计须为 100%，当前为 ${total}%。`;
  return null;
}

export function groupsWithDraftPercents(
  groups: RandomGroupInput[],
  percentByGroupId: Record<number, number>,
): RandomGroupInput[] {
  return groups.map((group) => ({
    ...group,
    target_ratio: percentByGroupId[group.id] ?? group.target_ratio,
  }));
}

function seededRandom(seed: number) {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shufflePatientIds(patientIds: number[], random: () => number): number[] {
  const shuffled = [...patientIds];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

function pickFractionIndex(fractions: number[], random: () => number): number {
  const totalFraction = fractions.reduce((sum, fraction) => sum + fraction, 0);
  if (totalFraction <= 0) return -1;

  let threshold = random() * totalFraction;
  for (let index = 0; index < fractions.length; index++) {
    threshold -= fractions[index];
    if (threshold <= 0) return index;
  }
  for (let index = fractions.length - 1; index >= 0; index--) {
    if (fractions[index] > 0) return index;
  }
  return -1;
}

function calculateGroupCounts(totalPatients: number, groups: RandomGroupInput[], random: () => number): number[] {
  const totalRatio = groups.reduce((sum, g) => sum + g.target_ratio, 0);
  const exact = groups.map((g) => (totalPatients * g.target_ratio) / totalRatio);
  const counts = exact.map((value) => Math.floor(value));
  const remainder = totalPatients - counts.reduce((sum, count) => sum + count, 0);
  const fractions = exact.map((value) => value - Math.floor(value));

  for (let i = 0; i < remainder; i++) {
    const index = pickFractionIndex(fractions, random);
    if (index === -1) break;
    counts[index] += 1;
    fractions[index] = 0;
  }

  return counts;
}

export function assignPatientsToGroups(
  patientIds: number[],
  groups: RandomGroupInput[],
  seed = Date.now(),
): LocalAssignment[] {
  if (!groups.length) throw new Error("没有启用分组，不能随机分组");
  if (groups.some((g) => g.target_ratio <= 0)) throw new Error("分组比例必须大于 0");

  const random = seededRandom(seed);
  const shuffled = shufflePatientIds(patientIds, random);
  const counts = calculateGroupCounts(shuffled.length, groups, random);
  let cursor = 0;
  const result: LocalAssignment[] = [];

  groups.forEach((group, index) => {
    const count = counts[index];
    for (const patientId of shuffled.slice(cursor, cursor + count)) {
      result.push({ patientId, groupId: group.id });
    }
    cursor += count;
  });

  return result;
}
