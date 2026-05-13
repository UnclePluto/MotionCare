# Grouping Board Selection Polish Implementation Plan

> 状态：implemented
> 日期：2026-05-13
> 范围：分组看板患者选择联动与项目详情文案收敛
> 关联：docs/superpowers/specs/2026-05-13-grouping-board-selection-polish-design.md
> 实施基线 commit：5a3f08f

执行记录（2026-05-13, codex）：Task 1-3 已落地于 commits 2ec9bbd、5a3f08f；聚焦测试、全量前端测试、前端构建与残留文案扫描已通过。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复分组看板患者取消勾选后仍保留本次随机结果的问题，并收敛项目详情页相关文案。

**Architecture:** 保持随机分组为纯前端临时状态，继续使用 `poolSelected` 表示当前参与随机的患者集合，使用 `localAssignments` 表示本页面内刚随机出的未确认结果。新增一个选择变更函数统一处理勾选与取消勾选：取消勾选时同步移除该患者的临时随机分配，重新勾选时只回到待随机集合，不恢复旧结果。

**Tech Stack:** React 18, TypeScript, Ant Design 5, TanStack Query v5, Vitest, React Testing Library.

---

## Files

- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`
  - 覆盖取消勾选清理本次随机结果。
  - 覆盖“全量患者”卡片中的冗余说明文案已删除。
- Modify: `frontend/src/app/App.test.tsx`
  - 覆盖项目详情页按钮文案从 `新增分组 / 元数据` 改为 `新增分组`。
  - 覆盖项目详情页不再出现被删除的冗余说明文案。
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
  - 新增 `handlePatientSelectionChange(patientId, checked)`。
  - 取消勾选时从 `poolSelected` 和 `localAssignments` 同步删除患者。
  - 删除“全量患者”卡片内说明段落。
- Modify: `frontend/src/pages/projects/ProjectDetailPage.tsx`
  - 将右上角配置按钮文案改为 `新增分组`。

---

### Task 1: 写失败测试覆盖选择联动与文案

**Files:**
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`
- Modify: `frontend/src/app/App.test.tsx`

- [x] **Step 1: Add ProjectGroupingBoard red tests**

In `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`, add this test after `随机只生成本地临时结果，不调用后端 randomize`:

```tsx
  it("取消勾选会同步移除本次随机患者", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ProjectGroupingBoard projectId={1} />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/未入组甲/)).toBeInTheDocument());
    expect(screen.queryByText(/勾选未确认入组患者后点击/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
    fireEvent.click(screen.getByRole("button", { name: "随机分组" }));
    await waitFor(() => expect(screen.getByText("本次随机")).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));

    await waitFor(() => expect(screen.queryByText("本次随机")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: /确认分组/ })).toBeDisabled();
  });
```

Expected current failure before implementation:

- The deleted paragraph assertion fails because the paragraph still exists.
- After removing the paragraph, the final `本次随机` assertion still fails until checkbox cancel also clears `localAssignments`.

- [x] **Step 2: Add ProjectDetailPage red assertions**

In `frontend/src/app/App.test.tsx`, inside `renders project detail as grouping board only`, add these assertions after the `waitFor` block and before the existing tab assertions:

```tsx
    expect(screen.getByRole("button", { name: "新增分组" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新增分组 / 元数据" })).not.toBeInTheDocument();
    expect(screen.queryByText(/勾选未确认入组患者后点击/)).not.toBeInTheDocument();
```

Expected current failure before implementation:

- `新增分组` button is not found because the page still renders `新增分组 / 元数据`.
- The deleted paragraph still exists on the grouping board.

- [x] **Step 3: Run focused tests and confirm they fail for the expected reasons**

Run:

```bash
cd frontend && npm test -- App.test.tsx ProjectGroupingBoard.test.tsx
```

Expected: FAIL. The failure should mention one or more of:

- `勾选未确认入组患者后点击`
- `新增分组`
- `本次随机`

- [x] **Step 4: Commit the red tests**

Run:

```bash
git add frontend/src/pages/projects/ProjectGroupingBoard.test.tsx frontend/src/app/App.test.tsx
git commit -m "test: 覆盖分组看板选择联动与文案"
```

---

### Task 2: 实现选择联动与文案收敛

**Files:**
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
- Modify: `frontend/src/pages/projects/ProjectDetailPage.tsx`

- [x] **Step 1: Add unified selection handler**

In `frontend/src/pages/projects/ProjectGroupingBoard.tsx`, add this function near the existing `runLocalRandomize` handler and before `return`:

```tsx
  const handlePatientSelectionChange = (patientId: number, checked: boolean) => {
    setPoolSelected((prev) =>
      checked
        ? prev.includes(patientId)
          ? prev
          : [...prev, patientId]
        : prev.filter((id) => id !== patientId),
    );

    if (!checked) {
      setLocalAssignments((prev) => prev.filter((assignment) => assignment.patientId !== patientId));
    }
  };
```

This keeps re-check behavior intentionally simple: re-checking only returns the patient to `poolSelected`; it does not restore an old `localAssignments` item.

- [x] **Step 2: Use the handler from patient checkboxes**

In `frontend/src/pages/projects/ProjectGroupingBoard.tsx`, replace the checkbox `onChange` block:

```tsx
        onChange={(e) =>
          setPoolSelected((prev) =>
            e.target.checked ? [...prev, p.id] : prev.filter((id) => id !== p.id),
          )
        }
```

with:

```tsx
        onChange={(e) => handlePatientSelectionChange(p.id, e.target.checked)}
```

- [x] **Step 3: Remove the redundant patient pool paragraph**

In `frontend/src/pages/projects/ProjectGroupingBoard.tsx`, remove this paragraph from the `全量患者` card:

```tsx
  <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
    勾选未确认入组患者后点击「随机分组」会生成本次页面内临时结果；确认前不会写入后端。
  </Typography.Paragraph>
```

Do not remove the toolbar text:

```text
当前随机结果仅保存在本页面；刷新或切换项目会丢弃，点击「确认分组」后才正式入组。
```

- [x] **Step 4: Rename the project detail config button**

In `frontend/src/pages/projects/ProjectDetailPage.tsx`, replace:

```tsx
新增分组 / 元数据
```

with:

```tsx
新增分组
```

Do not change the Drawer title `分组配置（元数据）`.

- [x] **Step 5: Run focused tests and confirm they pass**

Run:

```bash
cd frontend && npm test -- App.test.tsx ProjectGroupingBoard.test.tsx
```

Expected: PASS.

- [x] **Step 6: Commit implementation**

Run:

```bash
git add frontend/src/pages/projects/ProjectGroupingBoard.tsx frontend/src/pages/projects/ProjectDetailPage.tsx
git commit -m "fix: 联动清理分组看板临时随机结果"
```

---

### Task 3: 验证收口

**Files:**
- No code changes expected.

- [x] **Step 1: Run grouping-focused frontend tests**

Run:

```bash
cd frontend && npm test -- App.test.tsx ProjectGroupingBoard.test.tsx groupingBoardUtils.test.ts
```

Expected: PASS.

- [x] **Step 2: Run full frontend tests**

Run:

```bash
cd frontend && npm test
```

Expected: PASS.

- [x] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. A Vite chunk-size warning is acceptable if the build exits successfully.

- [x] **Step 4: Scan production frontend source for removed wording**

Run:

```bash
rg -n "勾选未确认入组患者后点击|新增分组 / 元数据" frontend/src --glob '!**/*.test.tsx' --glob '!**/*.test.ts'
```

Expected: no output.

- [x] **Step 5: Confirm git status**

Run:

```bash
git status --short
```

Expected: no unstaged implementation changes. The branch may contain the planned commits.
