import dayjs from "dayjs";
import { describe, expect, it } from "vitest";

import { antdZhCNLocale } from "./antdLocale";

describe("Ant Design 中文日期本地化", () => {
  it("同时启用 Ant Design 与 Day.js 的简体中文 locale", () => {
    expect(antdZhCNLocale.DatePicker?.lang.locale).toBe("zh_CN");
    expect(antdZhCNLocale.Calendar?.lang.locale).toBe("zh_CN");
    expect(dayjs.locale()).toBe("zh-cn");
  });
});
