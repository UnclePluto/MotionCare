import { describe, expect, it } from "vitest";

import { crfNameInitialsFour } from "./nameInitials";

describe("crfNameInitialsFour", () => {
  it("returns XXXX for empty or whitespace", () => {
    expect(crfNameInitialsFour("")).toBe("XXXX");
    expect(crfNameInitialsFour("   ")).toBe("XXXX");
  });

  it("pads to length 4 with X", () => {
    const r = crfNameInitialsFour("张三");
    expect(r).toHaveLength(4);
    expect(r).toMatch(/^[A-Z]+X*$/);
    expect(r.endsWith("XX")).toBe(true);
  });

  it("truncates to 4 letters when longer", () => {
    const r = crfNameInitialsFour("欧阳修文天祥");
    expect(r).toHaveLength(4);
    expect(r).toMatch(/^[A-Z]{4}$/);
  });

  it("trims surrounding spaces before computing", () => {
    const inner = crfNameInitialsFour("李四");
    expect(crfNameInitialsFour(`  李四  `)).toBe(inner);
  });
});
