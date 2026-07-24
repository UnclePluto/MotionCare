import { renderToString } from "react-dom/server";
import { expect, it } from "vitest";

import { WearableMetricChart } from "./WearableMetricChart";

it("使用真实图表依赖渲染血压双线配置时不报错", () => {
  expect(() =>
    renderToString(
      <WearableMetricChart
        metricType="blood_pressure"
        data={{
          metric_type: "blood_pressure",
          bucket: "raw",
          start: "2026-07-25",
          end: "2026-07-25",
          total: 1,
          page: 1,
          page_size: 500,
          next_page: null,
          items: [
            {
              measured_at: "2026-07-24T16:30:00Z",
              systolic: 120,
              diastolic: 80,
            },
          ],
        }}
      />,
    ),
  ).not.toThrow();
});
