/** 列表展示用：不改变存储值。11 位：前三 + **** + 后四；否则首尾各 1 位中间 *；空为 — */
export function maskPhoneForList(raw: string): string {
  const s = raw.trim();
  if (!s) return "—";
  const d = s.replace(/\D/g, "");
  if (d.length >= 11) {
    return `${d.slice(0, 3)}****${d.slice(-4)}`;
  }
  if (d.length <= 1) return "—";
  return `${d[0]}${"*".repeat(Math.max(1, d.length - 2))}${d[d.length - 1]}`;
}
