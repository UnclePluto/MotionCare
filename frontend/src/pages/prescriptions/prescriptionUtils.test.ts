import { describe, expect, it } from "vitest";

import { getActionParameterMode } from "./prescriptionUtils";

describe("getActionParameterMode", () => {
  it("uses duration mode for aerobic actions", () => {
    expect(getActionParameterMode("有氧训练")).toBe("duration");
  });

  it("uses count mode for balance and resistance actions", () => {
    expect(getActionParameterMode("平衡训练")).toBe("count");
    expect(getActionParameterMode("抗阻训练")).toBe("count");
  });
});
