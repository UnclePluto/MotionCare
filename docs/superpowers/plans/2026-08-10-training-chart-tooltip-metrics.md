# 训练图表悬浮指标实施计划

执行记录（2026-08-10, Codex）：Task 1 已完成。初始 tooltip、自动化回归与页签尺寸修复落地于 `8374438`，执行记录落地于 `cc4ca43`，真实浏览器验证发现的固定颜色系列名修复落地于 `e86070e`；验证证据见同目录 Task 1 报告。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将训练与健康详情页两个训练图表的悬浮提示改为业务指标名称，并按百分比或次数格式展示数值。

**Architecture:** 保留 Ant Design Charts 的共享 tooltip 和颜色标记，只在各个 `DualAxes` 子序列上配置 `name`、`channel: "y"` 和 `valueFormatter`。页面测试通过捕获实际传给 `DualAxes` 的配置验证名称和格式化函数，不新增组件或数据转换层。

**Tech Stack:** React 18、TypeScript、Ant Design Charts 2.6、Vitest、Testing Library

## Global Constraints

- “处方完成情况”显示“完成率 75%”和“完成次数 12 次”。
- 日趋势显示“完成次数 3 次”和“7 日移动平均 1.4 次”。
- 周趋势显示“完成次数 3 次”和“周汇总 3 次”。
- 保留颜色圆点、共享浮窗、坐标轴、图表颜色、数据范围及页签行为。
- 保留训练页签的 `destroyOnHidden: true` 及其回归测试，避免切换页签后图表宽度缩窄。
- 不新增依赖，不修改后端或接口数据。

---

### Task 1: 配置业务指标 tooltip 并完成前端回归

**Files:**
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx:205-260`
- Test: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx:8-28,395-480`

**Interfaces:**
- Consumes: `DualAxesConfig.children[].tooltip`，支持 `{ channel: "y", name: string, valueFormatter: (value) => string }`。
- Produces: 两张图表四条序列的业务指标名称与格式化结果；不导出新的公共接口。

- [x] **Step 1: 捕获 DualAxes 的真实配置并写失败测试**

在测试文件的 hoisted mock 中增加配置捕获数组，并在每次测试前清空：

```tsx
const { mockGet, mockPost, mockDualAxesProps } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDualAxesProps: [] as Array<Record<string, unknown>>,
}));

vi.mock("@ant-design/charts", () => ({
  DualAxes: (props: Record<string, unknown>) => {
    mockDualAxesProps.push(props);
    return (
      <pre data-testid="dual-axes-chart">
        {JSON.stringify(props, (_key, value) => (typeof value === "function" ? "[function]" : value))}
      </pre>
    );
  },
  Line: (props: Record<string, unknown>) => (
    <pre data-testid="line-chart">
      {JSON.stringify(props, (_key, value) => (typeof value === "function" ? "[function]" : value))}
    </pre>
  ),
}));
```

在既有 `beforeEach` 的 `mockGet.mockReset()` 前插入：

```tsx
mockDualAxesProps.length = 0;
```

新增测试，从最后一次渲染的完成情况和趋势配置中读取子序列 tooltip：

```tsx
it("图表悬浮提示使用业务指标名称和格式化数值", async () => {
  renderAt("/training-tracking/patients/201");
  expect(await screen.findByText("训练患者甲")).toBeInTheDocument();

  const configs = mockDualAxesProps.filter((props) => Array.isArray(props.children));
  const completion = configs.find((props) =>
    Array.isArray(props.data) && (props.data[0] as { action_name?: string } | undefined)?.action_name,
  );
  const trend = configs.find((props) =>
    Array.isArray(props.data) && (props.data[0] as { label?: string } | undefined)?.label,
  );
  const completionChildren = completion?.children as Array<{ tooltip: TooltipConfig }>;
  const trendChildren = trend?.children as Array<{ tooltip: TooltipConfig }>;

  expect(completionChildren[0].tooltip.name).toBe("完成率");
  expect(completionChildren[0].tooltip.valueFormatter(75)).toBe("75%");
  expect(completionChildren[1].tooltip.name).toBe("完成次数");
  expect(completionChildren[1].tooltip.valueFormatter(12)).toBe("12 次");
  expect(trendChildren[0].tooltip.name).toBe("完成次数");
  expect(trendChildren[0].tooltip.valueFormatter(3)).toBe("3 次");
  expect(trendChildren[1].tooltip.name).toBe("7 日移动平均");
  expect(trendChildren[1].tooltip.valueFormatter(1.4)).toBe("1.4 次");
});
```

测试文件内定义：

```ts
type TooltipConfig = {
  channel: string;
  name: string;
  valueFormatter: (value: number) => string;
};
```

- [x] **Step 2: 运行目标测试并确认 RED**

Run:

```bash
cd frontend
npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx -t "图表悬浮提示使用业务指标名称和格式化数值"
```

Expected: FAIL，因为现有四条子序列没有业务 tooltip 配置。

- [x] **Step 3: 为四条序列添加最小 tooltip 配置**

在 `TrainingTrackingDetailPage.tsx` 增加次数格式化函数：

```ts
function formatCount(value: number | null | undefined) {
  const formatted = formatNumber(value);
  return formatted === "—" ? formatted : `${formatted} 次`;
}
```

在趋势图配置中添加：

```ts
tooltip: {
  channel: "y",
  name: "完成次数",
  valueFormatter: formatCount,
},
```

```ts
tooltip: {
  channel: "y",
  name: range === "weekly" ? "周汇总" : "7 日移动平均",
  valueFormatter: formatCount,
},
```

在处方完成情况配置中添加：

```ts
tooltip: {
  channel: "y",
  name: "完成率",
  valueFormatter: formatPercent,
},
```

```ts
tooltip: {
  channel: "y",
  name: "完成次数",
  valueFormatter: formatCount,
},
```

- [x] **Step 4: 补充周趋势名称断言并确认 GREEN**

在同一测试中点击“按周”，读取最新趋势配置并断言：

```tsx
fireEvent.click(screen.getByText("按周"));

await waitFor(() => {
  const latestTrend = [...mockDualAxesProps]
    .reverse()
    .find((props) =>
      Array.isArray(props.data) && (props.data[0] as { label?: string } | undefined)?.label,
    );
  const children = latestTrend?.children as Array<{ tooltip: TooltipConfig }>;
  expect(children[1].tooltip.name).toBe("周汇总");
  expect(children[1].tooltip.valueFormatter(3)).toBe("3 次");
});
```

Run:

```bash
cd frontend
npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
```

Expected: 目标测试文件全部 PASS，包含现有页签切换后卸载并重建两张图表的断言。

- [x] **Step 5: 运行前端全量验证**

Run:

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Expected: 测试 0 失败；ESLint 0 error；TypeScript 与 Vite 生产构建成功。允许保留仓库既有的 Fast Refresh warning 和 Vite 大包提示，但不得新增告警。

- [x] **Step 6: 使用真实浏览器验证悬浮浮窗**

启动本地前端并使用 Playwright 打开训练与健康详情页，依次悬停两个图表的柱状和折线数据点。确认浮窗不再出现 `#1677ff`、`#52c41a` 或 `#fa8c16` 文本，并分别显示：

```text
完成率 75%
完成次数 12 次
完成次数 3 次
7 日移动平均 1.4 次
```

切换为“按周”后确认折线项显示“周汇总 3 次”；再执行“训练跟踪 → 穿戴健康 → 训练跟踪”，确认两张图表仍占满内容区。

可复核浏览器证据：

- [完成情况浮窗](../evidence/2026-08-10-training-chart-tooltip-metrics/completion-tooltip.png)：显示“完成次数 12 次”“完成率 75%”，且无十六进制颜色文本。
- [日趋势浮窗](../evidence/2026-08-10-training-chart-tooltip-metrics/daily-trend-tooltip.png)：显示“7 日移动平均 1.4 次”“完成次数 3 次”，且无十六进制颜色文本。
- [按周趋势浮窗](../evidence/2026-08-10-training-chart-tooltip-metrics/weekly-trend-tooltip.png)：显示“周汇总 3 次”“完成次数 3 次”，且无十六进制颜色文本。
- [页签回切宽度](../evidence/2026-08-10-training-chart-tooltip-metrics/tab-switch-width.png)：Playwright 同步记录切换前后两张 canvas 均为 `962px` 宽；穿戴健康页签期间 canvas 数量为 `0`。

- [x] **Step 7: 提交源代码与测试**

```bash
git add frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx \
  frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx \
  docs/superpowers/plans/2026-08-10-training-chart-tooltip-metrics.md
git commit -m "fix(training): 修复训练图表尺寸和指标提示"
```
