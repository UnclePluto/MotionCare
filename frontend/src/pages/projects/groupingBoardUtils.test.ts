import { describe, expect, it } from "vitest";

import {
  assignPatientsToGroups,
  balancePercents,
  getPercentValidationError,
  groupsWithDraftPercents,
} from "./groupingBoardUtils";

describe("balancePercents", () => {
  it("returns an empty map when there are no groups", () => {
    expect(balancePercents([])).toEqual({});
  });

  it("balances two groups to 50/50", () => {
    expect(balancePercents([10, 11])).toEqual({ 10: 50, 11: 50 });
  });

  it("balances three groups to 34/33/33", () => {
    expect(balancePercents([10, 11, 12])).toEqual({ 10: 34, 11: 33, 12: 33 });
  });

  it("balances four groups to 25/25/25/25", () => {
    expect(balancePercents([10, 11, 12, 13])).toEqual({ 10: 25, 11: 25, 12: 25, 13: 25 });
  });

  it("balances five groups to integers summing to 100", () => {
    const result = balancePercents([10, 11, 12, 13, 14]);
    expect(Object.values(result)).toEqual([20, 20, 20, 20, 20]);
    expect(Object.values(result).reduce((sum, value) => sum + value, 0)).toBe(100);
  });
});

describe("getPercentValidationError", () => {
  it("rejects empty active groups", () => {
    expect(getPercentValidationError([])).toBe("没有启用分组，不能确认分组。");
  });

  it("returns null when active group percents sum to 100", () => {
    expect(getPercentValidationError([50, 50])).toBeNull();
  });

  it("rejects non-positive percents", () => {
    expect(getPercentValidationError([100, 0])).toBe("每个启用组占比必须为大于 0 的整数。");
    expect(getPercentValidationError([101, -1])).toBe("每个启用组占比必须为大于 0 的整数。");
  });

  it("rejects decimal and non-finite percents", () => {
    expect(getPercentValidationError([49.5, 50.5])).toBe("每个启用组占比必须为大于 0 的整数。");
    expect(getPercentValidationError([Number.POSITIVE_INFINITY, 50])).toBe(
      "每个启用组占比必须为大于 0 的整数。",
    );
    expect(getPercentValidationError([Number.NaN, 50])).toBe("每个启用组占比必须为大于 0 的整数。");
  });

  it("rejects percents that do not sum to 100", () => {
    expect(getPercentValidationError([40, 40])).toBe("启用组占比合计须为 100%，当前为 80%。");
  });
});

describe("groupsWithDraftPercents", () => {
  it("uses local draft percents as randomization ratios", () => {
    expect(
      groupsWithDraftPercents(
        [
          { id: 10, target_ratio: 1 },
          { id: 11, target_ratio: 1 },
        ],
        { 10: 75, 11: 25 },
      ),
    ).toEqual([
      { id: 10, target_ratio: 75 },
      { id: 11, target_ratio: 25 },
    ]);
  });

  it("keeps original ratios for missing draft percents without mutating input", () => {
    const groups = [
      { id: 10, target_ratio: 60 },
      { id: 11, target_ratio: 40 },
    ];

    const result = groupsWithDraftPercents(groups, { 10: 75 });

    expect(result).toEqual([
      { id: 10, target_ratio: 75 },
      { id: 11, target_ratio: 40 },
    ]);
    expect(groups).toEqual([
      { id: 10, target_ratio: 60 },
      { id: 11, target_ratio: 40 },
    ]);
    expect(result).not.toBe(groups);
    expect(result[0]).not.toBe(groups[0]);
    expect(result[1]).not.toBe(groups[1]);
  });
});

describe("assignPatientsToGroups", () => {
  it("assigns selected patients to groups by target ratios", () => {
    const result = assignPatientsToGroups(
      [1, 2, 3, 4],
      [
        { id: 10, target_ratio: 50 },
        { id: 11, target_ratio: 50 },
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
      { id: 10, target_ratio: 25 },
      { id: 11, target_ratio: 50 },
      { id: 12, target_ratio: 25 },
    ];

    expect(assignPatientsToGroups([1, 2, 3, 4, 5, 6], groups, 456)).toEqual(
      assignPatientsToGroups([1, 2, 3, 4, 5, 6], groups, 456),
    );
  });

  it("allocates tied largest remainders by group order", () => {
    const result = assignPatientsToGroups(
      [1, 2, 3, 4],
      [
        { id: 10, target_ratio: 34 },
        { id: 11, target_ratio: 33 },
        { id: 12, target_ratio: 33 },
      ],
      123,
    );

    expect([10, 11, 12].map((groupId) => result.filter((x) => x.groupId === groupId).length)).toEqual(
      [2, 1, 1],
    );
  });

  it("uses seeded randomness when one remaining patient could belong to either 50% group", () => {
    const groups = [
      { id: 10, target_ratio: 50 },
      { id: 11, target_ratio: 50 },
    ];
    const groupIds = new Set(
      Array.from({ length: 20 }, (_, seed) => assignPatientsToGroups([1], groups, seed)[0].groupId),
    );

    expect(groupIds).toEqual(new Set([10, 11]));
  });

  it("keeps all patients assigned when stochastic rounding is needed", () => {
    const result = assignPatientsToGroups(
      [1, 2, 3],
      [
        { id: 10, target_ratio: 25 },
        { id: 11, target_ratio: 50 },
        { id: 12, target_ratio: 25 },
      ],
      123,
    );

    expect(result).toHaveLength(3);
    expect(new Set(result.map((x) => x.patientId))).toEqual(new Set([1, 2, 3]));
    expect(result.every((x) => [10, 11, 12].includes(x.groupId))).toBe(true);
  });

  it("does not mutate patient id order", () => {
    const patientIds = [1, 2, 3, 4];

    assignPatientsToGroups(
      patientIds,
      [
        { id: 10, target_ratio: 50 },
        { id: 11, target_ratio: 50 },
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
