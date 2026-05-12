# Frontend Fullscreen + Create Actions Implementation Plan

> **状态：approved → implementing**（计划已批准，部分任务正在落地中）
> **日期：** 2026-05-08
> **关联 spec：** `docs/superpowers/specs/2026-05-08-frontend-fullscreen-and-create-actions-design.md`
> **跨工具协作：** 修改本文件前请阅读仓库根 `AGENTS.md` §2。勾选 `- [x]` 时同时在文件顶部"执行记录"区注明 commit short-sha 和工具名（cursor / codex）。
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复页面默认留白（满屏），并补齐“患者档案/研究项目”的关键新增动作闭环：患者详情可访问、项目患者可添加。

**Architecture:** 通过引入一份最小的全局 CSS 清除 `body` 默认 margin 并保证根高度；在路由层补齐患者详情路由；在页面层用 React Query + AntD Modal/Select 打通“详情/添加患者”交互，并用 Vitest + Testing Library 覆盖关键路径。

**Tech Stack:** React 18 + TypeScript、React Router、@tanstack/react-query、Ant Design、Axios、Vitest、@testing-library/react。

---

## Scope / 注意事项

- 本计划只实现 spec 的“最小闭环”，不扩展到患者编辑/删除、项目患者移除、批量加入等。
- 当前工作区存在未提交的无关改动（例如 `frontend/src/auth/RequireAuth.tsx`、`specs/patient-rehab-system/*` 删除）。执行每个 task 提交时，只 stage 本 task 涉及文件，避免混入。

## File Structure（将新增/修改的文件）

**Create**
- `frontend/src/styles/global.css`：全局样式（清 margin、根高度）

**Modify**
- `frontend/src/main.tsx`：引入全局样式
- `frontend/src/app/App.tsx`：增加患者详情路由
- `frontend/src/pages/patients/PatientListPage.tsx`：详情按钮跳转
- `frontend/src/pages/patients/PatientDetailPage.tsx`：接入 API + loading/error + 展示
- `frontend/src/pages/projects/ProjectPatientsTab.tsx`：添加患者弹窗 + POST + 刷新
- `frontend/src/app/App.test.tsx`：补测试（路由/详情页/添加患者）

---

### Task 1: 全局满屏样式（清除默认留白）

**Files:**
- Create: `frontend/src/styles/global.css`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: 写一个失败的测试（确保 body 默认 margin 被清除）**

在 `frontend/src/app/App.test.tsx` 增加一个用例：渲染后断言 `document.body.style.margin === "0px"` 不成立（在实现前预计为空或不是 0）。

```ts
it("applies global fullscreen styles (body margin = 0)", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );

  // JSDOM 不一定能读到 computed style，但可以读到 inline style。
  // 我们在 global.css 引入后，会通过 style 注入让 body margin 变为 0。
  expect(document.body.style.margin).toBe("0px");
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:
- `cd frontend && npm test`

Expected:
- FAIL（`document.body.style.margin` 不是 `0px`）

- [ ] **Step 3: 写最小实现**

创建 `frontend/src/styles/global.css`：

```css
html,
body,
#root {
  height: 100%;
}

body {
  margin: 0;
}
```

并在 `frontend/src/main.tsx` 顶部引入：

```ts
import "./styles/global.css";
```

- [ ] **Step 4: 运行测试确认通过**

Run:
- `cd frontend && npm test`

Expected:
- PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add frontend/src/main.tsx frontend/src/styles/global.css frontend/src/app/App.test.tsx
git commit -m "功能：前端全局满屏样式"
```

---

### Task 2: 患者详情路由 + 列表“详情”跳转

**Files:**
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/pages/patients/PatientListPage.tsx`
- Test: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: 写失败测试（点击“详情”会进入患者详情路由）**

在 `frontend/src/app/App.test.tsx` 中：
- mock `/me/` 返回已登录
- mock `/patients/` 返回至少 1 个患者
- 使用 Memory Router 初始到 `/patients`
- 点击“详情”，断言页面出现“患者详情”

建议新增一个单独测试文件也可以（如 `frontend/src/pages/patients/PatientDetailPage.test.tsx`），但为减少改动先放在 `App.test.tsx`。

示例测试代码（以 `App` 级测试为准，保留现有 mock 风格）：

```ts
it("navigates to patient detail page from list", async () => {
  mockGet.mockImplementation((url: string) => {
    if (url === "/me/") return Promise.resolve({ data: { id: 1, phone: "13800000000", name: "测试医生" } });
    if (url === "/patients/") {
      return Promise.resolve({ data: [{ id: 101, name: "张三", gender: "male", age: 30, phone: "13900000000", primary_doctor: 1 }] });
    }
    // 详情页在 Task 3 接入，此处先不 mock
    return Promise.reject(new Error(`unmocked GET ${url}`));
  });

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );

  // 等待列表渲染
  await screen.findByText("张三");

  // 点击“详情”
  screen.getByText("详情").click();

  // PatientDetailPage 当前会显示标题“患者详情”（先用标题做断言）
  await screen.findByText("患者详情");
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:
- `cd frontend && npm test`

Expected:
- FAIL（当前“详情”按钮无跳转，且 App 未注册患者详情路由）

- [ ] **Step 3: 最小实现（路由 + 跳转）**

在 `frontend/src/app/App.tsx`：
- 引入 `PatientDetailPage`
- 增加路由：`/patients/:patientId`

在 `frontend/src/pages/patients/PatientListPage.tsx`：
- 把 “详情” 按钮改为 `Link` 或 `useNavigate()` 跳转
- 推荐使用 `Link`，避免在 Table render 里创建函数造成无谓 re-render

示例（Link 方式）：

```tsx
import { Link } from "react-router-dom";

// ...
render: (_: unknown, row) => (
  <Space>
    <Link to={`/patients/${row.id}`}>详情</Link>
  </Space>
),
```

- [ ] **Step 4: 运行测试确认通过**

Run:
- `cd frontend && npm test`

Expected:
- PASS（至少能导航到详情页并看到“患者详情”标题）

- [ ] **Step 5: 提交**

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add frontend/src/app/App.tsx frontend/src/pages/patients/PatientListPage.tsx frontend/src/app/App.test.tsx
git commit -m "功能：患者详情路由与列表跳转"
```

---

### Task 3: 患者详情页接入 API（含 loading/error）

**Files:**
- Modify: `frontend/src/pages/patients/PatientDetailPage.tsx`
- Test: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: 写失败测试（详情页能展示患者姓名/手机号）**

在测试中补充 mock：
- `GET /patients/101/` 返回患者详情

并断言进入 `/patients/101` 后，页面出现姓名与手机号。

```ts
it("renders patient detail data from API", async () => {
  mockGet.mockImplementation((url: string) => {
    if (url === "/me/") return Promise.resolve({ data: { id: 1, phone: "13800000000", name: "测试医生" } });
    if (url === "/patients/101/") return Promise.resolve({ data: { id: 101, name: "张三", phone: "13900000000" } });
    return Promise.reject(new Error(`unmocked GET ${url}`));
  });

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  window.history.pushState({}, "", "/patients/101");

  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );

  await screen.findByText("张三");
  await screen.findByText("13900000000");
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:
- `cd frontend && npm test`

Expected:
- FAIL（当前详情页未请求/未展示字段）

- [ ] **Step 3: 最小实现（useParams + useQuery + 展示）**

在 `PatientDetailPage.tsx`：
- 解析 `patientId` 为 number；非法时显示 `Alert` 或 `Card` 文案
- `useQuery` 请求 `GET /patients/${id}/`
- loading/error/成功态分别展示
- 成功态至少展示 `name` 与 `phone`（其余字段有则展示，无则 `—`）

- [ ] **Step 4: 运行测试确认通过**

Run:
- `cd frontend && npm test`

Expected:
- PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add frontend/src/pages/patients/PatientDetailPage.tsx frontend/src/app/App.test.tsx
git commit -m "功能：患者详情页接入 API"
```

---

### Task 4: 研究项目 - 项目患者 Tab 增加“添加患者到项目”

**Files:**
- Modify: `frontend/src/pages/projects/ProjectPatientsTab.tsx`
- Test: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: 写失败测试（添加患者后刷新表格）**

测试思路：
- mock `/me/`
- mock 初始 `GET /studies/project-patients/?project=1` 返回空
- mock `GET /patients/` 返回候选患者
- mock `POST /studies/project-patients/` 成功
- mock 二次 `GET /studies/project-patients/?project=1` 返回新增行

断言：
- 打开项目详情 `/projects/1` → “项目患者”Tab
- 点击“添加患者”打开 Modal
- 选择“张三（13900000000）”
- 点击“添加/确定”（按实现按钮文案）
- 表格出现“张三”

（测试中如果 Tabs 切换复杂，可直接渲染 `ProjectPatientsTab` 组件并包 Router/QueryClient；但优先保持 `App` 级路径覆盖。）

- [ ] **Step 2: 运行测试确认失败**

Run:
- `cd frontend && npm test`

Expected:
- FAIL（目前无入口/无 POST）

- [ ] **Step 3: 最小实现（UI + API + 刷新）**

在 `ProjectPatientsTab.tsx`：
- `Card` 增加 `extra` 按钮“添加患者”
- 新增 `Modal`：
  - `Select` 候选来自 `GET /patients/`
  - 单选：保存 `selectedPatientId`
  - 点击提交：
    - `POST /studies/project-patients/` body `{ project: projectId, patient: selectedPatientId }`
    - 成功：关闭 modal、清空选择、`invalidateQueries(["project-patients", projectId])`
    - 失败：message.error（优先 detail）

- [ ] **Step 4: 运行测试确认通过**

Run:
- `cd frontend && npm test`

Expected:
- PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add frontend/src/pages/projects/ProjectPatientsTab.tsx frontend/src/app/App.test.tsx
git commit -m "功能：项目患者支持添加患者"
```

---

### Task 5: 回归验证与基础质量门禁

**Files:**
- Modify: （仅当 lint/test 发现问题时）

- [ ] **Step 1: 运行前端测试**

Run:
- `cd frontend && npm test`

Expected:
- PASS

- [ ] **Step 2: 运行前端 lint**

Run:
- `cd frontend && npm run lint`

Expected:
- PASS（或仅出现与本次无关的既有告警；若阻断需修）

- [ ] **Step 3: 本地手测（可选但推荐）**

Run:
- `cd frontend && npm run dev`
- 打开 `http://localhost:5173`

Check:
- 页面四周无留白
- 患者列表 → 点击详情可进入并看到姓名/手机号
- 项目详情 → 项目患者 → 添加患者后表格刷新

- [ ] **Step 4: 提交（如有修复）**

仅在 Task 5 中出现代码修复时提交。

---

## Self-Review（计划自检）

- 覆盖性：满屏、患者详情路由+API、项目患者添加入口+POST+刷新均有对应 Task。
- 无占位：计划中不含 TBD/TODO；每个测试与命令均给出可直接执行的形式。
- 命名一致：React Query 的 queryKey 与现有代码保持一致（`["project-patients", projectId]`、`["patients"]`）。

