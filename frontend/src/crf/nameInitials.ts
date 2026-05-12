import { pinyin } from "pinyin-pro";

/** CRF 受试者姓名缩写：拼音首字母大写，不足四位右侧补 X，超过四位截断。 */
export function crfNameInitialsFour(fullName: string): string {
  const name = fullName.trim();
  if (!name) return "XXXX";
  const initials = pinyin(name, { pattern: "first", type: "string" }) as string;
  const letters = initials
    .replace(/\s+/g, "")
    .toUpperCase()
    .replace(/[^A-Z]/g, "");
  const core = letters.slice(0, 4);
  if (core.length >= 4) return core.slice(0, 4);
  return core + "X".repeat(4 - core.length);
}
