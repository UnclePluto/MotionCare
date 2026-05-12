/** 最大公约数（全为非负整数；至少一项为 0 时返回另一项）。 */
function gcdPair(a: number, b: number): number {
  let x = Math.abs(Math.trunc(a));
  let y = Math.abs(Math.trunc(b));
  while (y !== 0) {
    const t = y;
    y = x % y;
    x = t;
  }
  return x || 1;
}

function gcdMany(values: number[]): number {
  if (!values.length) return 1;
  return values.reduce((acc, v) => gcdPair(acc, v));
}

/**
 * 将整数权重换算为整数百分比展示，合计严格为 100（最大余数法）。
 */
export function targetRatiosToDisplayPercents(ratios: number[]): number[] {
  if (!ratios.length) return [];
  const total = ratios.reduce((a, b) => a + b, 0);
  if (total <= 0) return ratios.map(() => 0);

  const exact = ratios.map((r) => (r / total) * 100);
  const base = exact.map((x) => Math.floor(x));
  const remainder = 100 - base.reduce((s, x) => s + x, 0);
  const order = exact
    .map((x, i) => ({ i, f: x - Math.floor(x) }))
    .sort((a, b) => b.f - a.f || a.i - b.i);
  const out = [...base];
  for (let k = 0; k < remainder; k++) {
    out[order[k].i] += 1;
  }
  return out;
}

/**
 * 将用户输入的整数百分比（合计应为 100，且每项须 > 0）换算为最小正整数权重，便于写回 `target_ratio`。
 * 若含 0，与 `gcdMany` 组合会产生错误比例（例如 [0,50,50] → [1,1,1]），故显式拒绝。
 */
export function ratiosToTargetRatios(pcts: number[]): number[] {
  if (!pcts.length) return [];
  const cleaned = pcts.map((p) => Math.max(0, Math.round(p)));
  if (cleaned.some((p) => p <= 0)) {
    throw new Error("ratiosToTargetRatios: each percent must be a positive integer");
  }
  const g = gcdMany(cleaned);
  return cleaned.map((p) => Math.max(1, Math.round(p / g)));
}

export type RandomGroupInput = { id: number; target_ratio: number };
export type LocalAssignment = { patientId: number; groupId: number };

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

function calculateGroupCounts(totalPatients: number, groups: RandomGroupInput[]): number[] {
  const totalRatio = groups.reduce((sum, g) => sum + g.target_ratio, 0);
  const exact = groups.map((g) => (totalPatients * g.target_ratio) / totalRatio);
  const counts = exact.map((value) => Math.floor(value));
  const remainder = totalPatients - counts.reduce((sum, count) => sum + count, 0);
  const order = exact
    .map((value, index) => ({ index, fraction: value - Math.floor(value) }))
    .sort((a, b) => b.fraction - a.fraction || a.index - b.index);

  for (let i = 0; i < remainder; i++) {
    counts[order[i].index] += 1;
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
  const counts = calculateGroupCounts(shuffled.length, groups);
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
