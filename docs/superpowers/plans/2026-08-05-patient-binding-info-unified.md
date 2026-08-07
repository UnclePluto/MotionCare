# 患者绑定信息统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 执行记录（2026-08-06, Codex）：Task 1–3 已完成实现、完整验证与独立复审；当前按约束保留为未提交工作区改动。

**Goal:** 将小程序患者绑定和穿戴设备绑定合并为同一个“患者绑定信息”区域，通过右上角按钮和弹窗完成设备绑定，并在统一表格中展示设备简码与设备 ID。

**Architecture:** 保留 `ProjectPatientBindingCard` 对小程序绑定状态的所有权，将现有穿戴设备逻辑重构为同文件内可组合的 Provider、操作区、描述项、反馈区和弹窗片段。统一卡片负责排版，穿戴设备模块继续负责查询、绑定、通信测试、响铃、解绑和迟到响应隔离，避免复制领域逻辑。

**Tech Stack:** React 18、TypeScript、Ant Design 5、TanStack Query v5、Vitest、Testing Library

## Global Constraints

- 外层“患者接入”标题保持不变，内层标题固定为“患者绑定信息”。
- 未绑定设备时，“绑定穿戴设备”必须与“生成临时绑定码”位于同一右上角操作区。
- 已绑定设备后隐藏“绑定穿戴设备”，显示通信测试、能力受控响铃和解绑设备。
- 设备简码、设备 ID、设备绑定时间必须进入统一 `Descriptions` 表格。
- 设备绑定只能输入四位数字，并通过 Modal 提交；不能直接替换已绑定设备。
- 小程序绑定码生成、撤销和只显示一次的行为保持不变。
- 不修改后端 API、模型、迁移、穿戴设备库存页或小程序患者端。
- 不升级 React、Ant Design、TanStack Query 或其它依赖。
- 按仓库规则不自动提交 Git，完成后等待用户明确提交指令。

---

### Task 1: 把穿戴设备行为拆成可组合片段

**Files:**
- Modify: `frontend/src/pages/wearables/WearableBindingPanel.tsx`
- Test: `frontend/src/pages/wearables/WearableBindingPanel.test.tsx`

**Interfaces:**
- Produces: `WearableBindingProvider({ projectPatientId, children })`
- Produces: `useWearableBindingView(): WearableBindingView`
- Produces: `WearableBindingActions`
- Produces: `WearableBindingFeedback`
- Produces: `WearableBindingModals`
- Consumes: 现有 `/wearables/project-patients/:id/binding/`、绑定、状态、响铃和解绑接口

- [x] **Step 1: 写组合接口的失败测试**

在 `WearableBindingPanel.test.tsx` 增加测试 Harness，证明同一个 Provider 下的操作和展示共享
同一绑定状态：

```tsx
function renderComposableBinding(projectPatientId = 12) {
  return render(
    <QueryClientProvider client={queryClient}>
      <WearableBindingProvider projectPatientId={projectPatientId}>
        <WearableBindingActions />
        <WearableBindingHarnessDescriptions />
        <WearableBindingFeedback />
        <WearableBindingModals />
      </WearableBindingProvider>
    </QueryClientProvider>,
  );
}
```

断言未绑定时显示“绑定穿戴设备”；点击后出现“绑定穿戴设备”对话框和
`aria-label="设备固定简码"` 输入框；已有绑定时显示设备简码 `0826`、设备 ID `7`，
且不显示绑定按钮。

- [x] **Step 2: 运行测试确认 RED**

Run:

```bash
cd frontend
npm run test -- src/pages/wearables/WearableBindingPanel.test.tsx
```

Expected: FAIL，组合组件尚未导出。

- [x] **Step 3: 定义共享视图接口和 Context**

在 `WearableBindingPanel.tsx` 增加精确接口：

```tsx
type WearableBindingView = {
  binding: WearableBinding | null;
  isLoading: boolean;
  bindOpen: boolean;
  shortCode: string;
  canBind: boolean;
  bindPending: boolean;
  statusPending: boolean;
  canRing: boolean;
  ringPending: boolean;
  unbindOpen: boolean;
  openBind: () => void;
  closeBind: () => void;
  setShortCode: (value: string) => void;
  submitBind: () => void;
  runStatusCheck: () => void;
  requestRing: () => void;
  openUnbind: () => void;
  closeUnbind: () => void;
  confirmUnbind: () => void;
  feedback: {
    bindingSuccess: boolean;
    unbindSuccess: boolean;
    bindError: string | null;
    queryError: string | null;
    statusError: string | null;
    statusResult: WearableStatus | null;
    ringError: string | null;
    unbindError: string | null;
  };
};
```

用 `createContext<WearableBindingView | null>(null)` 提供状态，`useWearableBindingView`
在缺少 Provider 时抛出明确错误。将现有查询、mutation、患者切换清理和迟到响应保护
原样迁入 `WearableBindingProvider`。

- [x] **Step 4: 实现可组合展示片段**

实现以下行为：

```tsx
export function WearableBindingActions() {
  const view = useWearableBindingView();
  if (!view.binding) {
    return <Button onClick={view.openBind}>绑定穿戴设备</Button>;
  }
  return (
    <>
      <Button onClick={view.runStatusCheck}>通信测试</Button>
      {view.canRing ? <Button onClick={view.requestRing}>让设备响铃</Button> : null}
      <Button danger onClick={view.openUnbind}>解绑设备</Button>
    </>
  );
}
```

测试 Harness 通过 `useWearableBindingView` 直接读取 `binding`，输出“设备简码”
“设备 ID”“设备绑定时间”；未绑定或加载中时值均为“—”。生产统一表格在 Task 2
通过同一个 hook 把三项作为 `Descriptions` 的直接项目渲染，不能使用
`defaultProps`、嵌套表格或单个占满行项目伪装三项。`WearableBindingModals` 同时承载
新的绑定 Modal 和现有解绑 Modal。

绑定 Modal 必须：

- 输入时执行 `value.replace(/\D/g, "").slice(0, 4)`。
- `okText="确认绑定"`。
- `okButtonProps.disabled = !canBind`。
- `confirmLoading = bindPending`。
- 绑定失败时在 Modal 内展示 `bindError`，不关闭弹窗。
- 绑定成功时由 Provider 关闭弹窗并触发已有通信测试。

- [x] **Step 5: 运行穿戴设备测试确认 GREEN**

Run:

```bash
cd frontend
npm run test -- src/pages/wearables/WearableBindingPanel.test.tsx
```

Expected: PASS，原通信测试、响铃、解绑、患者切换和迟到响应用例继续通过。

### Task 2: 统一患者绑定信息布局

**Files:**
- Modify: `frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx`
- Modify: `frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx`
- Test: `frontend/src/pages/wearables/WearableBindingPanel.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `WearableBindingProvider`、`useWearableBindingView`、操作/反馈/弹窗片段
- Produces: 统一标题、操作区、表格、反馈和弹窗布局

- [x] **Step 1: 写统一布局失败测试**

在 `ProjectPatientBindingCard.test.tsx` 增加/调整断言：

```tsx
expect(screen.getByText("患者绑定信息")).toBeInTheDocument();
expect(screen.queryByText("小程序临时绑定码")).not.toBeInTheDocument();
expect(screen.queryByText("穿戴设备")).not.toBeInTheDocument();

const actions = screen.getByTestId("patient-binding-actions");
expect(within(actions).getByRole("button", { name: "生成绑定码" })).toBeInTheDocument();
expect(within(actions).getByRole("button", { name: "绑定穿戴设备" })).toBeInTheDocument();
```

模拟绑定接口返回 `{ device_id: 7, short_code: "0826" }`，绑定完成后断言统一表格中出现：

```tsx
expect(screen.getByText("设备简码")).toBeInTheDocument();
expect(screen.getByText("0826")).toBeInTheDocument();
expect(screen.getByText("设备 ID")).toBeInTheDocument();
expect(screen.getByText("7")).toBeInTheDocument();
```

- [x] **Step 2: 运行测试确认 RED**

Run:

```bash
cd frontend
npm run test -- src/pages/research-entry/ProjectPatientBindingCard.test.tsx
```

Expected: FAIL，当前仍显示旧标题、独立穿戴设备区域和行内输入框。

- [x] **Step 3: 重组卡片结构**

将 `MiniappBindingSection` 的内容包裹在 `WearableBindingProvider` 中，形成：

```tsx
<WearableBindingProvider projectPatientId={projectPatientId}>
  <Space direction="vertical" size="middle" style={{ width: "100%" }}>
    <Space style={{ width: "100%", justifyContent: "space-between" }} wrap>
      <Typography.Text strong>患者绑定信息</Typography.Text>
      <Space data-testid="patient-binding-actions" wrap>
        <Button aria-label="生成绑定码">生成临时绑定码</Button>
        <WearableBindingActions />
        <Button aria-label="撤销绑定">撤销绑定</Button>
      </Space>
    </Space>
    <PatientBindingDescriptions
      miniappStatus={status}
      generatedCode={generatedCode}
    />
    {/* 原绑定码成功/错误提示 */}
    <WearableBindingFeedback />
    <WearableBindingModals />
  </Space>
</WearableBindingProvider>
```

删除原 `Divider` 和单独的 `<WearableBindingPanel />`。保留外层“患者接入”标题。
`PatientBindingDescriptions` 是 `ProjectPatientBindingCard.tsx` 内的局部组件，通过
`useWearableBindingView()` 读取 `binding` 和 `isLoading`，并把“设备简码”“设备 ID”
“设备绑定时间”与原小程序字段一起作为同一个 `Descriptions` 的直接 `items` 数据渲染；
没有绑定或正在加载时三个值均为“—”。

- [x] **Step 4: 保持小程序绑定异步隔离**

继续用 `BindingCodeDisplay.projectPatientId` 判断临时绑定码是否属于当前患者；切换
`projectPatientId` 时重置生成结果。设备 Provider 使用同一个
`projectPatientId`，切换时关闭设备绑定/解绑 Modal 并清理简码。

- [x] **Step 5: 运行两个组件测试确认 GREEN**

Run:

```bash
cd frontend
npm run test -- \
  src/pages/research-entry/ProjectPatientBindingCard.test.tsx \
  src/pages/wearables/WearableBindingPanel.test.tsx
```

Expected: PASS。

### Task 3: 回归验证与收口

**Files:**
- Modify only if verification exposes an in-scope regression.
- Modify: `specs/patient-rehab-system/changelog.md`

**Interfaces:**
- Consumes: Tasks 1–2 的最终实现
- Produces: 可发布的医生端患者绑定信息界面

- [x] **Step 1: 更新变更日志**

在 `specs/patient-rehab-system/changelog.md` 顶部追加一条，记录统一标题、顶部操作区、
设备绑定 Modal 和设备简码/ID 表格展示；不得修改历史条目。

- [x] **Step 2: 扫描旧布局残留**

Run:

```bash
rg -n "小程序临时绑定码|Space\\.Compact|placeholder=\"设备固定简码\"" \
  frontend/src/pages/research-entry frontend/src/pages/wearables
```

Expected: 生产组件不再包含旧标题或行内绑定输入；测试文件可保留否定断言。

- [x] **Step 3: 运行前端完整测试**

Run:

```bash
cd frontend
npm run test
```

Expected: 全部测试通过。

- [x] **Step 4: 运行 Lint 和生产构建**

Run:

```bash
cd frontend
npm run lint
npm run build
```

Expected: Lint 无错误，生产构建成功；现有 Fast Refresh 和大包警告允许保留。

- [x] **Step 5: 检查差异和工作区**

Run:

```bash
git diff --check
git status --short
```

Expected: 只包含本计划涉及的前端代码、测试、规格、计划和追加式变更日志；不提交或
推送，等待用户明确指令。
