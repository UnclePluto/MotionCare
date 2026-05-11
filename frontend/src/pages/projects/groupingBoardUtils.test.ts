import { describe, expect, it } from "vitest";

import { ratiosToTargetRatios, targetRatiosToDisplayPercents } from "./groupingBoardUtils";

describe("targetRatiosToDisplayPercents", () => {
  it("maps 1:1:1 to integers summing to 100", () => {
    const p = targetRatiosToDisplayPercents([1, 1, 1]);
    expect(p.reduce((a, b) => a + b, 0)).toBe(100);
    expect(p.every((x) => Number.isInteger(x))).toBe(true);
    expect(Math.max(...p) - Math.min(...p)).toBeLessThanOrEqual(1);
  });

  it("maps 1:2:1 to 25, 50, 25", () => {
    expect(targetRatiosToDisplayPercents([1, 2, 1])).toEqual([25, 50, 25]);
  });
});

describe("ratiosToTargetRatios", () => {
  it("reduces 25,50,25 to 1,2,1", () => {
    expect(ratiosToTargetRatios([25, 50, 25])).toEqual([1, 2, 1]);
  });

  it("handles unequal gcd case", () => {
    expect(ratiosToTargetRatios([33, 33, 34])).toEqual([33, 33, 34]);
  });
});
