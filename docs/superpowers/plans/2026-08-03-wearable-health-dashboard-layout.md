# 穿戴健康面板平铺改版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将患者穿戴健康页改为四项趋势平铺、快捷日期筛选和统一日汇总，并移除设备配置区与通用 Tooltip 字段名。

**Architecture:** 保留现有穿戴后端接口与数据模型；前端用一个共享日期范围驱动三项原始测量查询和一个日汇总查询。`WearableHealthTab` 继续负责设备操作与异步隔离，图表配置函数负责业务 Tooltip 名称，日汇总列改为与指标选择无关的静态列。

**Tech Stack:** React 18、TypeScript、Ant Design 5、TanStack Query v5、Ant Design Charts、Vitest、Testing Library

## Global Constraints

- 只修改前端，不修改穿戴设备模型、同步规则、数据归属或后端接口。
- 默认“近 30 天”，支持“近 7 天”和最长 31 个自然日的自定义范围。
- 心率、血压、血氧固定使用 `bucket=raw`，步数读取日汇总。
- 四项趋势独立展示加载、错误与空态。
- Tooltip 使用“心率”“血氧”“步数”“收缩压”“舒张压”，不得显示通用 `value`。
- 日汇总展示所有指标和步数，不展示同步状态或归属状态。
- 不执行 Git commit，除非用户另行明确授权；下列提交步骤仅记录建议的提交边界。
- 保留当前工作区中与本任务无关的穿戴时间解析改动。

---

### Task 1: 图表 Tooltip 业务名称

**Files:**
- Modify: `frontend/src/pages/wearables/wearableMetricChartConfig.ts`
- Test: `frontend/src/pages/wearables/wearableMetricChartConfig.test.ts`

**Interfaces:**
- Consumes: `buildWearableMetricChartConfig(metricType, data)`、`buildWearableStepsChartConfig(data)`
- Produces: 两个配置函数返回带 `tooltip.items` 的图表配置；数据字段仍为 `value`

- [x] **Step 1: 写 Tooltip 失败测试**

在 `wearableMetricChartConfig.test.ts` 中引入
`buildWearableStepsChartConfig`，并补充断言：

```ts
expect(heartRateConfig.tooltip).toEqual({
  items: [{ field: "value", name: "心率" }],
});
expect(bloodOxygenConfig.tooltip).toEqual({
  items: [{ field: "value", name: "血氧" }],
});

const stepsConfig = buildWearableStepsChartConfig({
  items: [{ record_date: "2026-07-25", steps: 6000 }],
});
expect(stepsConfig.tooltip).toEqual({
  items: [{ field: "value", name: "步数" }],
});
```

血压继续使用 `series` 的“收缩压/舒张压”名称，并增加断言保证这两个名称存在于长格式数据中。

- [x] **Step 2: 运行测试并确认失败**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/wearableMetricChartConfig.test.ts
```

Expected: FAIL，提示 `tooltip` 为 `undefined`。

- [x] **Step 3: 最小实现 Tooltip 配置**

扩展配置类型并在单指标、步数配置中声明业务名称：

```ts
type LineChartConfig = {
  // 现有字段保持不变
  tooltip?: {
    items: Array<{ field: "value"; name: string }>;
  };
};

const metricName =
  metricType === "heart_rate" ? "心率" : "血氧";

return {
  // 现有配置
  tooltip: { items: [{ field: "value", name: metricName }] },
};
```

步数配置使用：

```ts
tooltip: { items: [{ field: "value", name: "步数" }] },
```

- [x] **Step 4: 运行图表配置测试**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/wearableMetricChartConfig.test.ts
```

Expected: PASS。

- [x] **Step 5: 建议提交边界（仅在用户授权后执行）**

```bash
git add frontend/src/pages/wearables/wearableMetricChartConfig.ts \
  frontend/src/pages/wearables/wearableMetricChartConfig.test.ts
git commit -m "fix(wearables): 使用健康指标名称展示图表提示"
```

---

### Task 2: 快捷日期筛选与四项趋势并行查询

**Files:**
- Modify: `frontend/src/pages/wearables/WearableHealthTab.tsx`
- Test: `frontend/src/pages/wearables/WearableHealthTab.test.tsx`

**Interfaces:**
- Consumes: `fetchWearableMeasurementsByIdentity`、`wearableMeasurementQueryKey`、`WearableMetricChart`、`WearableStepsChart`
- Produces:
  - `type DatePreset = "7d" | "30d" | "custom"`
  - `measurementIdentities: Record<"heart_rate" | "blood_pressure" | "blood_oxygen", WearableMeasurementQueryIdentity | null>`
  - 四张独立趋势卡片

- [x] **Step 1: 将现有筛选测试改写为快捷范围和并行查询失败测试**

删除依赖“健康指标”“图表间隔”下拉框的断言，增加：

```ts
expect(screen.getByText("近 7 天")).toBeInTheDocument();
expect(screen.getByText("近 30 天")).toBeInTheDocument();
expect(screen.getByText("自定义")).toBeInTheDocument();
expect(screen.queryByLabelText("健康指标")).not.toBeInTheDocument();
expect(screen.queryByLabelText("图表间隔")).not.toBeInTheDocument();

await waitFor(() => {
  for (const metricType of [
    "heart_rate",
    "blood_pressure",
    "blood_oxygen",
  ]) {
    expect(mockGet).toHaveBeenCalledWith(
      "/wearables/patients/201/measurements/",
      expect.objectContaining({
        params: expect.objectContaining({
          project_patient: 9001,
          metric_type: metricType,
          bucket: "raw",
        }),
        signal: expect.any(AbortSignal),
      }),
    );
  }
});

expect(screen.getByText("心率趋势")).toBeInTheDocument();
expect(screen.getByText("血压趋势")).toBeInTheDocument();
expect(screen.getByText("血氧趋势")).toBeInTheDocument();
expect(screen.getByText("步数趋势")).toBeInTheDocument();
```

增加近 7 天测试，点击后断言三个测量请求与日汇总请求使用上海时区今天及之前 6 天；增加自定义测试，点击“自定义”后才出现 `aria-label="健康日期范围"`。

- [x] **Step 2: 运行页面测试并确认失败**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx
```

Expected: FAIL，因为仍存在指标/分桶下拉框且只请求一个测量指标。

- [x] **Step 3: 实现日期预设状态**

替换 `metricType`、`bucket` 筛选状态：

```ts
type DatePreset = "7d" | "30d" | "custom";

const DATE_PRESET_OPTIONS = [
  { label: "近 7 天", value: "7d" },
  { label: "近 30 天", value: "30d" },
  { label: "自定义", value: "custom" },
] as const;

function presetRange(days: 7 | 30): [Dayjs, Dayjs] {
  const today = shanghaiToday();
  return [today.subtract(days - 1, "day"), today];
}
```

组件默认值：

```ts
const [datePreset, setDatePreset] = useState<DatePreset>("30d");
const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(() =>
  presetRange(30),
);
```

使用 Ant Design `Segmented` 展示快捷项；选择 `7d` 或 `30d` 时立即替换 `dateRange`，选择 `custom` 时保留当前范围并显示 `RangePicker`。自定义禁用日期使用 31 日上限：

```tsx
{datePreset === "custom" ? (
  <DatePicker.RangePicker
    aria-label="健康日期范围"
    value={dateRange}
    disabledDate={(current, info) =>
      isOutsideHealthRange(current, info.from, "heart_rate")
    }
    onChange={(value) => {
      if (value?.[0] && value[1]) {
        setDateRange(
          clampHealthDateRange([value[0], value[1]], "heart_rate"),
        );
      }
    }}
  />
) : null}
```

- [x] **Step 4: 实现三项原始测量并行查询**

定义固定测量指标：

```ts
const MEASUREMENT_METRICS = [
  "heart_rate",
  "blood_pressure",
  "blood_oxygen",
] as const;
```

为每项创建独立 identity，并使用 TanStack Query `useQueries`：

```ts
const measurementIdentities = useMemo(
  () =>
    Object.fromEntries(
      MEASUREMENT_METRICS.map((metricType) => [
        metricType,
        isBound && syncQuery.data?.binding_id && syncQuery.data.device_id
          ? {
              patientId,
              projectPatientId,
              bindingId: syncQuery.data.binding_id,
              deviceId: syncQuery.data.device_id,
              metricType,
              bucket: "raw" as const,
              start: params.start,
              end: params.end,
            }
          : null,
      ]),
    ) as Record<
      (typeof MEASUREMENT_METRICS)[number],
      WearableMeasurementQueryIdentity | null
    >,
  [isBound, params.end, params.start, patientId, projectPatientId, syncQuery.data],
);
```

每项查询必须使用各自 identity 作为 query key，并保持 `fetchWearableMeasurementsByIdentity` 的分页拉齐和 AbortSignal 行为。

- [x] **Step 5: 渲染四张独立趋势卡片**

使用 Ant Design `Row`、`Col`、`Card`：

```tsx
<Row gutter={[16, 16]}>
  {MEASUREMENT_METRICS.map((metricType, index) => (
    <Col xs={24} xl={12} key={metricType}>
      <Card title={`${METRIC_LABELS[metricType]}趋势`}>
        {measurementQueries[index].isLoading ? (
          <LoadingState label={`正在加载${METRIC_LABELS[metricType]}趋势`} />
        ) : measurementQueries[index].isError ? (
          <Alert
            type="error"
            showIcon
            message={errorMessage(
              measurementQueries[index].error,
              `加载${METRIC_LABELS[metricType]}趋势失败`,
            )}
          />
        ) : (
          <WearableMetricChart
            metricType={metricType}
            data={measurementQueries[index].data}
          />
        )}
      </Card>
    </Col>
  ))}
  <Col xs={24} xl={12}>
    <Card title="步数趋势">
      <WearableStepsChart data={dailyQuery.data} />
    </Card>
  </Col>
</Row>
```

单项查询失败只在对应卡片显示 `Alert`，不能替换整个趋势区。

- [x] **Step 6: 运行相关页面测试**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx \
  -t "快捷日期|四项趋势|独立错误"
```

Expected: 日期快捷筛选、并行查询、四卡片及独立错误态测试 PASS。

- [x] **Step 7: 建议提交边界（仅在用户授权后执行）**

```bash
git add frontend/src/pages/wearables/WearableHealthTab.tsx \
  frontend/src/pages/wearables/WearableHealthTab.test.tsx
git commit -m "feat(wearables): 平铺健康趋势并增加快捷日期筛选"
```

---

### Task 3: 移除设备配置并调整设备操作

**Files:**
- Modify: `frontend/src/pages/wearables/WearableHealthTab.tsx`
- Test: `frontend/src/pages/wearables/WearableHealthTab.test.tsx`

**Interfaces:**
- Consumes: Task 2 的 `measurementIdentities` 与 `measurementQueries`
- Produces:
  - `runStatusCheck()`
  - `runMeasure(metricType: MeasurementMetric)`
  - `runSyncAll()`
  - 不再存在设备配置草案或 `runConfigure`

- [x] **Step 1: 写移除配置和操作语义失败测试**

删除四项设备配置 payload、配置失败、配置 capability 和配置草案测试，改为：

```ts
expect(screen.queryByText("设备配置")).not.toBeInTheDocument();
expect(screen.queryByLabelText("心率间隔（分钟）")).not.toBeInTheDocument();
expect(screen.queryByLabelText("血压间隔（分钟）")).not.toBeInTheDocument();
expect(screen.queryByLabelText("血氧间隔（分钟）")).not.toBeInTheDocument();
expect(screen.queryByLabelText("步数开关待下发值")).not.toBeInTheDocument();
```

主动同步测试改为：

```ts
fireEvent.click(screen.getByRole("button", { name: "主动同步" }));
await waitFor(() =>
  expect(mockPost).toHaveBeenCalledWith(
    "/wearables/patients/201/sync/",
    {},
  ),
);
```

主动测量测试分别点击“测量心率”“测量血压”“测量血氧”，断言 payload 对应：

```ts
{ metric_type: "heart_rate" }
{ metric_type: "blood_pressure" }
{ metric_type: "blood_oxygen" }
```

- [x] **Step 2: 运行操作测试并确认失败**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx
```

Expected: FAIL，因为配置区仍存在、同步仍提交当前指标、主动测量仍依赖已删除的指标选择。

- [x] **Step 3: 删除设备配置前端代码**

从 `WearableHealthTab.tsx` 删除：

- `InputNumber` 和配置专用 `Select` 引入。
- `DeviceDraftState`、`DEFAULT_DEVICE_DRAFTS`。
- `deviceDraftState`、`activeDeviceDrafts`、`updateDeviceDrafts`。
- `validInterval`、`runConfigure`。
- “设备配置”标题、说明和四项配置控件。

保留 `syncStatus.capabilities` 中测量 capability 的读取；后端配置字段无需修改。

- [x] **Step 4: 将操作范围从当前指标改为明确目标**

操作请求记录具体测量指标：

```ts
type MeasurementMetric = (typeof MEASUREMENT_METRICS)[number];

type ActionRequest = {
  // 现有设备、绑定和 scope 字段
  metricType: MeasurementMetric | null;
  measurementIdentity: WearableMeasurementQueryIdentity | null;
};
```

三个入口职责固定：

```ts
const runStatusCheck = async () => {
  // POST /wearables/devices/:id/check-status/
};

const runMeasure = async (metricType: MeasurementMetric) => {
  // POST /wearables/patients/:id/measure/
  // body: { metric_type: metricType }
  // 使用 measurementIdentities[metricType] 做基线与轮询
};

const runSyncAll = async () => {
  await apiClient.post(`/wearables/patients/${patientId}/sync/`, {});
  await invalidateHealthQueries();
};
```

顶部只显示“通信测试”“主动同步”；三个测量按钮分别放到对应趋势卡片标题区，文案为“测量心率”“测量血压”“测量血氧”。

- [x] **Step 5: 保留异步隔离与轮询保护**

`actionScopeKey` 必须包含患者、项目患者、绑定、设备和日期范围，不再包含已删除的 `metricType`、`bucket`。`isCurrentRequest` 继续校验：

```ts
return (
  actionRequestRef.current === request.id &&
  currentActionScopeKey.current === request.scopeKey &&
  patientId === request.patientId &&
  projectPatientId === request.projectPatientId &&
  deviceIdRef.current === request.deviceId &&
  bindingIdRef.current === request.bindingId
);
```

主动测量轮询只获取 `request.measurementIdentity`，发现新点后只刷新该测量 query、日汇总与同步摘要。患者换绑、解绑或时间范围变化时，旧操作结果不得覆盖当前页面反馈。

- [x] **Step 6: 运行页面测试**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx
```

Expected: 配置移除、全指标同步、三项主动测量、轮询、换绑和迟到结果隔离测试全部 PASS。

- [x] **Step 7: 建议提交边界（仅在用户授权后执行）**

```bash
git add frontend/src/pages/wearables/WearableHealthTab.tsx \
  frontend/src/pages/wearables/WearableHealthTab.test.tsx
git commit -m "refactor(wearables): 简化健康页设备操作"
```

---

### Task 4: 统一日汇总列

**Files:**
- Modify: `frontend/src/pages/wearables/WearableHealthTab.tsx`
- Test: `frontend/src/pages/wearables/WearableHealthTab.test.tsx`

**Interfaces:**
- Consumes: `WearableDailySummary`
- Produces: `dailyColumns(): TableColumnsType<WearableDailySummary>`，不接受指标参数

- [x] **Step 1: 写统一日汇总失败测试**

日汇总 mock 同时提供四类数据：

```ts
{
  record_date: "2026-07-23",
  heart_rate_avg: 72,
  heart_rate_min: 60,
  heart_rate_max: 88,
  heart_rate_count: 12,
  systolic_avg: 120,
  diastolic_avg: 78,
  blood_pressure_count: 4,
  blood_oxygen_avg: 98,
  blood_oxygen_min: 96,
  blood_oxygen_max: 99,
  blood_oxygen_count: 8,
  steps: 6000,
}
```

断言表头同时存在：

```ts
for (const heading of [
  "日期",
  "心率均值",
  "最低心率",
  "最高心率",
  "心率测量次数",
  "收缩压均值",
  "舒张压均值",
  "血压测量次数",
  "血氧均值",
  "最低血氧",
  "最高血氧",
  "血氧测量次数",
  "步数",
]) {
  expect(screen.getByRole("columnheader", { name: heading }))
    .toBeInTheDocument();
}
expect(screen.queryByRole("columnheader", { name: "同步状态" }))
  .not.toBeInTheDocument();
expect(screen.queryByRole("columnheader", { name: "归属状态" }))
  .not.toBeInTheDocument();
```

- [x] **Step 2: 运行测试并确认失败**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx
```

Expected: FAIL，因为当前列取决于指标并包含状态列。

- [x] **Step 3: 将日汇总列改为静态全集**

替换 `dailyColumns(metricType)`：

```ts
function dailyColumns(): TableColumnsType<WearableDailySummary> {
  return [
    { title: "日期", dataIndex: "record_date", fixed: "left" },
    { title: "心率均值", dataIndex: "heart_rate_avg", render: valueOrDash },
    { title: "最低心率", dataIndex: "heart_rate_min", render: valueOrDash },
    { title: "最高心率", dataIndex: "heart_rate_max", render: valueOrDash },
    { title: "心率测量次数", dataIndex: "heart_rate_count", render: valueOrDash },
    { title: "收缩压均值", dataIndex: "systolic_avg", render: valueOrDash },
    { title: "舒张压均值", dataIndex: "diastolic_avg", render: valueOrDash },
    { title: "血压测量次数", dataIndex: "blood_pressure_count", render: valueOrDash },
    { title: "血氧均值", dataIndex: "blood_oxygen_avg", render: valueOrDash },
    { title: "最低血氧", dataIndex: "blood_oxygen_min", render: valueOrDash },
    { title: "最高血氧", dataIndex: "blood_oxygen_max", render: valueOrDash },
    { title: "血氧测量次数", dataIndex: "blood_oxygen_count", render: valueOrDash },
    { title: "步数", dataIndex: "steps", render: valueOrDash },
  ];
}
```

移除 `SYNC_STATUS_LABEL`、`ATTRIBUTION_STATUS_LABEL` 和 `statusText`；表格调用改为 `columns={dailyColumns()}`，增大横向滚动宽度以容纳全部列。

- [x] **Step 4: 运行页面测试**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx
```

Expected: PASS。

- [x] **Step 5: 建议提交边界（仅在用户授权后执行）**

```bash
git add frontend/src/pages/wearables/WearableHealthTab.tsx \
  frontend/src/pages/wearables/WearableHealthTab.test.tsx
git commit -m "feat(wearables): 统一展示健康日汇总"
```

---

### Task 5: 前端回归与运行态验证

**Files:**
- Verify: `frontend/src/pages/wearables/WearableHealthTab.tsx`
- Verify: `frontend/src/pages/wearables/WearableHealthTab.test.tsx`
- Verify: `frontend/src/pages/wearables/wearableMetricChartConfig.ts`
- Verify: `frontend/src/pages/wearables/wearableMetricChartConfig.test.ts`

**Interfaces:**
- Consumes: Tasks 1–4 的最终实现
- Produces: 可构建、可运行、符合设计稿的穿戴健康页

- [x] **Step 1: 运行穿戴健康专项测试**

Run:

```bash
cd frontend
npx vitest run \
  src/pages/wearables/wearableMetricChartConfig.test.ts \
  src/pages/wearables/WearableHealthTab.test.tsx
```

Expected: 全部 PASS。

- [x] **Step 2: 运行完整前端测试**

Run:

```bash
cd frontend
npm run test
```

Expected: 全部 PASS。

- [x] **Step 3: 运行 lint**

Run:

```bash
cd frontend
npm run lint
```

Expected: 0 errors；若存在基线 warning，记录但不得新增 warning。

- [x] **Step 4: 运行生产构建**

Run:

```bash
cd frontend
npm run build
```

Expected: 构建成功，无 TypeScript 错误。

- [x] **Step 5: 浏览器验收**

在当前本地项目中打开患者“训练与健康 > 穿戴健康”，确认：

1. 没有设备配置区、健康指标下拉框和图表间隔下拉框。
2. 默认选中近 30 天，近 7 天和自定义能刷新全部数据。
3. 四张趋势卡片同时展示，Tooltip 使用业务中文名称。
4. 日汇总有步数列且无同步状态、归属状态列。
5. 通信测试、全指标主动同步和三项主动测量保持可用。

- [x] **Step 6: 建议最终提交（仅在用户授权后执行）**

```bash
git add frontend/src/pages/wearables \
  docs/superpowers/specs/2026-08-03-wearable-health-dashboard-layout-design.md \
  docs/superpowers/plans/2026-08-03-wearable-health-dashboard-layout.md
git commit -m "feat(wearables): 改版穿戴健康数据面板"
```
