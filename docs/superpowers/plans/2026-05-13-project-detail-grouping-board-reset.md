# Project Detail Grouping Board Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the project-patients tab and direct project-patient add path from the project detail page, leaving the project detail page focused on the grouping board only.

**Architecture:** This is a narrow frontend cleanup. `ProjectDetailPage` returns to a single-content layout that renders `ProjectGroupingBoard` directly, while the deleted `ProjectPatientsTab` removes the conflicting direct `POST /studies/project-patients/` path. Tests lock the page against reintroducing project-patient tabs, fixed CRF copy, and stale `grouping_status` frontend typing.

**Tech Stack:** React 18, TypeScript, Ant Design, React Query, React Router, Vitest, Testing Library.

---

## File Structure

- Modify: `frontend/src/app/App.test.tsx`
  - Owns app-level route regression coverage.
  - Replace the old “项目患者 tab T0/T1/T2 links” expectation with a negative test that proves the project detail page has no project-patients tab, no direct add button, and no fixed CRF/visit copy.
- Modify: `frontend/src/pages/projects/ProjectDetailPage.tsx`
  - Owns the project detail page shell.
  - Remove `Tabs`, `Typography`, `ProjectPatientsTab`, `statusLabel`, and the fixed project metadata/CRF paragraphs.
  - Render `ProjectGroupingBoard` directly.
- Delete: `frontend/src/pages/projects/ProjectPatientsTab.tsx`
  - Remove the conflicting direct add-to-project UI and its direct `POST /studies/project-patients/` call.
- Modify: `frontend/src/pages/patients/PatientListPage.tsx`
  - Remove stale `grouping_status` type shape from `ProjectPatientRow`.
- No backend files are expected to change.

## Task 1: Write Project Detail Regression Test

**Files:**
- Modify: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: Replace the project detail tests with the new failing regression coverage**

In `frontend/src/app/App.test.tsx`, replace both existing tests named:

- `renders project grouping board when opening /projects/1`
- `renders T0/T1/T2 visit links on 项目患者 tab`

with this single test:

```tsx
  it("renders project detail as grouping board only", async () => {
    window.history.pushState({}, "", "/projects/1");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getAllByText("研究项目 A").length).toBeGreaterThan(0);
      expect(screen.getByText(/全量患者/)).toBeInTheDocument();
      expect(screen.getAllByText("项目患者甲").length).toBeGreaterThan(0);
      expect(screen.getAllByText("项目患者乙").length).toBeGreaterThan(0);
      expect(screen.getAllByText(/张三/).length).toBeGreaterThan(0);
    });

    expect(screen.queryByRole("tab", { name: "分组看板" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "项目患者" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "添加患者" })).not.toBeInTheDocument();
    expect(screen.queryByText(/CRF 模板版本/)).not.toBeInTheDocument();
    expect(screen.queryByText(/CRF 录入请从/)).not.toBeInTheDocument();
    expect(screen.queryByText(/访视评估/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "患者详情" }).length).toBeGreaterThan(0);
  });
```

- [ ] **Step 2: Run the focused test and verify it fails for the current reason**

Run:

```bash
cd frontend && npm test -- App.test.tsx
```

Expected: FAIL. The failure should show one of these current regressions still present:

- a `分组看板` tab exists,
- a `项目患者` tab exists,
- fixed copy such as `CRF 模板版本` or `访视评估` exists.

- [ ] **Step 3: Commit the failing test**

```bash
git add frontend/src/app/App.test.tsx
git commit -m "test: 覆盖项目详情仅展示分组看板"
```

## Task 2: Restore Project Detail to Direct Grouping Board

**Files:**
- Modify: `frontend/src/pages/projects/ProjectDetailPage.tsx`
- Delete: `frontend/src/pages/projects/ProjectPatientsTab.tsx`
- Test: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: Replace `ProjectDetailPage.tsx` with the simplified page shell**

Replace the whole file `frontend/src/pages/projects/ProjectDetailPage.tsx` with:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Drawer, Space } from "antd";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { ProjectGroupingBoard } from "./ProjectGroupingBoard";
import { ProjectGroupsTab } from "./ProjectGroupsTab";

type StudyProject = {
  id: number;
  name: string;
  description: string;
  crf_template_version: string;
  status: string;
};

export function ProjectDetailPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const [configOpen, setConfigOpen] = useState(false);

  const { data: project, isLoading, isError } = useQuery({
    queryKey: ["study-project", id],
    queryFn: async () => {
      const r = await apiClient.get<StudyProject>(`/studies/projects/${id}/`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  if (!Number.isFinite(id)) {
    return <Alert type="error" message="无效的项目 ID" />;
  }

  if (isError) {
    return <Alert type="error" message="项目不存在或无权限访问" />;
  }

  return (
    <Card
      loading={isLoading}
      title={project ? project.name : "项目详情"}
      extra={
        <Space>
          <Button type="default" onClick={() => setConfigOpen(true)}>
            新增分组 / 元数据
          </Button>
        </Space>
      }
    >
      {project && (
        <>
          <ProjectGroupingBoard projectId={id} />
          <Drawer
            title="分组配置（元数据）"
            width={720}
            open={configOpen}
            onClose={() => setConfigOpen(false)}
            destroyOnClose
          >
            <ProjectGroupsTab projectId={id} />
          </Drawer>
        </>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Delete the conflicting tab component**

Run:

```bash
git rm frontend/src/pages/projects/ProjectPatientsTab.tsx
```

- [ ] **Step 3: Run the focused test and verify it passes**

Run:

```bash
cd frontend && npm test -- App.test.tsx
```

Expected: PASS. The app-level project detail test should now prove the page has no tabs, no direct add button, and no fixed CRF/visit copy.

- [ ] **Step 4: Commit the page reset**

```bash
git add frontend/src/pages/projects/ProjectDetailPage.tsx frontend/src/pages/projects/ProjectPatientsTab.tsx
git commit -m "fix: 项目详情回归单一分组看板"
```

## Task 3: Remove Stale Grouping Status Frontend Type

**Files:**
- Modify: `frontend/src/pages/patients/PatientListPage.tsx`

- [ ] **Step 1: Remove unused project-patient fields from the delete modal query type**

In `frontend/src/pages/patients/PatientListPage.tsx`, replace:

```ts
type ProjectPatientRow = {
  id: number;
  project: number;
  patient_name: string;
  group_name: string | null;
  grouping_status: string;
};
```

with:

```ts
type ProjectPatientRow = {
  project: number;
};
```

- [ ] **Step 2: Run the targeted type-safety scan**

Run:

```bash
rg -n "grouping_status|ProjectPatientsTab|POST /api/studies/project-patients/|项目患者\"|添加患者到项目|CRF 模板版本|访视评估" frontend/src
```

Expected: only allowed result is the existing防回归 test text around `/randomize/` if included by a broader search. For this exact command, expected output should not include:

- `frontend/src/pages/patients/PatientListPage.tsx`
- `frontend/src/pages/projects/ProjectPatientsTab.tsx`
- `frontend/src/pages/projects/ProjectDetailPage.tsx`

- [ ] **Step 3: Run TypeScript build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. Vite may still print the existing chunk-size warning; that warning is not a failure.

- [ ] **Step 4: Commit the stale type cleanup**

```bash
git add frontend/src/pages/patients/PatientListPage.tsx
git commit -m "chore: 清理项目患者状态类型残留"
```

## Task 4: Full Verification and Final Scan

**Files:**
- No implementation files expected.
- Verification covers `frontend/src/app/App.test.tsx`, `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`, and the frontend build.

- [ ] **Step 1: Run project detail and grouping board frontend tests**

Run:

```bash
cd frontend && npm test -- App.test.tsx ProjectGroupingBoard.test.tsx groupingBoardUtils.test.ts
```

Expected: PASS. This confirms app routing, the project detail regression, and existing grouping-board local randomization behavior.

- [ ] **Step 2: Run all frontend tests**

Run:

```bash
cd frontend && npm test
```

Expected: PASS.

- [ ] **Step 3: Run frontend production build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. Existing Vite chunk-size warning is acceptable.

- [ ] **Step 4: Run final semantic residue scan**

Run:

```bash
rg -n "ProjectPatientsTab|POST /api/studies/project-patients/|添加患者到项目|CRF 模板版本|访视评估|grouping_status" frontend/src
```

Expected: no output.

- [ ] **Step 5: Confirm deleted component is not referenced**

Run:

```bash
test ! -e frontend/src/pages/projects/ProjectPatientsTab.tsx && rg -n "ProjectPatientsTab" frontend/src || true
```

Expected: no output.

- [ ] **Step 6: Check git status**

Run:

```bash
git status --short
```

Expected: clean worktree after commits.

## Self-Review

- Spec coverage:
  - Delete “项目患者” Tab: Task 1 and Task 2.
  - Delete direct “添加患者到项目” entry: Task 1 and Task 2.
  - Delete fixed CRF/visit copy: Task 1 and Task 2.
  - Preserve grouping board behavior: Task 2 avoids `ProjectGroupingBoard` changes; Task 4 runs existing grouping-board tests.
  - Clean `grouping_status` type residue: Task 3.
  - No backend changes: File structure and tasks do not modify backend files.
- Placeholder scan: no unresolved placeholders.
- Type consistency:
  - `ProjectPatientRow` in `PatientListPage.tsx` only needs `project`, matching `buildPatientDeleteModalCopy`.
  - `ProjectDetailPage` still uses `StudyProject.name` for the card title and keeps other response fields in the type because the backend still returns them.
