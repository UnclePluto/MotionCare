# 穿戴健康交互强化与日汇总分批加载 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 缩小血氧趋势余量、简化趋势卡片、强化训练/健康导航，并让日汇总独立按每批 5 天加载到设备绑定日期。

**Architecture:** 保留现有测量、同步和日汇总资源接口；同步状态补充 `bound_at`，前端将步数趋势查询与日汇总历史查询拆开。日汇总分页窗口和页面合并放入独立纯函数模块，页面通过 TanStack Query v5 `useInfiniteQuery` 按 5 天窗口请求。

**Tech Stack:** Django 5、DRF、pytest-django、React 18、TypeScript、Ant Design 5、TanStack Query v5、Day.js、Vitest、Testing Library

## Global Constraints

- 血氧下界固定使用 `max(0, floor((minimumBloodOxygen - 5) / 5) * 5)`。
- 血氧上界固定为 `100%`，可见刻度必须包含下界和 `100%`。
- 顶部“近 7 天 / 近 30 天 / 自定义”只控制四张趋势图。
- 日汇总从上海时区今天向设备绑定日期倒序加载，每批最多 5 个自然日。
- 日汇总历史请求不提交 `project_patient`，以患者当前有效绑定为时间边界；查询键仍包含 `projectPatientId`，保证页面上下文切换时重置。
- 日汇总继续只显示日期、心率均值、收缩压均值、舒张压均值、血氧均值和步数。
- 移除趋势卡片测量入口，但保留顶部“通信测试”“主动同步”及后端测量接口。
- 不引入新的分页 API 或第三方依赖。
- 当前工作区已有本功能前序未提交改动；执行时必须保留这些改动，不得回退或覆盖。
- 未获得用户对实现提交的明确授权前，不执行任务内 Git commit；若获得授权，仅暂存任务列出的文件，提交信息使用中文。

---

### Task 1: 提供绑定日期并保证日汇总每日唯一

**Files:**
- Modify: `backend/apps/wearables/services/queries.py:169-285`
- Test: `backend/apps/wearables/tests/test_queries_api.py`

**Interfaces:**
- Consumes: `sync_status(*, user, patient_id)`、`daily_summaries(*, user, patient_id, project_patient_id, start, end)`
- Produces: 同步状态字段 `bound_at: string | null`；日汇总 `items` 中每个 `record_date` 恰好一条

- [x] **Step 1: 写同步状态绑定日期失败测试**

在 `backend/apps/wearables/tests/test_queries_api.py` 增加：

```python
@pytest.mark.django_db
def test_sync_status_returns_current_binding_bound_at(
    doctor, project_patient, wearable_device
):
    binding = WearableBinding.objects.create(
        patient=project_patient.patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 24, 10, 30, tzinfo=UTC),
        bound_by=doctor,
    )

    response = _client(doctor).get(
        f"/api/wearables/patients/{project_patient.patient_id}/sync-status/"
    )

    assert response.status_code == 200
    assert response.data["binding_id"] == binding.id
    assert response.data["bound_at"] == "2026-07-24T18:30:00+08:00"
```

在现有未绑定同步状态测试中补充：

```python
assert response.data["bound_at"] is None
```

- [x] **Step 2: 写日汇总日期唯一性失败测试**

在同一测试文件增加：

```python
@pytest.mark.django_db
def test_daily_summaries_return_each_requested_date_once(
    doctor, project_patient, patient
):
    ProjectPatient.objects.filter(pk=project_patient.pk).update(
        enrolled_at=datetime(2026, 7, 1, tzinfo=UTC)
    )

    response = _client(doctor).get(
        f"/api/wearables/patients/{patient.id}/daily-summaries/",
        {"start": "2026-07-28", "end": "2026-08-01"},
    )

    assert response.status_code == 200
    assert [item["record_date"] for item in response.data["items"]] == [
        "2026-07-28",
        "2026-07-29",
        "2026-07-30",
        "2026-07-31",
        "2026-08-01",
    ]
```

- [x] **Step 3: 运行后端聚焦测试并确认失败**

Run:

```bash
cd backend
pytest apps/wearables/tests/test_queries_api.py \
  -k "sync_status_returns_current_binding_bound_at or daily_summaries_return_each_requested_date_once" -q
```

Expected: `bound_at` 缺失，且当前日汇总实现返回重复日期。

- [x] **Step 4: 最小实现响应字段与每日唯一性**

在 `sync_status` 的未绑定返回值加入：

```python
"bound_at": None,
```

在已绑定返回值加入：

```python
"bound_at": _serialize_datetime(binding.bound_at),
```

在 `daily_summaries` 的日期循环内只保留一次：

```python
items.append(item)
```

删除当前紧邻的第二次重复 `items.append(item)`，不改变字段填充和权限逻辑。

- [x] **Step 5: 运行后端穿戴查询测试**

Run:

```bash
cd backend
pytest apps/wearables/tests/test_queries_api.py -q
```

Expected: PASS。

- [x] **Step 6: 记录任务检查点**

Run:

```bash
git diff --check -- \
  backend/apps/wearables/services/queries.py \
  backend/apps/wearables/tests/test_queries_api.py
```

若执行前用户已明确授权提交：

```bash
git add backend/apps/wearables/services/queries.py \
  backend/apps/wearables/tests/test_queries_api.py
git commit -m "fix(wearables): 补充绑定边界并去重日汇总"
```

---

### Task 2: 调整血氧纵轴与刻度

**Files:**
- Modify: `frontend/src/pages/wearables/wearableMetricChartConfig.ts:77-139`
- Test: `frontend/src/pages/wearables/wearableMetricChartConfig.test.ts:208-275`

**Interfaces:**
- Consumes: `buildWearableMetricChartConfig("blood_oxygen", data)`
- Produces: `scale.y = { domainMin, domainMax: 100, nice: false }` 与 `axis.y.tickMethod`

- [x] **Step 1: 将血氧下界测试改为新公式**

在 `wearableMetricChartConfig.test.ts` 用表驱动测试锁定三个正常值：

```ts
it.each([
  { minimum: 99, expectedMin: 90, expectedTicks: [90, 95, 100] },
  { minimum: 96, expectedMin: 90, expectedTicks: [90, 95, 100] },
  { minimum: 92, expectedMin: 85, expectedTicks: [85, 90, 95, 100] },
])(
  "血氧最低值 $minimum 时下界为 $expectedMin",
  ({ minimum, expectedMin, expectedTicks }) => {
    const config = buildWearableMetricChartConfig("blood_oxygen", {
      metric_type: "blood_oxygen",
      bucket: "raw",
      start: "2026-07-28",
      end: "2026-07-28",
      total: 1,
      page: 1,
      page_size: 500,
      next_page: null,
      items: [
        {
          measured_at: "2026-07-27T18:00:00Z",
          blood_oxygen: minimum,
        },
      ],
    });

    expect(config.scale?.y).toEqual({
      domainMin: expectedMin,
      domainMax: 100,
      nice: false,
    });
    expect(config.axis?.y?.tickMethod?.(expectedMin, 100, 5)).toEqual(
      expectedTicks,
    );
  },
);
```

增加下界不得为负数：

```ts
it("血氧接近零时纵轴下界不小于零", () => {
  const config = buildWearableMetricChartConfig("blood_oxygen", {
    metric_type: "blood_oxygen",
    bucket: "raw",
    start: "2026-07-28",
    end: "2026-07-28",
    total: 1,
    page: 1,
    page_size: 500,
    next_page: null,
    items: [
      { measured_at: "2026-07-27T18:00:00Z", blood_oxygen: 3 },
    ],
  });

  expect(config.scale?.y?.domainMin).toBe(0);
  expect(config.axis?.y?.tickMethod?.(0, 100, 5)).toEqual([
    0, 25, 50, 75, 100,
  ]);
});
```

- [x] **Step 2: 运行图表配置测试并确认失败**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/wearableMetricChartConfig.test.ts
```

Expected: FAIL，现有动态跨度余量仍返回旧下界。

- [x] **Step 3: 实现下界公式和 5 倍数刻度**

将 `bloodOxygenScale` 改为：

```ts
function bloodOxygenScale(values: Array<number | null>) {
  const validValues = values.filter(
    (item): item is number =>
      typeof item === "number" && Number.isFinite(item),
  );
  if (validValues.length === 0) return undefined;
  const minimum = Math.min(...validValues);
  return {
    y: {
      domainMin: Math.max(0, Math.floor((minimum - 5) / 5) * 5),
      domainMax: 100,
      nice: false,
    },
  };
}
```

将 `bloodOxygenTicks` 的步长计算替换为：

```ts
const count = Number.isFinite(tickCount)
  ? Math.max(2, Math.floor(tickCount))
  : 5;
const rawStep = (maximum - minimum) / (count - 1);
const step = Math.max(5, Math.ceil(rawStep / 5) * 5);
```

保留当前强制插入 `minimum`、`maximum` 和浮点去重逻辑。

- [x] **Step 4: 运行图表配置测试**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/wearableMetricChartConfig.test.ts
```

Expected: PASS。

- [x] **Step 5: 记录任务检查点**

Run:

```bash
git diff --check -- \
  frontend/src/pages/wearables/wearableMetricChartConfig.ts \
  frontend/src/pages/wearables/wearableMetricChartConfig.test.ts
```

若已授权提交：

```bash
git add frontend/src/pages/wearables/wearableMetricChartConfig.ts \
  frontend/src/pages/wearables/wearableMetricChartConfig.test.ts
git commit -m "fix(wearables): 收紧血氧趋势纵轴余量"
```

---

### Task 3: 移除趋势卡片主动测量入口

**Files:**
- Modify: `frontend/src/pages/wearables/WearableHealthTab.tsx:111-550,660-688`
- Test: `frontend/src/pages/wearables/WearableHealthTab.test.tsx`

**Interfaces:**
- Consumes: 三项 `measurementQueries`，顶部 `runStatusCheck()` 与 `runSyncAll()`
- Produces: 只有标题的四张趋势卡片；顶部设备操作保持不变

- [x] **Step 1: 写卡片操作区移除测试**

在 `WearableHealthTab.test.tsx` 增加：

```ts
it("趋势卡片不展示主动测量与能力提示但保留顶部设备操作", async () => {
  mockGet.mockImplementation((url: string) => {
    if (url.includes("sync-status")) {
      return Promise.resolve({
        data: boundSyncStatus({
          capabilities: {
            ...boundSyncStatus().capabilities,
            measure_heart_rate: true,
            measure_blood_pressure: true,
            measure_blood_oxygen: true,
          },
        }),
      });
    }
    if (url.includes("measurements") || url.includes("daily-summaries")) {
      return Promise.resolve({ data: { items: [] } });
    }
    return Promise.reject(new Error(`unmocked GET ${url}`));
  });

  renderTab();

  expect(await screen.findByText("心率趋势")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "测量心率" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "测量血压" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "测量血氧" })).not.toBeInTheDocument();
  expect(screen.queryByText("该型号能力尚未验证")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /通信测试/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /主动同步/ })).toBeInTheDocument();
});
```

- [x] **Step 2: 运行聚焦测试并确认失败**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx \
  -t "趋势卡片不展示主动测量与能力提示但保留顶部设备操作"
```

Expected: FAIL，当前仍渲染三个测量按钮。

- [x] **Step 3: 删除仅供主动测量使用的代码**

从 `WearableHealthTab.tsx` 删除：

- `WearableCommandResponse` import
- `ActionRequest.metricType`、`ActionRequest.measurementIdentity`
- `MEASUREMENT_POLL_ATTEMPTS`、`MEASUREMENT_POLL_INTERVAL_MS`
- `waitForPollInterval`、`measurementSignature`、`commandFeedback`
- `measurementCapability`、`measurementReady`
- `pollForMeasurement`、`runMeasure`

将请求类型收窄为：

```ts
type ActionRequest = {
  id: number;
  scopeKey: string;
  patientId: number;
  projectPatientId: number;
  deviceId: number;
  bindingId: number;
};
```

将 `startRequest` 改为无参数：

```ts
const startRequest = (): ActionRequest | null => {
  const deviceId = syncQuery.data?.device_id;
  const bindingId = syncQuery.data?.binding_id;
  if (operationBusy || !isBound || deviceId == null || bindingId == null) {
    return null;
  }
  const id = actionRequestRef.current + 1;
  actionRequestRef.current = id;
  return {
    id,
    scopeKey: actionScopeKey,
    patientId,
    projectPatientId,
    deviceId,
    bindingId,
  };
};
```

`runStatusCheck` 和 `runSyncAll` 继续调用 `startRequest()`。

- [x] **Step 4: 移除卡片 `extra`**

三项测量卡统一改为：

```tsx
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
```

- [x] **Step 5: 删除已失效的主动测量测试**

从 `WearableHealthTab.test.tsx` 删除只验证以下行为的测试块：

- 能力开关控制“测量心率 / 血压 / 血氧”
- 主动测量命令状态反馈
- 主动测量 10 秒轮询、60 秒超时与迟到结果隔离
- 主动测量与通信测试互斥

保留并运行通信测试、主动同步、患者切换、换绑隔离及趋势读取测试。

- [x] **Step 6: 运行页面测试**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx
```

Expected: PASS。

- [x] **Step 7: 记录任务检查点**

Run:

```bash
git diff --check -- \
  frontend/src/pages/wearables/WearableHealthTab.tsx \
  frontend/src/pages/wearables/WearableHealthTab.test.tsx
```

若已授权提交：

```bash
git add frontend/src/pages/wearables/WearableHealthTab.tsx \
  frontend/src/pages/wearables/WearableHealthTab.test.tsx
git commit -m "refactor(wearables): 移除趋势卡片主动测量入口"
```

---

### Task 4: 强化训练与健康等宽导航

**Files:**
- Create: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.css`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx:1-20,496-510`
- Test: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx:345-405`

**Interfaces:**
- Consumes: Ant Design `Tabs`
- Produces: `training-health-tabs` 等宽导航样式，保留 `role="tab"` / `role="tabpanel"`

- [x] **Step 1: 写导航结构失败测试**

在 `TrainingTrackingDetailPage.test.tsx` 的页签测试中增加：

```ts
const trainingTab = screen.getByRole("tab", { name: "训练跟踪" });
const wearableTab = screen.getByRole("tab", { name: "穿戴健康" });

expect(trainingTab.closest(".training-health-tabs")).not.toBeNull();
expect(trainingTab.querySelector(".anticon-line-chart")).not.toBeNull();
expect(wearableTab.querySelector(".anticon-heart")).not.toBeNull();
expect(trainingTab).toHaveAttribute("aria-selected", "true");

fireEvent.click(wearableTab);
expect(wearableTab).toHaveAttribute("aria-selected", "true");
expect(trainingTab).toHaveAttribute("aria-selected", "false");
```

- [x] **Step 2: 运行页签测试并确认失败**

Run:

```bash
cd frontend
npx vitest run src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx \
  -t "可在训练跟踪与穿戴健康页签间切换并保留训练功能"
```

Expected: FAIL，缺少图标和 `training-health-tabs` 根样式。

- [x] **Step 3: 增加带图标的标签内容**

在页面导入：

```ts
import { HeartOutlined, LineChartOutlined } from "@ant-design/icons";
import "./TrainingTrackingDetailPage.css";
```

只替换 `items` 中两个 `label` 字段，不改已有 `children`：

```tsx
label: (
  <Space size={8}>
    <LineChartOutlined />
    训练跟踪
  </Space>
),
```

和：

```tsx
label: (
  <Space size={8}>
    <HeartOutlined />
    穿戴健康
  </Space>
),
```

同时给现有 `<Tabs>` 增加 `rootClassName="training-health-tabs"`。

- [x] **Step 4: 增加等宽可点击样式**

创建 `TrainingTrackingDetailPage.css`：

```css
.training-health-tabs > .ant-tabs-nav {
  width: min(100%, 480px);
  margin-bottom: 16px;
}

.training-health-tabs > .ant-tabs-nav::before {
  display: none;
}

.training-health-tabs > .ant-tabs-nav .ant-tabs-nav-wrap {
  border: 1px solid #d6e4ff;
  border-radius: 9px;
  overflow: hidden;
}

.training-health-tabs > .ant-tabs-nav .ant-tabs-nav-list {
  width: 100%;
}

.training-health-tabs > .ant-tabs-nav .ant-tabs-tab {
  width: 50%;
  justify-content: center;
  margin: 0;
  padding: 12px 18px;
  background: #fff;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.training-health-tabs > .ant-tabs-nav .ant-tabs-tab + .ant-tabs-tab {
  border-left: 1px solid #d6e4ff;
}

.training-health-tabs > .ant-tabs-nav .ant-tabs-tab:hover {
  background: #f0f7ff;
}

.training-health-tabs > .ant-tabs-nav .ant-tabs-tab-active {
  background: #e6f4ff;
  font-weight: 700;
}

.training-health-tabs > .ant-tabs-nav .ant-tabs-tab-btn:focus-visible {
  outline: 2px solid #1677ff;
  outline-offset: -2px;
  border-radius: 4px;
}

.training-health-tabs > .ant-tabs-nav .ant-tabs-ink-bar {
  display: none;
}
```

- [x] **Step 5: 运行训练详情测试**

Run:

```bash
cd frontend
npx vitest run src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
```

Expected: PASS。

- [x] **Step 6: 记录任务检查点**

Run:

```bash
git diff --check -- \
  frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx \
  frontend/src/pages/training-tracking/TrainingTrackingDetailPage.css \
  frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
```

若已授权提交：

```bash
git add frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx \
  frontend/src/pages/training-tracking/TrainingTrackingDetailPage.css \
  frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
git commit -m "feat(training): 强化训练与健康切换导航"
```

---

### Task 5: 提取日汇总五天窗口纯函数

**Files:**
- Create: `frontend/src/pages/wearables/wearableDailySummaryPagination.ts`
- Create: `frontend/src/pages/wearables/wearableDailySummaryPagination.test.ts`

**Interfaces:**
- Consumes: `boundAt: string`、`today: Dayjs`、`WearableDailySummaryResponse[]`
- Produces:
  - `DailySummaryWindow`
  - `firstDailySummaryWindow(boundAt, today)`
  - `nextDailySummaryWindow(current, boundAt)`
  - `mergeDailySummaryPages(pages)`

- [x] **Step 1: 写窗口与合并失败测试**

创建 `wearableDailySummaryPagination.test.ts`：

```ts
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

  it("合并分页时按日期去重并倒序", () => {
    const items = mergeDailySummaryPages([
      {
        items: [
          { record_date: "2026-08-03", steps: 3 },
          { record_date: "2026-08-02", steps: 2 },
        ],
      },
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
```

- [x] **Step 2: 运行纯函数测试并确认失败**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/wearableDailySummaryPagination.test.ts
```

Expected: FAIL，模块不存在。

- [x] **Step 3: 实现窗口与合并纯函数**

创建 `wearableDailySummaryPagination.ts`：

```ts
import type { Dayjs } from "dayjs";

import {
  inShanghai,
  shanghaiDateStart,
} from "../../utils/shanghaiTime";
import type {
  WearableDailySummary,
  WearableDailySummaryResponse,
} from "./types";

export type DailySummaryWindow = {
  start: string;
  end: string;
};

function bindingDay(boundAt: string) {
  return inShanghai(boundAt).startOf("day");
}

function windowEndingAt(end: Dayjs, boundAt: string): DailySummaryWindow {
  const bound = bindingDay(boundAt);
  const candidateStart = end.subtract(4, "day");
  const start = candidateStart.isBefore(bound) ? bound : candidateStart;
  return {
    start: start.format("YYYY-MM-DD"),
    end: end.format("YYYY-MM-DD"),
  };
}

export function firstDailySummaryWindow(
  boundAt: string,
  today: Dayjs,
): DailySummaryWindow {
  return windowEndingAt(today.startOf("day"), boundAt);
}

export function nextDailySummaryWindow(
  current: DailySummaryWindow,
  boundAt: string,
): DailySummaryWindow | null {
  const bound = bindingDay(boundAt);
  const currentStart = shanghaiDateStart(current.start);
  if (!currentStart.isAfter(bound)) return null;
  return windowEndingAt(currentStart.subtract(1, "day"), boundAt);
}

export function mergeDailySummaryPages(
  pages: WearableDailySummaryResponse[],
): WearableDailySummary[] {
  const byDate = new Map<string, WearableDailySummary>();
  for (const page of pages) {
    for (const item of page.items) {
      if (!byDate.has(item.record_date)) {
        byDate.set(item.record_date, item);
      }
    }
  }
  return [...byDate.values()].sort((left, right) =>
    right.record_date.localeCompare(left.record_date),
  );
}
```

- [x] **Step 4: 运行纯函数测试**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/wearableDailySummaryPagination.test.ts
```

Expected: PASS。

- [x] **Step 5: 记录任务检查点**

Run:

```bash
git diff --check -- \
  frontend/src/pages/wearables/wearableDailySummaryPagination.ts \
  frontend/src/pages/wearables/wearableDailySummaryPagination.test.ts
```

若已授权提交：

```bash
git add frontend/src/pages/wearables/wearableDailySummaryPagination.ts \
  frontend/src/pages/wearables/wearableDailySummaryPagination.test.ts
git commit -m "feat(wearables): 增加日汇总五天窗口计算"
```

---

### Task 6: 拆分趋势查询并接入日汇总无限加载

**Files:**
- Modify: `frontend/src/pages/wearables/types.ts:46-67`
- Modify: `frontend/src/pages/wearables/WearableHealthTab.tsx:1-730`
- Test: `frontend/src/pages/wearables/WearableHealthTab.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `PatientWearableSyncStatus.bound_at`，Task 5 的窗口和合并函数
- Produces:
  - `stepsTrendQuery`：跟随顶部趋势日期
  - `dailyHistoryQuery`：患者绑定历史的五天无限查询
  - 表格底部 `获取更多 / 正在获取… / 获取更多失败，点击重试 / 没有更多数据了`

- [x] **Step 1: 更新前端同步状态类型**

在 `PatientWearableSyncStatus` 增加：

```ts
bound_at: string | null;
```

同步更新 `boundSyncStatus()` 与 `unboundSyncStatus()` 测试工厂：

```ts
bound_at: "2026-07-24T18:30:00+08:00",
```

和：

```ts
bound_at: null,
```

所有测试内联的已绑定同步状态对象也加入：

```ts
bound_at: "2026-07-24T18:30:00+08:00",
```

- [x] **Step 2: 增加日汇总测试数据帮助函数**

将测试导入改为：

```ts
import {
  shanghaiDateStart,
  shanghaiToday,
} from "../../utils/shanghaiTime";
```

在 `renderTab` 后增加：

```ts
function dailySummaryResponse(start: string, end: string) {
  const items = [];
  for (
    let cursor = shanghaiDateStart(end);
    !cursor.isBefore(shanghaiDateStart(start));
    cursor = cursor.subtract(1, "day")
  ) {
    items.push({
      record_date: cursor.format("YYYY-MM-DD"),
      steps: 0,
    });
  }
  return Promise.resolve({ data: { start, end, items } });
}
```

- [x] **Step 3: 写趋势筛选与表格解耦失败测试**

增加测试：

```ts
it("趋势日期切换不重新查询或重置日汇总历史", async () => {
  renderTab();

  await screen.findByRole("button", { name: "获取更多" });
  const historyCallsBefore = mockGet.mock.calls.filter(
    ([url, config]) =>
      String(url).includes("daily-summaries") &&
      !(config as { params?: Record<string, unknown> }).params?.project_patient,
  ).length;

  fireEvent.click(screen.getByText("近 7 天"));

  await waitFor(() => {
    const trendCalls = mockGet.mock.calls.filter(
      ([url, config]) =>
        String(url).includes("daily-summaries") &&
        (config as { params?: Record<string, unknown> }).params?.project_patient === 9001,
    );
    expect(trendCalls.at(-1)?.[1]).toMatchObject({
      params: {
        project_patient: 9001,
        start: "2026-07-28",
        end: "2026-08-03",
      },
    });
  });

  const historyCallsAfter = mockGet.mock.calls.filter(
    ([url, config]) =>
      String(url).includes("daily-summaries") &&
      !(config as { params?: Record<string, unknown> }).params?.project_patient,
  ).length;
  expect(historyCallsAfter).toBe(historyCallsBefore);
});
```

- [x] **Step 4: 写连续加载与终止状态失败测试**

使用绑定时间 `2026-07-24T18:30:00+08:00`，在测试开头覆盖 mock：

```ts
mockGet.mockImplementation(
  (url: string, config?: { params?: Record<string, unknown> }) => {
    if (url.includes("sync-status")) {
      return Promise.resolve({ data: boundSyncStatus() });
    }
    if (url.includes("measurements")) {
      return Promise.resolve({ data: { items: [] } });
    }
    if (url.includes("daily-summaries")) {
      const start = String(config?.params?.start);
      const end = String(config?.params?.end);
      return dailySummaryResponse(start, end);
    }
    return Promise.reject(new Error(`unmocked GET ${url}`));
  },
);
```

然后增加断言：

```ts
it("日汇总每次追加更早五天并在绑定日期停止", async () => {
  renderTab();

  expect(await screen.findByText("2026-08-03")).toBeInTheDocument();
  expect(screen.getByText("2026-07-30")).toBeInTheDocument();
  expect(screen.queryByText("2026-07-29")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
  expect(await screen.findByText("2026-07-29")).toBeInTheDocument();
  expect(screen.getByText("2026-07-25")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
  expect(await screen.findByText("2026-07-24")).toBeInTheDocument();
  expect(screen.getByText("没有更多数据了")).toBeInTheDocument();

  const dates = screen
    .getAllByRole("row")
    .slice(1)
    .map((row) => row.firstElementChild?.textContent);
  expect(dates).toEqual([
    "2026-08-03",
    "2026-08-02",
    "2026-08-01",
    "2026-07-31",
    "2026-07-30",
    "2026-07-29",
    "2026-07-28",
    "2026-07-27",
    "2026-07-26",
    "2026-07-25",
    "2026-07-24",
  ]);
});
```

- [x] **Step 5: 写错误、重试与主动同步保留分页测试**

初始请求失败测试：

```ts
it("日汇总初始失败时提供重新加载入口", async () => {
  let failed = false;
  mockGet.mockImplementation(
    (url: string, config?: { params?: Record<string, unknown> }) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({ data: boundSyncStatus() });
      }
      if (url.includes("measurements")) {
        return Promise.resolve({ data: { items: [] } });
      }
      if (url.includes("daily-summaries")) {
        if (config?.params?.project_patient) {
          return dailySummaryResponse(
            String(config.params.start),
            String(config.params.end),
          );
        }
        if (!failed) {
          failed = true;
          return Promise.reject(new Error("history unavailable"));
        }
        return dailySummaryResponse(
          String(config?.params?.start),
          String(config?.params?.end),
        );
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    },
  );

  renderTab();

  expect(await screen.findByText("加载日汇总失败")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
  expect(await screen.findByText("2026-08-03")).toBeInTheDocument();
});
```

加载更多失败测试：

```ts
it("加载更多失败时保留首批数据并允许重试", async () => {
  let secondPageAttempts = 0;
  mockGet.mockImplementation(
    (url: string, config?: { params?: Record<string, unknown> }) => {
      if (url.includes("sync-status")) {
        return Promise.resolve({ data: boundSyncStatus() });
      }
      if (url.includes("measurements")) {
        return Promise.resolve({ data: { items: [] } });
      }
      if (url.includes("daily-summaries")) {
        const start = String(config?.params?.start);
        const end = String(config?.params?.end);
        if (!config?.params?.project_patient && start === "2026-07-25") {
          secondPageAttempts += 1;
          if (secondPageAttempts === 1) {
            return Promise.reject(new Error("next page unavailable"));
          }
        }
        return dailySummaryResponse(start, end);
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    },
  );

  renderTab();

  expect(await screen.findByText("2026-08-03")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "获取更多" }));

  const retry = await screen.findByRole("button", {
    name: "获取更多失败，点击重试",
  });
  expect(screen.getByText("2026-08-03")).toBeInTheDocument();

  fireEvent.click(retry);
  expect(await screen.findByText("2026-07-29")).toBeInTheDocument();
});
```

主动同步保留已展开分页测试：

```ts
it("主动同步刷新已加载分页但不收回历史行", async () => {
  renderTab();

  await screen.findByText("2026-08-03");
  fireEvent.click(screen.getByRole("button", { name: "获取更多" }));
  expect(await screen.findByText("2026-07-25")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /主动同步/ }));

  await waitFor(() => {
    expect(mockPost).toHaveBeenCalledWith(
      "/wearables/patients/201/sync/",
      {},
    );
  });
  expect(screen.getByText("2026-07-25")).toBeInTheDocument();
});
```

- [x] **Step 6: 更新患者与换绑隔离测试**

在现有“操作中解绑后重绑”“同患者直接换绑”“绑定代际变化”测试中，把旧的
单次 `wearable-daily-summaries` 断言改为：

```ts
await waitFor(() => {
  const historyCalls = mockGet.mock.calls.filter(
    ([url, config]) =>
      String(url).includes("daily-summaries") &&
      !(config as { params?: Record<string, unknown> }).params?.project_patient,
  );
  expect(historyCalls.at(-1)?.[1]).toMatchObject({
    params: {
      start: "2026-07-30",
      end: "2026-08-03",
    },
  });
});
```

并断言旧设备绑定查询的数据行在新绑定生效后不再显示。

- [x] **Step 7: 运行新页面测试并确认失败**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx \
  -t "趋势日期切换不重新查询或重置日汇总历史|日汇总每次追加更早五天并在绑定日期停止|日汇总初始失败时提供重新加载入口|加载更多失败时保留首批数据并允许重试|主动同步刷新已加载分页但不收回历史行"
```

Expected: FAIL，当前只有一条随趋势日期变化的 `dailyQuery`。

- [x] **Step 8: 建立趋势步数查询**

将当前 `dailyQuery` 改名并收窄为：

```ts
const stepsTrendQuery = useQuery({
  queryKey: [
    "wearable-daily-trend",
    patientId,
    projectPatientId,
    params,
  ],
  enabled: isBound,
  queryFn: async () =>
    (
      await apiClient.get<WearableDailySummaryResponse>(
        `/wearables/patients/${patientId}/daily-summaries/`,
        { params },
      )
    ).data,
});
```

步数卡片全部改用 `stepsTrendQuery`。

- [x] **Step 9: 建立独立日汇总无限查询**

导入：

```ts
import {
  useInfiniteQuery,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  firstDailySummaryWindow,
  mergeDailySummaryPages,
  nextDailySummaryWindow,
  type DailySummaryWindow,
} from "./wearableDailySummaryPagination";
```

在同步状态成功后建立首批参数：

```ts
const historyEnabled =
  isBound &&
  syncQuery.data?.binding_id != null &&
  syncQuery.data.bound_at != null;
const initialHistoryWindow = useMemo<DailySummaryWindow>(
  () =>
    syncQuery.data?.bound_at
      ? firstDailySummaryWindow(syncQuery.data.bound_at, shanghaiToday())
      : {
          start: shanghaiToday().format("YYYY-MM-DD"),
          end: shanghaiToday().format("YYYY-MM-DD"),
        },
  [syncQuery.data?.bound_at],
);
```

增加无限查询；注意历史请求不传 `project_patient`：

```ts
const dailyHistoryQuery = useInfiniteQuery({
  queryKey: [
    "wearable-daily-history",
    patientId,
    projectPatientId,
    syncQuery.data?.binding_id ?? "unbound",
  ],
  enabled: historyEnabled,
  initialPageParam: initialHistoryWindow,
  queryFn: async ({ pageParam }) =>
    (
      await apiClient.get<WearableDailySummaryResponse>(
        `/wearables/patients/${patientId}/daily-summaries/`,
        { params: pageParam },
      )
    ).data,
  getNextPageParam: (_lastPage, _allPages, lastPageParam) => {
    const boundAt = syncQuery.data?.bound_at;
    if (!boundAt) return undefined;
    return nextDailySummaryWindow(lastPageParam, boundAt) ?? undefined;
  },
});

const dailyHistoryItems = useMemo(
  () => mergeDailySummaryPages(dailyHistoryQuery.data?.pages ?? []),
  [dailyHistoryQuery.data?.pages],
);
```

- [x] **Step 10: 渲染独立表格状态和底部操作**

将日汇总区替换为：

```tsx
<Typography.Title level={5} style={{ margin: 0 }}>
  日汇总
</Typography.Title>
{dailyHistoryQuery.isLoading ? (
  <LoadingState label="正在加载日汇总" />
) : dailyHistoryQuery.isError ? (
  <Space direction="vertical">
    <Alert
      type="error"
      showIcon
      message={errorMessage(
        dailyHistoryQuery.error,
        "加载日汇总失败",
      )}
    />
    <Button type="link" onClick={() => void dailyHistoryQuery.refetch()}>
      重新加载
    </Button>
  </Space>
) : dailyHistoryItems.length === 0 ? (
  <Empty description="暂无日汇总数据" />
) : (
  <Table<WearableDailySummary>
    rowKey="record_date"
    dataSource={dailyHistoryItems}
    pagination={false}
    columns={dailyColumns()}
    footer={() => (
      <div style={{ textAlign: "center" }}>
        {dailyHistoryQuery.hasNextPage ? (
          <Button
            type="link"
            loading={dailyHistoryQuery.isFetchingNextPage}
            onClick={() => void dailyHistoryQuery.fetchNextPage()}
          >
            {dailyHistoryQuery.isFetchNextPageError
              ? "获取更多失败，点击重试"
              : dailyHistoryQuery.isFetchingNextPage
                ? "正在获取…"
                : "获取更多"}
          </Button>
        ) : (
          <Typography.Text type="secondary">
            没有更多数据了
          </Typography.Text>
        )}
      </div>
    )}
  />
)}
```

若 Ant Design `Button loading` 隐藏子文本，则改用
`loading={false}`、`disabled={isFetchingNextPage}` 并在子文本显示“正在获取…”；
最终 DOM 必须能读取该文案。

- [x] **Step 11: 更新主动同步失效键**

将 `invalidateHealthQueries` 中的日汇总键替换为：

```ts
queryClient.invalidateQueries({
  queryKey: [
    "wearable-daily-trend",
    patientId,
    projectPatientId,
  ],
}),
queryClient.invalidateQueries({
  queryKey: [
    "wearable-daily-history",
    patientId,
    projectPatientId,
    syncQuery.data?.binding_id ?? "unbound",
  ],
}),
```

保留同步状态和三项测量趋势的失效。TanStack Query 应刷新当前无限查询已有的所有
page，不调用 `removeQueries`，因此已展开行数保持不变。

- [x] **Step 12: 运行页面测试**

Run:

```bash
cd frontend
npx vitest run src/pages/wearables/WearableHealthTab.test.tsx
```

Expected: PASS。

- [x] **Step 13: 记录任务检查点**

Run:

```bash
git diff --check -- \
  frontend/src/pages/wearables/types.ts \
  frontend/src/pages/wearables/WearableHealthTab.tsx \
  frontend/src/pages/wearables/WearableHealthTab.test.tsx
```

若已授权提交：

```bash
git add frontend/src/pages/wearables/types.ts \
  frontend/src/pages/wearables/WearableHealthTab.tsx \
  frontend/src/pages/wearables/WearableHealthTab.test.tsx
git commit -m "feat(wearables): 日汇总按五天独立加载"
```

---

### Task 7: 集成回归与真实页面验收

**Files:**
- Verify: `backend/apps/wearables/services/queries.py`
- Verify: `frontend/src/pages/wearables/wearableMetricChartConfig.ts`
- Verify: `frontend/src/pages/wearables/WearableHealthTab.tsx`
- Verify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`

**Interfaces:**
- Consumes: Tasks 1-6
- Produces: 可交付的训练与穿戴健康页面及完整验证证据

- [x] **Step 1: 运行后端全量测试**

Run:

```bash
cd backend
pytest
```

Expected: 全部通过。

- [x] **Step 2: 运行前端全量测试**

Run:

```bash
cd frontend
npm run test
```

Expected: 全部通过。

- [x] **Step 3: 运行前端静态检查和构建**

Run:

```bash
cd frontend
npm run lint
npm run build
```

Expected: Lint 0 errors；生产构建成功。既有 warning 单独记录，不得表述为本次新增。

- [x] **Step 4: 检查工作区差异**

Run:

```bash
git diff --check
git status --short
```

Expected: 无空白错误；只包含执行前已知改动和本计划文件，不执行范围外清理。

- [x] **Step 5: 真实页面验证**

打开患者“训练与健康”详情页，逐项确认：

1. “训练跟踪 / 穿戴健康”为等宽导航条，选中、悬停、键盘焦点清晰。
2. 三张测量趋势卡没有测量按钮或能力提示。
3. 顶部通信测试和主动同步可用。
4. 血氧最低值约 `96%` 时纵轴下界显示 `90%`，上界 `100%`。
5. 切换近 7 天、近 30 天和自定义只更新趋势，不改变日汇总行。
6. 日汇总首次 5 天，点击后追加更早 5 天，顺序倒序且无重复。
7. 到设备绑定日期后显示“没有更多数据了”。
8. 浏览器控制台没有新增错误。

保存三张截图：

```text
frontend/output/playwright/wearable-health-navigation-and-cards.png
frontend/output/playwright/wearable-health-summary-first-five.png
frontend/output/playwright/wearable-health-summary-loaded-all.png
```

- [x] **Step 6: 最终审查**

对照设计：

```text
docs/superpowers/specs/2026-08-03-wearable-health-interaction-pagination-design.md
```

逐条核对 Tasks 1-7，无 Critical / Important 问题后才可报告完成。
