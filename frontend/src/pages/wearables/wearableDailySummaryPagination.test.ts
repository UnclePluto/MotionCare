import { describe, expect, it } from "vitest";

import { shanghaiDateStart } from "../../utils/shanghaiTime";
import {
  firstDailySummaryWindow,
  mergeDailySummaryPages,
  nextDailySummaryWindow,
} from "./wearableDailySummaryPagination";

describe("wearableDailySummaryPagination", () => {
  it("从今天向绑定日期按最多五天生成窗口", () => {
    const boundAt = "2026-07-24T10:30:00Z";
    const first = firstDailySummaryWindow(
      boundAt,
      shanghaiDateStart("2026-08-03"),
    );
    const second = nextDailySummaryWindow(first, boundAt);
    const third = nextDailySummaryWindow(second!, boundAt);

    expect(first).toEqual({ start: "2026-07-30", end: "2026-08-03" });
    expect(second).toEqual({ start: "2026-07-25", end: "2026-07-29" });
    expect(third).toEqual({ start: "2026-07-24", end: "2026-07-24" });
    expect(nextDailySummaryWindow(third!, boundAt)).toBeNull();
  });

  it("绑定不足五天时首批直接收敛到绑定日期", () => {
    expect(
      firstDailySummaryWindow(
        "2026-08-01T04:00:00Z",
        shanghaiDateStart("2026-08-03"),
      ),
    ).toEqual({ start: "2026-08-01", end: "2026-08-03" });
  });

  it("按上海时区计算 UTC 绑定时间所在日期", () => {
    expect(
      firstDailySummaryWindow(
        "2026-07-24T16:30:00Z",
        shanghaiDateStart("2026-07-29"),
      ),
    ).toEqual({ start: "2026-07-25", end: "2026-07-29" });
  });

  it("绑定日为今天或未来时不会继续加载历史窗口", () => {
    const today = shanghaiDateStart("2026-08-03");
    const todayWindow = firstDailySummaryWindow("2026-08-03T00:00:00Z", today);
    const futureWindow = firstDailySummaryWindow("2026-08-04T00:00:00Z", today);

    expect(todayWindow).toEqual({ start: "2026-08-03", end: "2026-08-03" });
    expect(nextDailySummaryWindow(todayWindow, "2026-08-03T00:00:00Z")).toBeNull();
    expect(futureWindow).toEqual({ start: "2026-08-03", end: "2026-08-03" });
    expect(nextDailySummaryWindow(futureWindow, "2026-08-04T00:00:00Z")).toBeNull();
  });

  it("合并分页时按日期去重并倒序，保留较新页面的数据", () => {
    const items = mergeDailySummaryPages([
      {
        items: [
          { record_date: "2026-08-03", steps: 3 },
          { record_date: "2026-08-02", steps: 2 },
        ],
      },
      { items: [] },
      {
        items: [
          { record_date: "2026-08-02", steps: 20 },
          { record_date: "2026-08-01", steps: 1 },
        ],
      },
    ]);

    expect(items.map((item) => item.record_date)).toEqual([
      "2026-08-03",
      "2026-08-02",
      "2026-08-01",
    ]);
    expect(items[1].steps).toBe(2);
  });
});
