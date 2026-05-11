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
