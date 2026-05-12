import { describe, expect, it } from "vitest";
import { maskPhoneForList } from "./phoneMask";

describe("maskPhoneForList", () => {
  it("masks standard 11-digit mainland number", () => {
    expect(maskPhoneForList("13812345678")).toBe("138****5678");
  });

  it("returns em dash for empty", () => {
    expect(maskPhoneForList("")).toBe("—");
    expect(maskPhoneForList("   ")).toBe("—");
  });

  it("strips non-digits then masks short numbers", () => {
    expect(maskPhoneForList("12")).toBe("1*2");
  });
});
