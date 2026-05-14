# Project Patient Research Entry Tabs Implementation Plan

执行记录（2026-05-14, codex）：Task 1-7 已落地于 commit 6286b83

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build project-patient-level research entry: list one row per `ProjectPatient`, open a T0/T1/T2 tabbed entry page, rename patient baseline UI to “基线资料”, and make completed visits read-only.

**Architecture:** Keep existing Django models. Extend `ProjectPatientSerializer` with project and visit summaries, harden `VisitRecordViewSet` so completed visits are immutable, and reuse the existing visit form by extracting it into a `VisitFormContent` component. Frontend routes add `/research-entry/project-patients/:projectPatientId`, while old `/visits/:visitId` and `/patients/:id/crf-baseline` routes remain compatible.

**Tech Stack:** Django 5 + DRF + pytest; React 18 + TypeScript + Vite + Ant Design 5 + TanStack Query v5 + Vitest.

---

## Scope Check

The approved spec covers one workflow with related slices: backend summaries, visit immutability, frontend research entry, baseline naming, and entry links. These slices should ship together because the new research-entry page depends on the new backend response and the completed-readonly rule.

## File Structure

### Backend

- Modify `backend/apps/studies/serializers.py`
  - Add `project_name`, `project_status`, `visit_summaries` to `ProjectPatientSerializer`.
- Modify `backend/apps/studies/views.py`
  - Add `patient_name` and `patient_phone` query filters to `ProjectPatientViewSet.get_queryset()`.
  - Keep array response shape for `/api/studies/project-patients/`.
- Modify `backend/apps/studies/tests/test_project_patient_visit_ids.py`
  - Extend serializer/API contract tests for visit summaries and patient filters.
- Modify `backend/apps/visits/views.py`
  - Reject `PATCH` / `PUT` updates when the current visit is already `completed`.
- Modify `backend/apps/visits/tests/test_status_transition.py`
  - Replace the old “completed visit still editable” test with completed-readonly tests.
- Leave `backend/apps/crf/services/aggregate.py` unchanged.
  - Existing tests already prove CRF reads `PatientBaseline`; final verification reruns those tests.

### Frontend

- Create `frontend/src/pages/visits/VisitFormContent.tsx`
  - Move the reusable visit form implementation out of `VisitFormPage`.
  - Accept `visitId` prop and optional `timeDescription`.
  - Make readonly true when `visit.status === "completed"` or project status is `archived`.
- Modify `frontend/src/pages/visits/VisitFormPage.tsx`
  - Route wrapper only: parse `visitId` and render `VisitFormContent`.
- Modify `frontend/src/pages/visits/VisitFormPage.test.tsx`
  - Update completed-visit expectation to readonly.
- Create `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx`
  - Load one `ProjectPatient`, render summary, T0/T1/T2 tabs, time descriptions, `基线资料`, and `打开 CRF`.
- Create `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.test.tsx`
  - Cover default tab, query-selected tab, completed-readonly state, and missing visit record message.
- Modify `frontend/src/pages/research-entry/ResearchEntryPage.tsx`
  - Switch data source from `/visits/` to `/studies/project-patients/`.
  - Render T0/T1/T2 status links and project-patient actions.
- Create `frontend/src/pages/research-entry/ResearchEntryPage.test.tsx`
  - Cover project-patient rows, same patient in two projects, status links, and removed visit-type filter.
- Modify `frontend/src/pages/patients/PatientCrfBaselinePage.tsx`
  - Change title to `患者基础基线资料`.
- Modify `frontend/src/pages/patients/PatientDetailPage.tsx`
  - Rename top button to `基线资料`.
  - Replace project row `打开 CRF` with `研究录入`.
  - Remove stale alert that says visit/CRF linkage is future work.
- Modify `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
  - Add project-context links on confirmed patient cards: `研究录入` and `打开 CRF`.
- Modify `frontend/src/app/App.tsx`
  - Register `/research-entry/project-patients/:projectPatientId`.
- Modify `frontend/src/app/App.test.tsx`
  - Update route smoke mocks and expectations.

---

### Task 1: Backend ProjectPatient Visit Summaries And Filters

**Files:**
- Modify: `backend/apps/studies/serializers.py`
- Modify: `backend/apps/studies/views.py`
- Test: `backend/apps/studies/tests/test_project_patient_visit_ids.py`

- [x] **Step 1: Extend the failing serializer/API tests**

Append these tests to `backend/apps/studies/tests/test_project_patient_visit_ids.py`:

```python
@pytest.mark.django_db
def test_project_patient_serializer_exposes_visit_summaries(auth_client, project_patient):
    t0 = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    t0.status = VisitRecord.Status.COMPLETED
    t0.visit_date = "2026-05-14"
    t0.save(update_fields=["status", "visit_date"])

    r = auth_client.get(f"/api/studies/project-patients/?project={project_patient.project_id}")

    assert r.status_code == 200, r.content
    rows = r.data if isinstance(r.data, list) else r.data["results"]
    row = rows[0]
    assert row["project_name"] == project_patient.project.name
    assert row["project_status"] == project_patient.project.status
    assert row["visit_summaries"]["T0"] == {
        "id": t0.id,
        "status": VisitRecord.Status.COMPLETED,
        "visit_date": "2026-05-14",
    }
    assert row["visit_summaries"]["T1"]["status"] == VisitRecord.Status.DRAFT
    assert row["visit_summaries"]["T2"]["status"] == VisitRecord.Status.DRAFT


@pytest.mark.django_db
def test_project_patient_list_filters_patient_name_and_phone(auth_client, project_patient):
    by_name = auth_client.get("/api/studies/project-patients/", {"patient_name": "患者甲"})
    by_phone = auth_client.get("/api/studies/project-patients/", {"patient_phone": "13900001111"})
    no_match = auth_client.get("/api/studies/project-patients/", {"patient_name": "不存在"})

    assert by_name.status_code == 200, by_name.content
    assert by_phone.status_code == 200, by_phone.content
    assert no_match.status_code == 200, no_match.content
    assert [row["id"] for row in by_name.data] == [project_patient.id]
    assert [row["id"] for row in by_phone.data] == [project_patient.id]
    assert no_match.data == []
```

- [x] **Step 2: Run the backend tests and verify they fail**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/studies/tests/test_project_patient_visit_ids.py -q
```

Expected: FAIL because `project_name`, `project_status`, `visit_summaries`, `patient_name`, and `patient_phone` filter behavior are not implemented.

- [x] **Step 3: Extend `ProjectPatientSerializer`**

In `backend/apps/studies/serializers.py`, replace the current `ProjectPatientSerializer` class with this implementation:

```python
class ProjectPatientSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    patient_phone = serializers.CharField(source="patient.phone", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    project_status = serializers.CharField(source="project.status", read_only=True)
    group_name = serializers.SerializerMethodField()
    visit_ids = serializers.SerializerMethodField()
    visit_summaries = serializers.SerializerMethodField()

    class Meta:
        model = ProjectPatient
        fields = [
            "id",
            "project",
            "project_name",
            "project_status",
            "patient",
            "patient_name",
            "patient_phone",
            "group",
            "group_name",
            "enrolled_at",
            "visit_ids",
            "visit_summaries",
        ]
        read_only_fields = [
            "id",
            "enrolled_at",
            "project_name",
            "project_status",
            "patient_name",
            "patient_phone",
            "group_name",
            "visit_ids",
            "visit_summaries",
        ]

    def get_group_name(self, obj: ProjectPatient) -> str | None:
        return obj.group.name if obj.group_id else None

    def _visits_by_type(self, obj: ProjectPatient):
        cached = getattr(obj, "_prefetched_objects_cache", {}).get("visits")
        visits = cached if cached is not None else obj.visits.all()
        return {v.visit_type: v for v in visits}

    def get_visit_ids(self, obj: ProjectPatient) -> dict[str, int]:
        return {visit_type: v.id for visit_type, v in self._visits_by_type(obj).items()}

    def get_visit_summaries(self, obj: ProjectPatient) -> dict[str, dict[str, object]]:
        out: dict[str, dict[str, object]] = {}
        visits = self._visits_by_type(obj)
        for visit_type in ("T0", "T1", "T2"):
            v = visits.get(visit_type)
            if v is None:
                continue
            out[visit_type] = {
                "id": v.id,
                "status": v.status,
                "visit_date": v.visit_date.isoformat() if v.visit_date else None,
            }
        return out
```

- [x] **Step 4: Extend `ProjectPatientViewSet.get_queryset()`**

In `backend/apps/studies/views.py`, add `Prefetch` to the imports:

```python
from django.db.models import Count, Prefetch
```

Add the import inside the existing local import block at the top level:

```python
from apps.visits.models import VisitRecord
```

Replace `ProjectPatientViewSet.queryset` with:

```python
queryset = ProjectPatient.objects.select_related("project", "patient", "group").prefetch_related(
    Prefetch("visits", queryset=VisitRecord.objects.only("id", "project_patient_id", "visit_type", "status", "visit_date"))
).order_by("-id")
```

Then replace `ProjectPatientViewSet.get_queryset()` with:

```python
def get_queryset(self):
    qs = super().get_queryset()
    project_id = self.request.query_params.get("project")
    if project_id:
        qs = qs.filter(project_id=project_id)
    patient_id = self.request.query_params.get("patient")
    if patient_id:
        qs = qs.filter(patient_id=patient_id)
    patient_name = self.request.query_params.get("patient_name")
    if patient_name:
        qs = qs.filter(patient__name__icontains=patient_name)
    patient_phone = self.request.query_params.get("patient_phone")
    if patient_phone:
        qs = qs.filter(patient__phone__icontains=patient_phone)
    return qs
```

- [x] **Step 5: Run focused backend tests**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/studies/tests/test_project_patient_visit_ids.py -q
```

Expected: PASS.

- [x] **Step 6: Commit backend project-patient contract**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add backend/apps/studies/serializers.py backend/apps/studies/views.py backend/apps/studies/tests/test_project_patient_visit_ids.py
git commit -m "feat(studies): 扩展项目患者访视摘要"
```

---

### Task 2: Backend Completed Visit Readonly Rule

**Files:**
- Modify: `backend/apps/visits/views.py`
- Modify: `backend/apps/visits/tests/test_status_transition.py`

- [x] **Step 1: Replace the old editable-completed test**

In `backend/apps/visits/tests/test_status_transition.py`, replace `test_completed_visit_still_editable` with these two tests:

```python
@pytest.mark.django_db
def test_completed_visit_rejects_form_data_patch(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.status = VisitRecord.Status.COMPLETED
    visit.form_data = {"assessments": {"sppb": {"total": 8}}, "computed_assessments": {}}
    visit.save()

    r = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )

    assert r.status_code == 400, r.content
    assert "已完成访视只读" in str(r.data)
    visit.refresh_from_db()
    assert visit.form_data["assessments"]["sppb"]["total"] == 8
    assert visit.status == VisitRecord.Status.COMPLETED


@pytest.mark.django_db
def test_completed_visit_rejects_repeated_completed_patch(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.status = VisitRecord.Status.COMPLETED
    visit.save(update_fields=["status"])

    r = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"status": VisitRecord.Status.COMPLETED},
        format="json",
    )

    assert r.status_code == 400, r.content
    assert "已完成访视只读" in str(r.data)
```

- [x] **Step 2: Run the visit status tests and verify failure**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/visits/tests/test_status_transition.py -q
```

Expected: FAIL because completed visits are still editable.

- [x] **Step 3: Add completed-visit guard**

In `backend/apps/visits/views.py`, add this import:

```python
from rest_framework.exceptions import ValidationError
```

Then add this helper method inside `VisitRecordViewSet` before `perform_update`:

```python
def _ensure_current_visit_writable(self, visit: VisitRecord) -> None:
    if visit.status == VisitRecord.Status.COMPLETED:
        raise ValidationError({"detail": "已完成访视只读，不能继续编辑。"})
```

Update `perform_update` to:

```python
def perform_update(self, serializer):
    visit = self.get_object()
    self._ensure_current_visit_writable(visit)
    ensure_project_open(visit.project_patient.project)
    target_project_patient = serializer.validated_data.get("project_patient", visit.project_patient)
    ensure_project_open(target_project_patient.project)
    serializer.save()
```

- [x] **Step 4: Run backend visit tests**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/visits/tests/test_status_transition.py apps/visits/tests/test_visit_form_data_contract.py -q
```

Expected: PASS.

- [x] **Step 5: Commit completed-readonly backend rule**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add backend/apps/visits/views.py backend/apps/visits/tests/test_status_transition.py
git commit -m "fix(visits): 完成态访视改为只读"
```

---

### Task 3: Extract Reusable Visit Form Content And Enforce Frontend Readonly

**Files:**
- Create: `frontend/src/pages/visits/VisitFormContent.tsx`
- Modify: `frontend/src/pages/visits/VisitFormPage.tsx`
- Modify: `frontend/src/pages/visits/VisitFormPage.test.tsx`

- [x] **Step 1: Add the failing completed-readonly frontend test**

Append this test to `frontend/src/pages/visits/VisitFormPage.test.tsx`:

```tsx
  it("renders completed visits as readonly and blocks mutations", async () => {
    mockGet.mockResolvedValue({
      data: {
        id: 22,
        project_patient: 1,
        project_status: "active",
        visit_type: "T0",
        status: "completed",
        visit_date: null,
        form_data: {
          assessments: { sppb: { total: 9 } },
          computed_assessments: {},
          crf: { adherence: { platform_id: "PID-99" } },
        },
      },
    });

    const r = renderAt(22);

    expect(await screen.findByText("访视已完成，当前为只读查看。")).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "SPPB 总分" })).toBeDisabled();
    expect(screen.getByLabelText("平台账号/编号")).toBeDisabled();

    const saveBtn = r.container.querySelector('button[aria-label="保存"]');
    const completeBtn = r.container.querySelector('button[aria-label="标记已完成"]');
    expect(saveBtn).toBeDisabled();
    expect(completeBtn).toBeDisabled();

    fireEvent.click(saveBtn as Element);
    fireEvent.click(completeBtn as Element);
    expect(mockPatch).not.toHaveBeenCalled();
  });
```

- [x] **Step 2: Run the focused frontend test and verify failure**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run test -- VisitFormPage.test.tsx
```

Expected: FAIL because completed visits do not show the new readonly alert and core assessment controls are not disabled by completed status.

- [x] **Step 3: Create `VisitFormContent.tsx` by moving the existing form implementation**

Create `frontend/src/pages/visits/VisitFormContent.tsx` by copying the current contents of `VisitFormPage.tsx`, then make these exact changes:

1. Remove `useParams` from the import:

```tsx
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
```

2. Add the props type before the component:

```tsx
type VisitFormContentProps = {
  visitId: number;
  title?: string;
  timeDescription?: string;
};
```

3. Rename the exported component and replace route param parsing:

```tsx
export function VisitFormContent({ visitId, title = "访视表单", timeDescription }: VisitFormContentProps) {
  const id = visitId;
```

4. Replace the readonly calculation block with:

```tsx
  const isCompletedVisit = visit?.status === "completed";
  const isArchivedProject = visit?.project_status === "archived";
  const isVisitReadonly = Boolean(isCompletedVisit || isArchivedProject);
```

5. Change the `<Card>` title:

```tsx
    <Card title={title} loading={isLoading} extra={headerExtra}>
```

6. Add this alert after the computed-prefill alert and before the archived-project alert:

```tsx
          {isCompletedVisit && (
            <Alert
              type="info"
              showIcon
              message="访视已完成，当前为只读查看。"
            />
          )}

          {timeDescription && (
            <Alert
              type="info"
              showIcon
              message={timeDescription}
            />
          )}
```

7. Replace every `disabled={isArchivedProject}` and every `disabled={visit.status === "completed" || isArchivedProject}` with `disabled={isVisitReadonly}`.

8. Replace the save button disabled prop:

```tsx
                disabled={isVisitReadonly}
```

9. Replace the complete button disabled prop:

```tsx
                disabled={isVisitReadonly}
```

- [x] **Step 4: Replace `VisitFormPage.tsx` with a route wrapper**

Replace `frontend/src/pages/visits/VisitFormPage.tsx` with:

```tsx
import { Alert } from "antd";
import { useParams } from "react-router-dom";

import { VisitFormContent } from "./VisitFormContent";

export function VisitFormPage() {
  const { visitId } = useParams<{ visitId: string }>();
  const id = Number(visitId);

  if (!Number.isFinite(id)) {
    return <Alert type="error" message="无效的访视 ID" />;
  }

  return <VisitFormContent visitId={id} />;
}
```

- [x] **Step 5: Run visit form tests**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run test -- VisitFormPage.test.tsx
```

Expected: PASS.

- [x] **Step 6: Commit reusable visit form extraction**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add frontend/src/pages/visits/VisitFormContent.tsx frontend/src/pages/visits/VisitFormPage.tsx frontend/src/pages/visits/VisitFormPage.test.tsx
git commit -m "refactor(frontend): 抽出可复用访视表单"
```

---

### Task 4: ProjectPatient Research Entry Tab Page

**Files:**
- Create: `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx`
- Create: `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.test.tsx`
- Modify: `frontend/src/app/App.tsx`

- [x] **Step 1: Write the failing tab page tests**

Create `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectPatientResearchEntryPage } from "./ProjectPatientResearchEntryPage";

const { mockGet, mockPatch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPatch: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
  },
}));

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/research-entry/project-patients/:projectPatientId" element={<ProjectPatientResearchEntryPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const projectPatient = {
  id: 9001,
  project: 1,
  project_name: "研究项目 A",
  project_status: "active",
  patient: 201,
  patient_name: "项目患者甲",
  patient_phone: "13800000201",
  group: 10,
  group_name: "试验组",
  enrolled_at: "2026-05-12T10:00:00+08:00",
  visit_ids: { T0: 11, T1: 12, T2: 13 },
  visit_summaries: {
    T0: { id: 11, status: "completed", visit_date: "2026-05-12" },
    T1: { id: 12, status: "draft", visit_date: null },
    T2: { id: 13, status: "draft", visit_date: null },
  },
};

describe("ProjectPatientResearchEntryPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPatch.mockReset();
    mockPatch.mockResolvedValue({ data: {} });
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/project-patients/9001/") return Promise.resolve({ data: projectPatient });
      if (url === "/visits/11/") {
        return Promise.resolve({
          data: {
            id: 11,
            project_patient: 9001,
            project_status: "active",
            visit_type: "T0",
            status: "completed",
            visit_date: "2026-05-12",
            form_data: { assessments: { sppb: { total: 9 } }, computed_assessments: {}, crf: {} },
          },
        });
      }
      if (url === "/visits/12/") {
        return Promise.resolve({
          data: {
            id: 12,
            project_patient: 9001,
            project_status: "active",
            visit_type: "T1",
            status: "draft",
            visit_date: null,
            form_data: { assessments: {}, computed_assessments: {}, crf: {} },
          },
        });
      }
      if (url === "/visits/13/") {
        return Promise.resolve({
          data: {
            id: 13,
            project_patient: 9001,
            project_status: "active",
            visit_type: "T2",
            status: "draft",
            visit_date: null,
            form_data: { assessments: {}, computed_assessments: {}, crf: {} },
          },
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  afterEach(() => cleanup());

  it("defaults to first unfinished visit when no query visit is provided", async () => {
    renderAt("/research-entry/project-patients/9001");

    expect(await screen.findByText("项目患者甲 · 研究项目 A")).toBeInTheDocument();
    expect(screen.getByText("试验组")).toBeInTheDocument();
    expect(screen.getByText(/干预 12 周节点/)).toBeInTheDocument();
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("/visits/12/"));
  });

  it("opens the query-selected tab", async () => {
    renderAt("/research-entry/project-patients/9001?visit=T0");

    expect(await screen.findByText(/筛选\/入组节点/)).toBeInTheDocument();
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("/visits/11/"));
    expect(await screen.findByText("访视已完成，当前为只读查看。")).toBeInTheDocument();
  });

  it("renders baseline and CRF links in project context", async () => {
    renderAt("/research-entry/project-patients/9001?visit=T1");

    expect(await screen.findByRole("link", { name: "基线资料" })).toHaveAttribute("href", "/patients/201/crf-baseline");
    expect(screen.getByRole("link", { name: "打开 CRF" })).toHaveAttribute("href", "/crf?projectPatientId=9001");
  });
});
```

- [x] **Step 2: Run the new test and verify failure**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run test -- ProjectPatientResearchEntryPage.test.tsx
```

Expected: FAIL because the component does not exist.

- [x] **Step 3: Create the tab page component**

Create `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Descriptions, Space, Tabs, Tag } from "antd";
import { useMemo } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { VisitFormContent } from "../visits/VisitFormContent";

type VisitType = "T0" | "T1" | "T2";

type VisitSummary = {
  id: number;
  status: "draft" | "completed";
  visit_date: string | null;
};

type ProjectPatientDetail = {
  id: number;
  project: number;
  project_name: string;
  project_status: "draft" | "active" | "archived";
  patient: number;
  patient_name: string;
  patient_phone: string;
  group: number | null;
  group_name: string | null;
  enrolled_at: string;
  visit_ids?: Partial<Record<VisitType, number>>;
  visit_summaries?: Partial<Record<VisitType, VisitSummary>>;
};

const VISIT_TYPES: VisitType[] = ["T0", "T1", "T2"];

const TIME_DESCRIPTIONS: Record<VisitType, string> = {
  T0: "筛选/入组节点；填写访视信息、知情同意、纳排、筛选结论，以及 T0 基线评估类字段。",
  T1: "干预 12 周节点；填写依从性、身体机能、MoCA、满意度、合并用药变化、不良事件等。",
  T2: "干预后 36 周节点；填写依从性、身体机能、MoCA、满意度、合并用药变化、不良事件、完成/退出与质控核查字段。",
};

function isVisitType(v: string | null): v is VisitType {
  return v === "T0" || v === "T1" || v === "T2";
}

function visitStatusLabel(summary: VisitSummary | undefined): string {
  if (!summary) return "访视未生成";
  return summary.status === "completed" ? "已完成" : "草稿";
}

function firstOpenVisit(row: ProjectPatientDetail): VisitType {
  for (const vt of VISIT_TYPES) {
    if (row.visit_summaries?.[vt]?.status !== "completed") return vt;
  }
  return "T0";
}

export function ProjectPatientResearchEntryPage() {
  const { projectPatientId } = useParams<{ projectPatientId: string }>();
  const id = Number(projectPatientId);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["project-patient", id],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientDetail>(`/studies/project-patients/${id}/`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  const activeVisit = useMemo<VisitType>(() => {
    const requested = searchParams.get("visit");
    if (isVisitType(requested)) return requested;
    return data ? firstOpenVisit(data) : "T0";
  }, [data, searchParams]);

  if (!Number.isFinite(id)) return <Alert type="error" message="无效的项目患者 ID" />;
  if (isError) return <Alert type="error" message="记录不存在或无权限访问" />;

  const items = VISIT_TYPES.map((vt) => {
    const summary = data?.visit_summaries?.[vt];
    const visitId = summary?.id ?? data?.visit_ids?.[vt];
    return {
      key: vt,
      label: (
        <Space>
          <span>{vt}</span>
          <Tag color={summary?.status === "completed" ? "green" : summary ? "default" : "red"}>
            {visitStatusLabel(summary)}
          </Tag>
        </Space>
      ),
      children: visitId ? (
        <VisitFormContent
          visitId={visitId}
          title={`${vt} 访视录入`}
          timeDescription={TIME_DESCRIPTIONS[vt]}
        />
      ) : (
        <Alert type="warning" showIcon message={`${vt} 访视未生成`} />
      ),
    };
  });

  return (
    <Card
      loading={isLoading}
      title={data ? `${data.patient_name} · ${data.project_name}` : "研究录入"}
      extra={
        data ? (
          <Space wrap>
            <Link to={`/patients/${data.patient}/crf-baseline`}>基线资料</Link>
            <Link to={`/crf?projectPatientId=${data.id}`}>打开 CRF</Link>
          </Space>
        ) : null
      }
    >
      {data && (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Descriptions size="small" bordered column={2}>
            <Descriptions.Item label="患者">{data.patient_name}</Descriptions.Item>
            <Descriptions.Item label="项目">{data.project_name}</Descriptions.Item>
            <Descriptions.Item label="分组">{data.group_name ?? "—"}</Descriptions.Item>
            <Descriptions.Item label="入组时间">{data.enrolled_at || "—"}</Descriptions.Item>
          </Descriptions>
          <Tabs
            activeKey={activeVisit}
            onChange={(key) => navigate(`/research-entry/project-patients/${id}?visit=${key}`)}
            items={items}
          />
        </Space>
      )}
    </Card>
  );
}
```

- [x] **Step 4: Register the route**

In `frontend/src/app/App.tsx`, add this import:

```tsx
import { ProjectPatientResearchEntryPage } from "../pages/research-entry/ProjectPatientResearchEntryPage";
```

Add this route immediately after `/research-entry`:

```tsx
<Route path="/research-entry/project-patients/:projectPatientId" element={<ProjectPatientResearchEntryPage />} />
```

- [x] **Step 5: Run focused frontend tests**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run test -- ProjectPatientResearchEntryPage.test.tsx VisitFormPage.test.tsx
```

Expected: PASS.

- [x] **Step 6: Commit research-entry tab page**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.test.tsx frontend/src/app/App.tsx
git commit -m "feat(frontend): 新增项目患者研究录入页"
```

---

### Task 5: ResearchEntry ProjectPatient List

**Files:**
- Modify: `frontend/src/pages/research-entry/ResearchEntryPage.tsx`
- Create: `frontend/src/pages/research-entry/ResearchEntryPage.test.tsx`
- Modify: `frontend/src/app/App.test.tsx`

- [x] **Step 1: Write the failing research-entry list tests**

Create `frontend/src/pages/research-entry/ResearchEntryPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ResearchEntryPage } from "./ResearchEntryPage";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/research-entry"]}>
        <Routes>
          <Route path="/research-entry" element={<ResearchEntryPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ResearchEntryPage", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/projects/") {
        return Promise.resolve({ data: [{ id: 1, name: "研究项目 A" }, { id: 2, name: "研究项目 B" }] });
      }
      if (url === "/studies/project-patients/") {
        return Promise.resolve({
          data: [
            {
              id: 9001,
              project: 1,
              project_name: "研究项目 A",
              project_status: "active",
              patient: 201,
              patient_name: "同名患者",
              patient_phone: "13800000201",
              group: 10,
              group_name: "试验组",
              enrolled_at: "2026-05-12T10:00:00+08:00",
              visit_ids: { T0: 11, T1: 12, T2: 13 },
              visit_summaries: {
                T0: { id: 11, status: "completed", visit_date: "2026-05-12" },
                T1: { id: 12, status: "draft", visit_date: null },
                T2: { id: 13, status: "draft", visit_date: null },
              },
            },
            {
              id: 9002,
              project: 2,
              project_name: "研究项目 B",
              project_status: "active",
              patient: 201,
              patient_name: "同名患者",
              patient_phone: "13800000201",
              group: 20,
              group_name: "对照组",
              enrolled_at: "2026-05-13T10:00:00+08:00",
              visit_ids: { T0: 21, T1: 22, T2: 23 },
              visit_summaries: {
                T0: { id: 21, status: "draft", visit_date: null },
                T1: { id: 22, status: "draft", visit_date: null },
                T2: { id: 23, status: "draft", visit_date: null },
              },
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  afterEach(() => cleanup());

  it("renders one row per project patient and no visit-type filter", async () => {
    renderPage();

    expect(await screen.findByText("研究项目 A")).toBeInTheDocument();
    expect(screen.getByText("研究项目 B")).toBeInTheDocument();
    expect(screen.getAllByText("同名患者").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("访视类型")).not.toBeInTheDocument();
  });

  it("links record and visit status to project-patient research-entry page", async () => {
    renderPage();

    const recordLinks = await screen.findAllByRole("link", { name: "录入" });
    expect(recordLinks[0]).toHaveAttribute("href", "/research-entry/project-patients/9001");
    expect(screen.getByRole("link", { name: /T1 草稿/ })).toHaveAttribute(
      "href",
      "/research-entry/project-patients/9001?visit=T1",
    );
    expect(screen.getByRole("link", { name: "基线资料" })).toHaveAttribute("href", "/patients/201/crf-baseline");
  });

  it("passes project and patient filters to backend", async () => {
    renderPage();

    await screen.findByText("研究项目 A");
    fireEvent.change(screen.getByPlaceholderText("患者姓名或手机号"), { target: { value: "同名" } });
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(
        "/studies/project-patients/",
        expect.objectContaining({ params: expect.objectContaining({ patient_name: "同名" }) }),
      );
    });
  });
});
```

- [x] **Step 2: Run the new test and verify failure**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run test -- ResearchEntryPage.test.tsx
```

Expected: FAIL because the page still uses `/visits/` and renders the visit-type filter.

- [x] **Step 3: Replace `ResearchEntryPage.tsx` with project-patient list**

Replace `frontend/src/pages/research-entry/ResearchEntryPage.tsx` with:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Input, Select, Space, Table, Tag } from "antd";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "../../api/client";

type StudyProject = { id: number; name: string };
type VisitType = "T0" | "T1" | "T2";
type VisitSummary = { id: number; status: "draft" | "completed"; visit_date: string | null };

type ProjectPatientRow = {
  id: number;
  project: number;
  project_name: string;
  project_status: "draft" | "active" | "archived";
  patient: number;
  patient_name: string;
  patient_phone: string;
  group: number | null;
  group_name: string | null;
  enrolled_at: string;
  visit_summaries?: Partial<Record<VisitType, VisitSummary>>;
};

const VISIT_TYPES: VisitType[] = ["T0", "T1", "T2"];

function statusTag(summary: VisitSummary | undefined) {
  if (!summary) return <Tag color="red">访视未生成</Tag>;
  return (
    <Tag color={summary.status === "completed" ? "green" : "default"}>
      {summary.status === "completed" ? "已完成" : "草稿"}
      {summary.visit_date ? ` · ${summary.visit_date}` : ""}
    </Tag>
  );
}

export function ResearchEntryPage() {
  const [projectId, setProjectId] = useState<number | undefined>();
  const [patientNameDraft, setPatientNameDraft] = useState("");
  const [patientNameQuery, setPatientNameQuery] = useState("");

  const { data: projects = [] } = useQuery({
    queryKey: ["study-projects"],
    queryFn: async () => {
      const r = await apiClient.get<StudyProject[]>("/studies/projects/");
      return r.data;
    },
  });

  const queryParams = useMemo(() => {
    const p: Record<string, string | number> = {};
    if (projectId) p.project = projectId;
    if (patientNameQuery.trim()) p.patient_name = patientNameQuery.trim();
    return p;
  }, [projectId, patientNameQuery]);

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["project-patients", "research-entry", queryParams],
    queryFn: async () => {
      const r = await apiClient.get<ProjectPatientRow[]>("/studies/project-patients/", { params: queryParams });
      return r.data;
    },
  });

  return (
    <Card title="研究录入">
      <Space wrap style={{ marginBottom: 16 }} align="center">
        <span>项目</span>
        <Select
          allowClear
          placeholder="全部"
          style={{ width: 220 }}
          value={projectId}
          onChange={setProjectId}
          options={projects.map((p) => ({ value: p.id, label: p.name }))}
        />
        <span>患者</span>
        <Input
          allowClear
          placeholder="患者姓名或手机号"
          style={{ width: 180 }}
          value={patientNameDraft}
          onChange={(e) => setPatientNameDraft(e.target.value)}
          onPressEnter={() => setPatientNameQuery(patientNameDraft)}
        />
        <Button type="primary" onClick={() => setPatientNameQuery(patientNameDraft)}>
          查询
        </Button>
      </Space>

      <Table<ProjectPatientRow>
        rowKey="id"
        loading={isLoading}
        dataSource={rows}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        columns={[
          {
            title: "患者",
            dataIndex: "patient_name",
            render: (t: string, r) => (
              <>
                {t} · {r.patient_phone}
              </>
            ),
          },
          { title: "项目", dataIndex: "project_name" },
          {
            title: "分组",
            dataIndex: "group_name",
            render: (v: string | null) => v ?? "—",
          },
          {
            title: "T0 / T1 / T2",
            render: (_: unknown, r) => (
              <Space wrap>
                {VISIT_TYPES.map((vt) => (
                  <Link key={vt} to={`/research-entry/project-patients/${r.id}?visit=${vt}`}>
                    {vt} {statusTag(r.visit_summaries?.[vt])}
                  </Link>
                ))}
              </Space>
            ),
          },
          {
            title: "操作",
            render: (_: unknown, r) => (
              <Space>
                <Link to={`/research-entry/project-patients/${r.id}`}>录入</Link>
                <Link to={`/patients/${r.patient}/crf-baseline`}>基线资料</Link>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
```

- [x] **Step 4: Update `App.test.tsx` research-entry smoke expectation**

In `frontend/src/app/App.test.tsx`, update the `/studies/project-patients/` mock rows to include `project_name`, `project_status`, `enrolled_at`, and `visit_summaries`.

Replace the final research-entry route expectation:

```tsx
await waitFor(() => {
  expect(screen.getByPlaceholderText("患者姓名或手机号")).toBeInTheDocument();
});
```

- [x] **Step 5: Run focused tests**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run test -- ResearchEntryPage.test.tsx App.test.tsx
```

Expected: PASS.

- [x] **Step 6: Commit research-entry list**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add frontend/src/pages/research-entry/ResearchEntryPage.tsx frontend/src/pages/research-entry/ResearchEntryPage.test.tsx frontend/src/app/App.test.tsx
git commit -m "feat(frontend): 研究录入改为项目患者列表"
```

---

### Task 6: Baseline Naming And Patient/Project Entry Links

**Files:**
- Modify: `frontend/src/pages/patients/PatientCrfBaselinePage.tsx`
- Modify: `frontend/src/pages/patients/PatientDetailPage.tsx`
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
- Modify: `frontend/src/app/App.test.tsx`
- Test: `frontend/src/pages/patients/PatientDetailPage.tsx` via `App.test.tsx`
- Test: `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`

- [x] **Step 1: Add patient detail route assertions to `App.test.tsx`**

Append this test to `frontend/src/app/App.test.tsx`:

```tsx
  it("patient detail uses baseline资料 and project research-entry without CRF link", async () => {
    window.history.pushState({}, "", "/patients/201");
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "基线资料" })).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "研究录入" })).toHaveAttribute(
      "href",
      "/research-entry/project-patients/9001",
    );
    expect(screen.queryByRole("link", { name: "打开 CRF" })).not.toBeInTheDocument();
    expect(screen.queryByText(/CRF 基线/)).not.toBeInTheDocument();
  });
```

Extend the existing mock for `/patients/201/` in `App.test.tsx`:

```tsx
if (url === "/patients/201/") {
  return Promise.resolve({
    data: {
      id: 201,
      name: "项目患者甲",
      gender: "male",
      phone: "13800000201",
      birth_date: null,
      primary_doctor_name: "测试医生",
      symptom_note: "",
      is_active: true,
    },
  });
}
```

Extend the existing `/studies/project-patients/` mock so `params.patient === 201` returns one row:

```tsx
if (p.patient === 201) {
  return Promise.resolve({
    data: [
      {
        id: 9001,
        project: 1,
        project_name: "研究项目 A",
        project_status: "active",
        patient: 201,
        patient_name: "项目患者甲",
        patient_phone: "13800000201",
        group: 10,
        group_name: "试验组",
        enrolled_at: "2026-05-12T10:00:00+08:00",
        visit_ids: { T0: 11, T1: 12, T2: 13 },
        visit_summaries: {
          T0: { id: 11, status: "completed", visit_date: "2026-05-12" },
          T1: { id: 12, status: "draft", visit_date: null },
          T2: { id: 13, status: "draft", visit_date: null },
        },
      },
    ],
  });
}
```

- [x] **Step 2: Run the failing patient detail test**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run test -- App.test.tsx
```

Expected: FAIL because patient detail still shows `CRF 基线录入` and `打开 CRF`.

- [x] **Step 3: Rename baseline page title**

In `frontend/src/pages/patients/PatientCrfBaselinePage.tsx`, change:

```tsx
title="患者 CRF 基线信息"
```

to:

```tsx
title="患者基础基线资料"
```

- [x] **Step 4: Update patient detail buttons and table action**

In `frontend/src/pages/patients/PatientDetailPage.tsx`, change the top baseline button:

```tsx
<Button onClick={() => navigate(`/patients/${id}/crf-baseline`)}>基线资料</Button>
```

Replace the project row action column render with:

```tsx
render: (_: unknown, row) => (
  <Link to={`/research-entry/project-patients/${row.id}`}>研究录入</Link>
),
```

Remove the stale `<Alert>` block with message `随访与访视`.

- [x] **Step 5: Add project-context links on confirmed patient cards**

In `frontend/src/pages/projects/ProjectGroupingBoard.tsx`, inside `ConfirmedPatientCard`, add these links after the existing patient detail link:

```tsx
<Link to={`/research-entry/project-patients/${row.id}`}>研究录入</Link>
<Link to={`/crf?projectPatientId=${row.id}`}>打开 CRF</Link>
```

The resulting action span for confirmed cards should contain:

```tsx
<span className="patient-card-actions">
  <Link to={`/patients/${row.patient}`}>详情</Link>
  <Link to={`/research-entry/project-patients/${row.id}`}>研究录入</Link>
  <Link to={`/crf?projectPatientId=${row.id}`}>打开 CRF</Link>
  {readOnly ? null : (
    <Button type="link" danger size="small" style={{ padding: 0 }} onClick={() => onRequestUnbind(row)}>
      解绑
    </Button>
  )}
</span>
```

- [x] **Step 6: Update or add grouping-board link assertion**

In `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`, add an assertion in the existing test that renders confirmed patients:

```tsx
expect(screen.getAllByRole("link", { name: "研究录入" })[0]).toHaveAttribute(
  "href",
  "/research-entry/project-patients/9001",
);
expect(screen.getAllByRole("link", { name: "打开 CRF" })[0]).toHaveAttribute(
  "href",
  "/crf?projectPatientId=9001",
);
```

If the fixture row id is not `9001`, use that fixture’s `ProjectPatientRow.id` in the expected href.

- [x] **Step 7: Run focused frontend tests**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run test -- App.test.tsx ProjectGroupingBoard.test.tsx
```

Expected: PASS.

- [x] **Step 8: Commit naming and entry-link changes**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add frontend/src/pages/patients/PatientCrfBaselinePage.tsx frontend/src/pages/patients/PatientDetailPage.tsx frontend/src/pages/projects/ProjectGroupingBoard.tsx frontend/src/pages/projects/ProjectGroupingBoard.test.tsx frontend/src/app/App.test.tsx
git commit -m "feat(frontend): 调整基线资料与研究录入口径"
```

---

### Task 7: Final Verification And Plan Bookkeeping

**Files:**
- Modify: `docs/superpowers/plans/2026-05-14-project-patient-research-entry-tabs.md`

- [x] **Step 1: Run backend focused suite**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/studies/tests/test_project_patient_visit_ids.py apps/visits/tests/test_status_transition.py apps/visits/tests/test_visit_form_data_contract.py apps/crf/tests/test_crf_aggregate.py -q
```

Expected: PASS.

- [x] **Step 2: Run frontend focused suite**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run test -- VisitFormPage.test.tsx ProjectPatientResearchEntryPage.test.tsx ResearchEntryPage.test.tsx App.test.tsx ProjectGroupingBoard.test.tsx
```

Expected: PASS.

- [x] **Step 3: Run full frontend validation**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run lint
npm run build
```

Expected: PASS for both commands.

- [x] **Step 4: Run full backend validation**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest -q
```

Expected: PASS.

- [x] **Step 5: Update plan checkboxes and execution record**

After Task 7 Step 4 passes, run:

```bash
cd /Users/nick/my_dev/workout/MotionCare
git rev-parse --short HEAD
```

Copy the printed short SHA. At the top of this file, add an execution record in this form: `执行记录（2026-05-14, codex）：Task 1-7 已落地于 commit ` followed by the copied short SHA on the same line.

Then mark completed steps from `- [ ]` to `- [x]`.

- [x] **Step 6: Commit plan bookkeeping**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add docs/superpowers/plans/2026-05-14-project-patient-research-entry-tabs.md
git commit -m "docs(plan): 标记项目患者研究录入实施完成"
```

---

## Self-Review

**Spec coverage:** Task 1 covers `ProjectPatient` summary and filters. Task 2 covers completed-readonly backend rule. Task 3 covers reusable visit form and completed-readonly frontend rule. Task 4 covers `/research-entry/project-patients/:id` with T0/T1/T2 tabs, time descriptions, baseline and CRF links. Task 5 covers project-patient research-entry list. Task 6 covers “患者基础基线资料” title, “基线资料” entry label, patient-detail CRF removal, and project-context CRF links. Task 7 covers final verification.

**Placeholder scan:** No deferred implementation markers are intentionally left in this plan.

**Type consistency:** The plan uses `VisitType = "T0" | "T1" | "T2"`, `VisitSummary`, `visit_summaries`, `project_status`, and `ProjectPatient` property names consistently across backend serializer, frontend pages, and tests.
