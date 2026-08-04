# 血氧纵轴与日汇总精简 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩大血氧趋势纵轴余量，并将患者穿戴健康页的日汇总精简为 6 列。

**Architecture:** 保留现有后端日汇总响应和数据模型，只修改前端图表配置与表格列定义。血氧纵轴范围由纯函数根据有效值计算；日汇总继续使用同一日期查询，仅减少展示列。

**Tech Stack:** React 18、TypeScript、Ant Design 5、Ant Design Charts、Vitest、Testing Library

执行记录（2026-08-03, codex）：Task 1–3 已落地并通过独立审查与真实页面验收；工作区改动未提交。

## Global Constraints

- 血氧 `95%–99%` 时纵轴必须显示为 `85%–100%`。
- 血氧低于 `85%` 时纵轴必须继续向下扩展，不能裁剪真实值。
- 日汇总只展示日期、心率均值、收缩压均值、舒张压均值、血氧均值和步数。
- 不修改后端响应字段、同步逻辑和数据归属。
- 顶部日期筛选继续同时驱动趋势图和日汇总表。
- 不执行 Git commit，除非用户另行明确授权。

---

### Task 1: 扩大血氧趋势纵轴余量

**Files:**
- Modify: `frontend/src/pages/wearables/wearableMetricChartConfig.ts`
- Test: `frontend/src/pages/wearables/wearableMetricChartConfig.test.ts`

**Interfaces:**
- Consumes: `buildWearableMetricChartConfig(metricType, data)`
- Produces: 血氧配置中的 `scale.y.domainMin` 与 `scale.y.domainMax`

- [x] **Step 1: 写血氧范围失败测试**

在 `wearableMetricChartConfig.test.ts` 增加：

```ts
it("为血氧纵轴保留 85% 到 100% 的正常观察区间", () => {
  const config = buildWearableMetricChartConfig("blood_oxygen", {
    metric_type: "blood_oxygen",
    bucket: "raw",
    start: "2026-07-28",
    end: "2026-07-28",
    total: 2,
    page: 1,
    page_size: 500,
    next_page: null,
    items: [
      { measured_at: "2026-07-27T18:00:00Z", blood_oxygen: 95 },
      { measured_at: "2026-07-27T19:00:00Z", blood_oxygen: 99 },
    ],
  });

  expect(config.scale?.y).toEqual({
    domainMin: 85,
    domainMax: 100,
  });
});

it("血氧低于 85% 时继续向下扩展纵轴", () => {
  const config = buildWearableMetricChartConfig("blood_oxygen", {
    metric_type: "blood_oxygen",
    bucket: "raw",
    start: "2026-07-28",
    end: "2026-07-28",
    total: 2,
    page: 1,
    page_size: 500,
    next_page: null,
    items: [
      { measured_at: "2026-07-27T18:00:00Z", blood_oxygen: 80 },
      { measured_at: "2026-07-27T19:00:00Z", blood_oxygen: 90 },
    ],
  });

  expect(config.scale?.y).toEqual({
    domainMin: 75,
    domainMax: 100,
  });
});
```

- [x] **Step 2: 运行测试并确认失败**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/wearableMetricChartConfig.test.ts
```

Expected: FAIL，血氧配置尚未设置 `scale.y`。

- [x] **Step 3: 实现血氧纵轴纯函数**

在 `wearableMetricChartConfig.ts` 增加：

```ts
function bloodOxygenScale(values: Array<number | null>) {
  const validValues = values.filter(
    (item): item is number => typeof item === "number",
  );
  if (validValues.length === 0) return undefined;
  const minimum = Math.min(...validValues);
  const maximum = Math.max(...validValues);
  const padding = Math.max(2, (maximum - minimum) * 0.5);
  return {
    y: {
      domainMin: Math.max(0, Math.min(85, Math.floor(minimum - padding))),
      domainMax: 100,
    },
  };
}
```

构建心率或血氧配置前先生成 `points`，然后只为
`metricType === "blood_oxygen"` 合并纵轴：

```ts
const xScale = timeRange(data?.start, data?.end);
const yScale =
  metricType === "blood_oxygen"
    ? bloodOxygenScale(points.map((point) => point.value))
    : undefined;
const scale =
  xScale || yScale
    ? { ...xScale, ...yScale }
    : undefined;
```

- [x] **Step 4: 运行图表配置测试**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/wearableMetricChartConfig.test.ts
```

Expected: PASS。

---

### Task 2: 精简日汇总表格列

**Files:**
- Modify: `frontend/src/pages/wearables/WearableHealthTab.tsx`
- Test: `frontend/src/pages/wearables/WearableHealthTab.test.tsx`

**Interfaces:**
- Consumes: `dailyColumns(): TableColumnsType<WearableDailySummary>`
- Produces: 固定 6 列的日汇总表

- [x] **Step 1: 写精简列失败测试**

把现有“日汇总成功”测试的列断言改为：

```ts
const headers = screen
  .getAllByRole("columnheader")
  .map((header) => header.textContent);

expect(headers).toEqual([
  "日期",
  "心率均值",
  "收缩压均值",
  "舒张压均值",
  "血氧均值",
  "步数",
]);
```

- [x] **Step 2: 运行页面测试并确认失败**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx \
  -t "日汇总成功"
```

Expected: FAIL，当前仍包含最低值、最高值和测量次数列。

- [x] **Step 3: 将 `dailyColumns` 精简为 6 列**

在 `WearableHealthTab.tsx` 中返回：

```ts
function dailyColumns(): TableColumnsType<WearableDailySummary> {
  return [
    { title: "日期", dataIndex: "record_date", fixed: "left", width: 120 },
    { title: "心率均值", dataIndex: "heart_rate_avg", render: valueOrDash },
    { title: "收缩压均值", dataIndex: "systolic_avg", render: valueOrDash },
    { title: "舒张压均值", dataIndex: "diastolic_avg", render: valueOrDash },
    { title: "血氧均值", dataIndex: "blood_oxygen_avg", render: valueOrDash },
    { title: "步数", dataIndex: "steps", render: valueOrDash },
  ];
}
```

移除表格的 `scroll={{ x: 1600 }}`；6 列在当前满宽布局中直接自适应，避免精简后
仍出现无意义横向滚动。

- [x] **Step 4: 运行页面测试**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx
```

Expected: PASS。

---

### Task 3: 页面与全量回归验证

**Files:**
- Verify: `frontend/src/pages/wearables/wearableMetricChartConfig.ts`
- Verify: `frontend/src/pages/wearables/WearableHealthTab.tsx`

**Interfaces:**
- Consumes: Tasks 1–2
- Produces: 可交付的穿戴健康页面

- [x] **Step 1: 浏览器验证**

打开患者穿戴健康页并确认：

1. 血氧为 `95%–99%` 时纵轴显示 `85%–100%`。
2. 日汇总只有 6 列。
3. 近 7 天、近 30 天与自定义范围仍会更新表格。
4. 浏览器控制台没有新增错误。

- [x] **Step 2: 运行完整前端验证**

Run:

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Expected: 测试和构建通过，Lint 无错误。

- [x] **Step 3: 检查差异**

Run:

```bash
git diff --check
git status --short
```

Expected: 没有空白错误，只包含当前已知工作区改动；不执行提交。
