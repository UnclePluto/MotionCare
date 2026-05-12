import { describe, expect, it } from "vitest";

import {
  assignPatientsToGroups,
  ratiosToTargetRatios,
  targetRatiosToDisplayPercents,
} from "./groupingBoardUtils";

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

  it("rejects zeros (would otherwise gcd to wrong weights)", () => {
    expect(() => ratiosToTargetRatios([0, 50, 50])).toThrow(/positive integer/);
  });
});

describe("assignPatientsToGroups", () => {
  it("assigns selected patients to groups by target ratios", () => {
    const result = assignPatientsToGroups(
      [1, 2, 3, 4],
      [
        { id: 10, target_ratio: 1 },
        { id: 11, target_ratio: 1 },
      ],
      123,
    );

    expect(result).toHaveLength(4);
    expect(result.filter((x) => x.groupId === 10)).toHaveLength(2);
    expect(result.filter((x) => x.groupId === 11)).toHaveLength(2);
    expect(new Set(result.map((x) => x.patientId))).toEqual(new Set([1, 2, 3, 4]));
  });

  it("returns the same assignments for the same seed", () => {
    const groups = [
      { id: 10, target_ratio: 1 },
      { id: 11, target_ratio: 2 },
      { id: 12, target_ratio: 1 },
    ];

    expect(assignPatientsToGroups([1, 2, 3, 4, 5, 6], groups, 456)).toEqual(
      assignPatientsToGroups([1, 2, 3, 4, 5, 6], groups, 456),
    );
  });

  it("allocates tied largest remainders by group order", () => {
    const result = assignPatientsToGroups(
      [1, 2, 3, 4],
      [
        { id: 10, target_ratio: 1 },
        { id: 11, target_ratio: 1 },
        { id: 12, target_ratio: 1 },
      ],
      123,
    );

    expect([10, 11, 12].map((groupId) => result.filter((x) => x.groupId === groupId).length)).toEqual(
      [2, 1, 1],
    );
  });

  it("uses largest remainders instead of giving the final group leftovers", () => {
    const result = assignPatientsToGroups(
      [1, 2, 3],
      [
        { id: 10, target_ratio: 1 },
        { id: 11, target_ratio: 2 },
        { id: 12, target_ratio: 1 },
      ],
      123,
    );

    expect([10, 11, 12].map((groupId) => result.filter((x) => x.groupId === groupId).length)).toEqual(
      [1, 1, 1],
    );
  });

  it("does not mutate patient id order", () => {
    const patientIds = [1, 2, 3, 4];

    assignPatientsToGroups(
      patientIds,
      [
        { id: 10, target_ratio: 1 },
        { id: 11, target_ratio: 1 },
      ],
      123,
    );

    expect(patientIds).toEqual([1, 2, 3, 4]);
  });

  it("rejects randomization when groups are empty or invalid", () => {
    expect(() => assignPatientsToGroups([1], [], 1)).toThrow("没有启用分组");
    expect(() => assignPatientsToGroups([1], [{ id: 10, target_ratio: 0 }], 1)).toThrow(
      "分组比例必须大于 0",
    );
  });
});
