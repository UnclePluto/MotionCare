import { describe, expect, it } from "vitest";

import type { RegistryField } from "./types";
import { orderBaselineTableEntries } from "./baselineSectionOrder";

describe("orderBaselineTableEntries", () => {
  it("按 order 过滤并排序；跳过 entries 中不存在的 key", () => {
    const empty: RegistryField[] = [];
    const result = orderBaselineTableEntries(
      [
        ["#T10", empty],
        ["#T8", empty],
      ],
      ["#T0", "#T8", "#T10"],
    );
    expect(result).toEqual([
      ["#T8", empty],
      ["#T10", empty],
    ]);
  });
});
