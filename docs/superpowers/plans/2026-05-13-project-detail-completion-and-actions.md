# 项目详情动作区与项目完结 Implementation Plan

执行记录（2026-05-13, Codex）：Task 1-7 已完成；未提交（用户未要求 commit）；验证通过：`cd backend && pytest`、`cd frontend && npm run test`、`cd frontend && npm run lint`、`cd frontend && npm run build`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目详情页的分组动作统一到右上角，并用现有 `archived` 状态实现项目完结后的服务端写入阻断和前端只读体验。

**Architecture:** 后端新增项目完结动作和统一项目状态守卫，所有会新增入组、修改分组或写访视的入口在服务端拒绝已完结项目；CRF 预览和导出保持只读可用。前端由 `ProjectDetailPage` 统一持有右上角按钮，通过 `ProjectGroupingBoard` 的 imperative handle 触发随机/确认逻辑，并将 `archived` 项目传入子组件进入只读模式。

**Tech Stack:** Django 5 + DRF + pytest-django；React 18 + TypeScript + Ant Design 5 + TanStack Query v5 + Vitest/Testing Library。

---

## Execution Notes

- 本计划对应 spec：`docs/superpowers/specs/2026-05-13-project-detail-completion-and-actions-design.md`。
- 当前仓库规则 `AGENTS.md §7` 写明“不要主动 commit”。每个任务中的提交步骤仅在用户明确要求提交时执行；提交信息必须使用中文。
- 本计划不新增数据库字段，不需要 migration。
- 所有写入口的最终边界必须在后端，前端禁用只作为 UX。

## File Structure

- Create: `backend/apps/studies/project_status.py`
  - 存放项目完结判断、统一错误文案和 `ensure_project_open()`，避免多个 view 复制状态判断。
- Modify: `backend/apps/studies/views.py`
  - 新增 `StudyProjectViewSet.complete` 动作。
  - 在 `confirm_grouping`、`StudyGroupViewSet` 创建/更新/删除、`ProjectPatientViewSet.unbind` 加项目完结守卫。
- Modify: `backend/apps/patients/views.py`
  - `enroll_projects` 拒绝已完结项目。
- Modify: `backend/apps/visits/serializers.py`
  - Visit 详情响应增加 `project_id`、`project_name`、`project_status`，供前端访视表单只读判断。
- Modify: `backend/apps/visits/views.py`
  - `perform_update` 拒绝已完结项目的 `PATCH/PUT`。
- Create: `backend/apps/studies/tests/test_project_completion.py`
  - 覆盖完结接口、确认分组、分组配置、解绑和只读接口。
- Modify: `backend/apps/patients/tests/test_enroll_projects.py`
  - 覆盖患者详情直接入组拒绝已完结项目。
- Modify: `backend/apps/visits/tests/test_status_transition.py`
  - 覆盖访视详情带项目状态、已完结项目拒绝访视写入。
- Create: `backend/apps/crf/tests/test_project_completion_crf_api.py`
  - 覆盖已完结项目仍允许 CRF 预览和导出。
- Modify: `frontend/src/pages/projects/ProjectDetailPage.tsx`
  - 统一右上角按钮，新增项目完结二次确认，向看板/分组配置传递只读状态。
- Modify: `frontend/src/pages/projects/ProjectListPage.tsx`
  - 将 `archived` 项目状态文案从“已归档”统一为“已完结”。
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
  - 使用 `forwardRef/useImperativeHandle` 暴露随机、确认、清空草案；移除内部工具条；支持只读模式。
- Modify: `frontend/src/pages/projects/ProjectGroupsTab.tsx`
  - 增加 `readOnly`，已完结项目禁用新建分组。
- Modify: `frontend/src/pages/patients/components/EnrollProjectsModal.tsx`
  - 项目类型增加 `status`，过滤已完结项目。
- Modify: `frontend/src/pages/visits/VisitFormPage.tsx`
  - 使用 `project_status` 进入只读状态并禁用输入/保存/完成。
- Modify: frontend tests:
  - `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`
  - `frontend/src/app/App.test.tsx`
  - `frontend/src/pages/patients/components/EnrollProjectsModal.test.tsx`
  - `frontend/src/pages/visits/VisitFormPage.test.tsx`
  - `frontend/src/pages/crf/CrfPreviewPage.test.tsx`

---

## Task 1: 后端项目完结状态与写入守卫

**Files:**
- Create: `backend/apps/studies/project_status.py`
- Modify: `backend/apps/studies/views.py`
- Create: `backend/apps/studies/tests/test_project_completion.py`

- [x] **Step 1: 新建后端测试文件，先覆盖完结接口和 studies 写入口**

Create `backend/apps/studies/tests/test_project_completion.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.visits.services import ensure_default_visits


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _patient(doctor, name="患者乙", phone="13900000222"):
    return Patient.objects.create(name=name, phone=phone, primary_doctor=doctor)


@pytest.mark.django_db
def test_complete_project_sets_archived_and_is_idempotent(doctor, project):
    client = _client(doctor)

    first = client.post(f"/api/studies/projects/{project.id}/complete/")
    assert first.status_code == 200, first.data
    assert first.data["status"] == StudyProject.Status.ARCHIVED

    project.refresh_from_db()
    assert project.status == StudyProject.Status.ARCHIVED

    second = client.post(f"/api/studies/projects/{project.id}/complete/")
    assert second.status_code == 200, second.data
    assert second.data["status"] == StudyProject.Status.ARCHIVED


@pytest.mark.django_db
def test_completed_project_rejects_confirm_grouping_without_saving_ratios(doctor, project):
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=50)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=50)
    patient = _patient(doctor)

    response = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "group_ratios": [
                {"group_id": g1.id, "target_ratio": 60},
                {"group_id": g2.id, "target_ratio": 40},
            ],
            "assignments": [{"patient_id": patient.id, "group_id": g1.id}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    g1.refresh_from_db()
    g2.refresh_from_db()
    assert (g1.target_ratio, g2.target_ratio) == (50, 50)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()


@pytest.mark.django_db
def test_completed_project_rejects_group_create_update_and_delete(doctor, project):
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=100)
    client = _client(doctor)

    create_response = client.post(
        "/api/studies/groups/",
        {
            "project": project.id,
            "name": "新增组",
            "description": "",
            "target_ratio": 100,
            "sort_order": 1,
            "is_active": True,
        },
        format="json",
    )
    assert create_response.status_code == 400
    assert "项目已完结" in str(create_response.data)
    assert not StudyGroup.objects.filter(project=project, name="新增组").exists()

    update_response = client.patch(
        f"/api/studies/groups/{group.id}/",
        {"name": "修改后"},
        format="json",
    )
    assert update_response.status_code == 400
    assert "项目已完结" in str(update_response.data)
    group.refresh_from_db()
    assert group.name == "干预组"

    delete_response = client.delete(f"/api/studies/groups/{group.id}/")
    assert delete_response.status_code == 400
    assert "项目已完结" in str(delete_response.data)
    assert StudyGroup.objects.filter(id=group.id).exists()


@pytest.mark.django_db
def test_completed_project_rejects_unbind_project_patient(doctor, project, patient):
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=100)
    project_patient = ProjectPatient.objects.create(project=project, patient=patient, group=group)
    ensure_default_visits(project_patient)
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])

    response = _client(doctor).post(f"/api/studies/project-patients/{project_patient.id}/unbind/")

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    assert ProjectPatient.objects.filter(id=project_patient.id).exists()


@pytest.mark.django_db
def test_completed_project_readonly_study_endpoints_still_work(doctor, project, patient):
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=100)
    project_patient = ProjectPatient.objects.create(project=project, patient=patient, group=group)
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])
    client = _client(doctor)

    detail_response = client.get(f"/api/studies/projects/{project.id}/")
    assert detail_response.status_code == 200
    assert detail_response.data["status"] == StudyProject.Status.ARCHIVED

    groups_response = client.get("/api/studies/groups/", {"project": project.id})
    assert groups_response.status_code == 200
    assert any(row["id"] == group.id for row in groups_response.data)

    project_patients_response = client.get("/api/studies/project-patients/", {"project": project.id})
    assert project_patients_response.status_code == 200
    assert any(row["id"] == project_patient.id for row in project_patients_response.data)
```

- [x] **Step 2: 运行 studies 完结测试确认失败**

Run:

```bash
cd backend && pytest apps/studies/tests/test_project_completion.py -q
```

Expected: FAIL，至少包含 `404` for `/complete/` 或完结项目仍允许写入的断言失败。

- [x] **Step 3: 新增统一项目状态守卫**

Create `backend/apps/studies/project_status.py`:

```python
from rest_framework.exceptions import ValidationError

from apps.studies.models import StudyProject


PROJECT_COMPLETED_DETAIL = "项目已完结，不能继续新增患者或录入访视。"
PROJECT_COMPLETED_GROUP_DETAIL = "项目已完结，不能修改分组配置。"
PROJECT_COMPLETED_UNBIND_DETAIL = "项目已完结，不能解绑患者。"


def is_project_completed(project: StudyProject) -> bool:
    return project.status == StudyProject.Status.ARCHIVED


def ensure_project_open(project: StudyProject, detail: str = PROJECT_COMPLETED_DETAIL) -> None:
    if is_project_completed(project):
        raise ValidationError({"detail": detail})
```

- [x] **Step 4: 在 `backend/apps/studies/views.py` 接入完结接口和守卫**

Modify imports at the top of `backend/apps/studies/views.py`:

```python
from apps.studies.project_status import (
    PROJECT_COMPLETED_GROUP_DETAIL,
    PROJECT_COMPLETED_UNBIND_DETAIL,
    ensure_project_open,
)
```

Inside `StudyProjectViewSet`, add this action after `destroy()`:

```python
    @action(detail=True, methods=["post"], url_path="complete")
    @transaction.atomic
    def complete(self, request, pk=None):
        project = StudyProject.objects.select_for_update(of=("self",)).get(pk=self.get_object().pk)
        if project.status != StudyProject.Status.ARCHIVED:
            project.status = StudyProject.Status.ARCHIVED
            project.save(update_fields=["status", "updated_at"])
        return Response(StudyProjectSerializer(project).data)
```

In `confirm_grouping()`, immediately after the locked project is loaded, add:

```python
        ensure_project_open(project)
```

Inside `StudyGroupViewSet`, replace the current `perform_create()` with these methods:

```python
    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        ensure_project_open(project, PROJECT_COMPLETED_GROUP_DETAIL)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        group = self.get_object()
        ensure_project_open(group.project, PROJECT_COMPLETED_GROUP_DETAIL)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        group = self.get_object()
        ensure_project_open(group.project, PROJECT_COMPLETED_GROUP_DETAIL)
        return super().destroy(request, *args, **kwargs)
```

In `ProjectPatientViewSet.unbind()`, add the status guard before calling `unbind_project_patient()`:

```python
        ensure_project_open(pp.project, PROJECT_COMPLETED_UNBIND_DETAIL)
```

- [x] **Step 5: 运行 studies 测试确认通过**

Run:

```bash
cd backend && pytest apps/studies/tests/test_project_completion.py apps/studies/tests/test_confirm_grouping.py apps/studies/tests/test_unbind_project_patient.py apps/studies/tests/test_study_project_delete_guard.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit checkpoint（仅用户要求提交时执行）**

```bash
git add backend/apps/studies/project_status.py backend/apps/studies/views.py backend/apps/studies/tests/test_project_completion.py
git commit -m "feat(studies): 支持项目完结与写入拦截"
```

---

## Task 2: 患者详情直接入组拒绝已完结项目

**Files:**
- Modify: `backend/apps/patients/views.py`
- Modify: `backend/apps/patients/tests/test_enroll_projects.py`

- [x] **Step 1: 添加后端失败测试**

Append to `backend/apps/patients/tests/test_enroll_projects.py`:

```python
@pytest.mark.django_db
def test_enroll_projects_rejects_completed_project(doctor, patient, project):
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])
    group = StudyGroup.objects.create(project=project, name="A", target_ratio=100)
    client = APIClient()
    client.force_authenticate(user=doctor)

    response = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {"enrollments": [{"project_id": project.id, "group_id": group.id}]},
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()
```

- [x] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend && pytest apps/patients/tests/test_enroll_projects.py::test_enroll_projects_rejects_completed_project -q
```

Expected: FAIL，因为当前 `enroll_projects` 仍会创建 `ProjectPatient`。

- [x] **Step 3: 在 `backend/apps/patients/views.py` 加状态校验**

Add import:

```python
from apps.studies.project_status import ensure_project_open
```

Replace the current project existence query block in `enroll_projects()` with:

```python
        existing_projects = {
            project.id: project
            for project in StudyProject.objects.filter(pk__in=project_ids)
        }
        missing_projects = sorted(project_ids - existing_projects.keys())
        if missing_projects:
            raise ValidationError({"detail": f"以下项目不存在: {missing_projects}"})

        for project_obj in existing_projects.values():
            ensure_project_open(project_obj)
```

Keep the remaining group validation and `already_linked` logic unchanged.

- [x] **Step 4: 运行患者入组测试确认通过**

Run:

```bash
cd backend && pytest apps/patients/tests/test_enroll_projects.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit checkpoint（仅用户要求提交时执行）**

```bash
git add backend/apps/patients/views.py backend/apps/patients/tests/test_enroll_projects.py
git commit -m "fix(patients): 完结项目不可直接入组"
```

---

## Task 3: 访视写入拒绝已完结项目，详情返回项目状态

**Files:**
- Modify: `backend/apps/visits/serializers.py`
- Modify: `backend/apps/visits/views.py`
- Modify: `backend/apps/visits/tests/test_status_transition.py`

- [x] **Step 1: 添加访视后端测试**

Append to `backend/apps/visits/tests/test_status_transition.py`:

```python
@pytest.mark.django_db
def test_visit_detail_includes_project_status(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")

    response = auth_client.get(f"/api/visits/{visit.id}/")

    assert response.status_code == 200, response.content
    assert response.data["project_id"] == project_patient.project_id
    assert response.data["project_name"] == project_patient.project.name
    assert response.data["project_status"] == project_patient.project.status


@pytest.mark.django_db
def test_completed_project_rejects_visit_patch(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    project = project_patient.project
    project.status = "archived"
    project.save(update_fields=["status"])

    response = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    visit.refresh_from_db()
    assert visit.form_data == {}
```

- [x] **Step 2: 运行访视测试确认失败**

Run:

```bash
cd backend && pytest apps/visits/tests/test_status_transition.py -q
```

Expected: FAIL，详情缺少 `project_status`，且已完结项目仍允许 PATCH。

- [x] **Step 3: 扩展 Visit serializer 响应字段**

In `backend/apps/visits/serializers.py`, add these fields to `VisitRecordSerializer` before `class Meta`:

```python
    project_id = serializers.IntegerField(source="project_patient.project_id", read_only=True)
    project_name = serializers.CharField(source="project_patient.project.name", read_only=True)
    project_status = serializers.CharField(source="project_patient.project.status", read_only=True)
```

Update `VisitRecordSerializer.Meta.fields` to include the new fields:

```python
        fields = [
            "id",
            "project_patient",
            "project_id",
            "project_name",
            "project_status",
            "visit_type",
            "status",
            "visit_date",
            "form_data",
        ]
```

- [x] **Step 4: 在 Visit view 中拒绝已完结项目写入**

In `backend/apps/visits/views.py`, add import:

```python
from apps.studies.project_status import ensure_project_open
```

Add this method inside `VisitRecordViewSet`:

```python
    def perform_update(self, serializer):
        visit = self.get_object()
        ensure_project_open(visit.project_patient.project)
        serializer.save()
```

- [x] **Step 5: 运行访视相关测试确认通过**

Run:

```bash
cd backend && pytest apps/visits/tests/test_status_transition.py apps/visits/tests/test_visit_form_data_contract.py apps/visits/tests/test_visit_list_api.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit checkpoint（仅用户要求提交时执行）**

```bash
git add backend/apps/visits/serializers.py backend/apps/visits/views.py backend/apps/visits/tests/test_status_transition.py
git commit -m "fix(visits): 完结项目访视改为只读"
```

---

## Task 4: CRF 预览和导出允许已完结项目

**Files:**
- Create: `backend/apps/crf/tests/test_project_completion_crf_api.py`

- [x] **Step 1: 添加 CRF API 测试**

Create `backend/apps/crf/tests/test_project_completion_crf_api.py`:

```python
from django.test import override_settings
import pytest
from rest_framework.test import APIClient

from apps.crf.models import CrfExport
from apps.studies.models import StudyProject


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_crf_preview_allowed_for_completed_project(doctor, project_patient):
    project = project_patient.project
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])

    response = _client(doctor).get(f"/api/crf/project-patients/{project_patient.id}/preview/")

    assert response.status_code == 200, response.content
    assert response.data["project_patient_id"] == project_patient.id
    assert response.data["project"]["name"] == project.name


@pytest.mark.django_db
def test_crf_export_allowed_for_completed_project(doctor, project_patient, tmp_path):
    project = project_patient.project
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])
    root_dir = tmp_path
    media_root = root_dir / "media"
    export_dir = media_root / "crf_exports"
    export_dir.mkdir(parents=True)

    with override_settings(ROOT_DIR=root_dir, MEDIA_ROOT=media_root, CRF_EXPORT_DIR=export_dir):
        response = _client(doctor).post(f"/api/crf/project-patients/{project_patient.id}/export/")

    assert response.status_code == 200, response.content
    assert CrfExport.objects.filter(project_patient=project_patient).exists()
    assert response.data["docx_file"]
```

- [x] **Step 2: 运行 CRF 测试确认通过**

Run:

```bash
cd backend && pytest apps/crf/tests/test_project_completion_crf_api.py -q
```

Expected: PASS。若失败，说明之前的 guard 错误地加到了 CRF 只读入口，需要移除该 guard。

- [ ] **Step 3: Commit checkpoint（仅用户要求提交时执行）**

```bash
git add backend/apps/crf/tests/test_project_completion_crf_api.py
git commit -m "test(crf): 完结项目仍允许预览和导出"
```

---

## Task 5: 项目详情右上角动作区和看板动作 refactor

**Files:**
- Modify: `frontend/src/pages/projects/ProjectDetailPage.tsx`
- Modify: `frontend/src/pages/projects/ProjectListPage.tsx`
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`
- Modify: `frontend/src/app/App.test.tsx`

- [x] **Step 1: 为 `ProjectGroupingBoard.test.tsx` 增加外部动作按钮 harness**

In `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`, update the import:

```tsx
import { useRef, useState } from "react";
import { Button } from "antd";
import {
  ProjectGroupingBoard,
  type ProjectGroupingBoardActionState,
  type ProjectGroupingBoardHandle,
} from "./ProjectGroupingBoard";
```

Add this helper after the mock setup:

```tsx
function BoardHarness({ readOnly = false }: { readOnly?: boolean }) {
  const boardRef = useRef<ProjectGroupingBoardHandle>(null);
  const [state, setState] = useState<ProjectGroupingBoardActionState>({
    hasActiveGroups: false,
    hasEligibleSelection: false,
    confirmLoading: false,
  });

  return (
    <>
      <Button
        type="primary"
        disabled={readOnly || !state.hasEligibleSelection || !state.hasActiveGroups}
        onClick={() => boardRef.current?.randomize()}
      >
        随机分组
      </Button>
      <Button
        type="primary"
        disabled={readOnly || !state.hasActiveGroups}
        loading={state.confirmLoading}
        onClick={() => boardRef.current?.confirm()}
      >
        确认分组
      </Button>
      <ProjectGroupingBoard
        ref={boardRef}
        projectId={1}
        readOnly={readOnly}
        onActionStateChange={setState}
      />
    </>
  );
}
```

- [x] **Step 2: 调整 ProjectGroupingBoard 测试渲染方式**

In `ProjectGroupingBoard.test.tsx`, for tests that click `随机分组` or `确认分组`, replace direct board rendering:

```tsx
<ProjectGroupingBoard projectId={1} />
```

with:

```tsx
<BoardHarness />
```

For tests that only inspect board content and do not click external action buttons, direct board rendering can remain. The group revision test may keep this render:

```tsx
<ProjectGroupingBoard projectId={1} groupRevision={0} />
```

Append this read-only test to `ProjectGroupingBoard.test.tsx`:

```tsx
  it("已完结项目下看板禁用选择、占比、删除、拖拽和解绑", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <BoardHarness readOnly />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("全量患者")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "随机分组" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "确认分组" })).toBeDisabled();
    expect(screen.getByLabelText(/选择患者 未入组甲/)).toBeDisabled();
    expect(screen.getByLabelText("试验组占比")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "删除试验组" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "解绑" })).not.toBeInTheDocument();
  });
```

- [x] **Step 3: 更新 App 集成测试覆盖右上角动作**

In `frontend/src/app/App.test.tsx`, inside `renders project detail as grouping board only`, after the existing `新增分组` assertion, add:

```tsx
    expect(screen.getByRole("button", { name: "随机分组" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认分组" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "项目完结" })).toBeInTheDocument();
    expect(screen.queryByText("占比与本轮随机结果仅在确认后保存。")).not.toBeInTheDocument();
```

Add a new project completion action test after it:

```tsx
  it("project detail complete action posts complete endpoint", async () => {
    window.history.pushState({}, "", "/projects/1");
    mockPost.mockResolvedValueOnce({
      data: {
        id: 1,
        name: "研究项目 A",
        description: "",
        crf_template_version: "v1",
        status: "archived",
      },
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByRole("button", { name: "项目完结" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "项目完结" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认完结" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/studies/projects/1/complete/"));
  });
```

- [x] **Step 4: 将项目列表状态文案统一为“已完结”**

In `frontend/src/pages/projects/ProjectListPage.tsx`, update `statusLabel`:

```tsx
const statusLabel: Record<string, string> = {
  draft: "草稿",
  active: "进行中",
  archived: "已完结",
};
```

- [x] **Step 5: 运行前端相关测试确认失败**

Run:

```bash
cd frontend && npm test -- ProjectGroupingBoard.test.tsx App.test.tsx
```

Expected: FAIL，因为组件尚未暴露 handle，项目详情也还没有右上角统一动作和完结按钮。

- [x] **Step 6: 在 `ProjectGroupingBoard.tsx` 暴露 handle、状态并支持只读**

Modify imports:

```tsx
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
```

Add exported types near the existing `Props`:

```tsx
export type ProjectGroupingBoardHandle = {
  randomize: () => void;
  confirm: () => void;
  clearDraft: () => void;
};

export type ProjectGroupingBoardActionState = {
  hasActiveGroups: boolean;
  hasEligibleSelection: boolean;
  confirmLoading: boolean;
};

type Props = {
  projectId: number;
  groupRevision?: number;
  readOnly?: boolean;
  onActionStateChange?: (state: ProjectGroupingBoardActionState) => void;
};
```

Change the function signature:

```tsx
export const ProjectGroupingBoard = forwardRef<ProjectGroupingBoardHandle, Props>(function ProjectGroupingBoard(
  { projectId, groupRevision = 0, readOnly = false, onActionStateChange }: Props,
  ref,
) {
```

Convert `runLocalRandomize` and `confirmCurrentDraft` to `useCallback` and add read-only guard:

```tsx
  const runLocalRandomize = useCallback(() => {
    if (readOnly) return;
    const eligibleIds = poolSelected.filter((id) => !confirmedPatientIds.has(id));
    if (!eligibleIds.length) {
      message.warning("请先选择至少一名未确认入组患者。");
      return;
    }
    const validationError = getPercentValidationError(activePercents);
    if (validationError) {
      message.warning(validationError);
      return;
    }
    try {
      setLocalAssignments(
        assignPatientsToGroups(eligibleIds, groupsWithDraftPercents(activeGroups, percentByGroupId), Date.now()),
      );
      message.success("已生成本次随机分组");
    } catch (err) {
      message.error(err instanceof Error ? err.message : "随机分组失败");
    }
  }, [activeGroups, activePercents, confirmedPatientIds, percentByGroupId, poolSelected, readOnly]);

  const confirmCurrentDraft = useCallback(() => {
    if (readOnly) return;
    if (percentValidationError) {
      message.warning(percentValidationError);
      return;
    }
    confirmGroupingMutation.mutate();
  }, [confirmGroupingMutation, percentValidationError, readOnly]);
```

Add this after the callbacks:

```tsx
  useImperativeHandle(
    ref,
    () => ({
      randomize: runLocalRandomize,
      confirm: confirmCurrentDraft,
      clearDraft: () => {
        setLocalAssignments([]);
        setPoolSelected([]);
      },
    }),
    [confirmCurrentDraft, runLocalRandomize],
  );

  useEffect(() => {
    onActionStateChange?.({
      hasActiveGroups: activeGroups.length > 0,
      hasEligibleSelection,
      confirmLoading: confirmGroupingMutation.isPending,
    });
  }, [
    activeGroups.length,
    confirmGroupingMutation.isPending,
    hasEligibleSelection,
    onActionStateChange,
  ]);
```

Remove the internal top `Card size="small"` that renders `随机分组`、`确认分组` and the text `占比与本轮随机结果仅在确认后保存。`.

Apply read-only to existing controls:

```tsx
disabled={readOnly || confirmedPatientIds.has(p.id)}
```

```tsx
disabled={readOnly || !g.is_active}
```

Render group delete button only when not read-only:

```tsx
{!readOnly && (
  <Button
    type="text"
    danger
    size="small"
    aria-label={`删除${g.name}`}
    className="group-delete-bubble"
    onClick={() => openDeleteGroupModal(g)}
    loading={deleteGroupMutation.isPending}
    disabled={!g.is_active}
    style={{
      position: "absolute",
      right: 8,
      top: 8,
      width: 24,
      height: 24,
      minWidth: 24,
      borderRadius: 9999,
      zIndex: 2,
    }}
  >
    ×
  </Button>
)}
```

In `ConfirmedPatientCard`, add a `readOnly` prop and only render `解绑` when `!readOnly`:

```tsx
function ConfirmedPatientCard({
  row,
  patientById,
  onRequestUnbind,
  readOnly,
}: {
  row: ProjectPatientRow;
  patientById: Record<number, PatientOption>;
  onRequestUnbind: (row: ProjectPatientRow) => void;
  readOnly: boolean;
}) {
```

```tsx
{!readOnly && (
  <Button type="link" danger size="small" style={{ padding: 0 }} onClick={() => onRequestUnbind(row)}>
    解绑
  </Button>
)}
```

Pass `readOnly={readOnly}` where `ConfirmedPatientCard` is rendered.

In `LocalAssignmentCard`, set `draggable={!readOnly}` by adding `readOnly` prop; do not render local assignment cards during read-only unless a stale draft exists before state clears. The read-only guard on buttons and inputs is the required behavior.

At the end of the file, close the forwarded component:

```tsx
});
```

- [x] **Step 7: 在 `ProjectDetailPage.tsx` 统一右上角动作**

Replace imports:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Drawer, Space, Tag, message } from "antd";
import { useRef, useState } from "react";
```

Update local imports:

```tsx
import {
  ProjectGroupingBoard,
  type ProjectGroupingBoardActionState,
  type ProjectGroupingBoardHandle,
} from "./ProjectGroupingBoard";
import { DestructiveActionModal } from "../components/DestructiveActionModal";
```

Inside `ProjectDetailPage`, add state and mutation:

```tsx
  const qc = useQueryClient();
  const boardRef = useRef<ProjectGroupingBoardHandle>(null);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [boardState, setBoardState] = useState<ProjectGroupingBoardActionState>({
    hasActiveGroups: false,
    hasEligibleSelection: false,
    confirmLoading: false,
  });
```

After project query:

```tsx
  const completeMutation = useMutation({
    mutationFn: async () => {
      const r = await apiClient.post<StudyProject>(`/studies/projects/${id}/complete/`);
      return r.data;
    },
    onSuccess: async () => {
      message.success("项目已完结");
      setCompleteOpen(false);
      boardRef.current?.clearDraft();
      await qc.invalidateQueries({ queryKey: ["study-project", id] });
      await qc.invalidateQueries({ queryKey: ["study-projects"] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      message.error(err.response?.data?.detail ?? "项目完结失败");
    },
  });
```

Before return:

```tsx
  const isCompleted = project?.status === "archived";
```

Replace `extra` with:

```tsx
      extra={
        project ? (
          <Space wrap>
            {isCompleted ? <Tag color="default">已完结</Tag> : null}
            <Button
              type="primary"
              disabled={isCompleted || !boardState.hasEligibleSelection || !boardState.hasActiveGroups}
              onClick={() => boardRef.current?.randomize()}
            >
              随机分组
            </Button>
            <Button
              type="primary"
              style={{ backgroundColor: "#16a34a", borderColor: "#16a34a" }}
              disabled={isCompleted || !boardState.hasActiveGroups}
              loading={boardState.confirmLoading}
              onClick={() => boardRef.current?.confirm()}
            >
              确认分组
            </Button>
            <Button type="default" disabled={isCompleted} onClick={() => setConfigOpen(true)}>
              新增分组
            </Button>
            <Button danger disabled={isCompleted} onClick={() => setCompleteOpen(true)}>
              项目完结
            </Button>
          </Space>
        ) : null
      }
```

Render board with ref and read-only state:

```tsx
          <ProjectGroupingBoard
            ref={boardRef}
            projectId={id}
            groupRevision={groupRevision}
            readOnly={isCompleted}
            onActionStateChange={setBoardState}
          />
```

Render `ProjectGroupsTab` with readOnly:

```tsx
            <ProjectGroupsTab
              projectId={id}
              readOnly={isCompleted}
              onGroupCreated={() => setGroupRevision((value) => value + 1)}
            />
```

Add `DestructiveActionModal` after `Drawer`:

```tsx
          <DestructiveActionModal
            open={completeOpen}
            title={`确认完结项目「${project.name}」？`}
            okText="确认完结"
            impactSummary={[
              "完结后不能新增或确认入组患者。",
              "完结后不能新增、删除或修改分组配置，也不能保存分组占比。",
              "完结后不能保存访视表单或标记访视完成。",
              "CRF 预览和 DOCX 导出仍可继续使用。",
              "完结后不提供恢复入口。",
            ]}
            confirmLoading={completeMutation.isPending}
            onCancel={() => setCompleteOpen(false)}
            onConfirm={() => void completeMutation.mutateAsync()}
          />
```

- [x] **Step 8: 运行前端项目测试确认通过**

Run:

```bash
cd frontend && npm test -- ProjectGroupingBoard.test.tsx App.test.tsx
```

Expected: PASS。

- [ ] **Step 9: Commit checkpoint（仅用户要求提交时执行）**

```bash
git add frontend/src/pages/projects/ProjectDetailPage.tsx frontend/src/pages/projects/ProjectListPage.tsx frontend/src/pages/projects/ProjectGroupingBoard.tsx frontend/src/pages/projects/ProjectGroupingBoard.test.tsx frontend/src/app/App.test.tsx
git commit -m "feat(frontend): 项目详情动作区支持完结只读"
```

---

## Task 6: 分组配置、患者入组弹窗和访视表单前端只读

**Files:**
- Modify: `frontend/src/pages/projects/ProjectGroupsTab.tsx`
- Modify: `frontend/src/pages/patients/components/EnrollProjectsModal.tsx`
- Modify: `frontend/src/pages/patients/components/EnrollProjectsModal.test.tsx`
- Modify: `frontend/src/pages/visits/VisitFormPage.tsx`
- Modify: `frontend/src/pages/visits/VisitFormPage.test.tsx`
- Modify: `frontend/src/pages/crf/CrfPreviewPage.test.tsx`

- [x] **Step 1: 添加 EnrollProjectsModal 过滤测试**

Append to `frontend/src/pages/patients/components/EnrollProjectsModal.test.tsx`:

```tsx
  it("filters completed projects from direct enrollment choices", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === "/studies/projects/") {
        return Promise.resolve({
          data: [
            { id: 1, name: "项目甲", status: "active" },
            { id: 2, name: "已完结项目", status: "archived" },
          ],
        });
      }
      if (url.startsWith("/studies/project-patients/?patient=")) {
        return Promise.resolve({ data: [] });
      }
      if (url === "/studies/groups/") {
        return Promise.resolve({
          data: [
            { id: 10, project: 1, name: "干预组", is_active: true },
            { id: 20, project: 2, name: "历史组", is_active: true },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={qc}>
        <EnrollProjectsModal open onClose={vi.fn()} patientId={42} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("项目甲")).toBeInTheDocument();
    expect(screen.queryByText("已完结项目")).not.toBeInTheDocument();
  });
```

- [x] **Step 2: 更新 EnrollProjectsModal 类型和过滤**

In `frontend/src/pages/patients/components/EnrollProjectsModal.tsx`, change type:

```tsx
type StudyProject = { id: number; name: string; status: string };
```

Replace `availableProjects`:

```tsx
  const availableProjects = useMemo(
    () => projects.filter((p) => p.status !== "archived" && !enrolledIds.has(p.id)),
    [projects, enrolledIds],
  );
```

- [x] **Step 3: 更新 ProjectGroupsTab 支持只读**

In `frontend/src/pages/projects/ProjectGroupsTab.tsx`, update Props:

```tsx
type Props = {
  projectId: number;
  readOnly?: boolean;
  onGroupCreated?: () => void;
};
```

Update function signature:

```tsx
export function ProjectGroupsTab({ projectId, readOnly = false, onGroupCreated }: Props) {
```

Disable new group button:

```tsx
        <Button type="primary" disabled={readOnly} onClick={() => setOpen(true)}>
          新建分组
        </Button>
```

In the Modal form submit button:

```tsx
<Button type="primary" htmlType="submit" disabled={readOnly} loading={createMutation.isPending}>
  保存
</Button>
```

- [x] **Step 4: 添加 VisitFormPage 只读测试**

Append to `frontend/src/pages/visits/VisitFormPage.test.tsx`:

```tsx
  it("renders completed project visit as readonly", async () => {
    mockGet.mockResolvedValue({
      data: {
        id: 21,
        project_patient: 1,
        project_id: 1,
        project_name: "已完结研究",
        project_status: "archived",
        visit_type: "T0",
        status: "draft",
        visit_date: null,
        form_data: {
          assessments: {},
          computed_assessments: {},
          crf: {},
        },
      },
    });

    const r = renderAt(21);

    expect(await screen.findByText("项目已完结，访视表单只读。")).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "SPPB 总分" })).toBeDisabled();
    expect(r.container.querySelector('button[aria-label="保存"]')).toBeDisabled();
    expect(r.container.querySelector('button[aria-label="标记已完成"]')).toBeDisabled();
  });
```

- [x] **Step 5: 更新 VisitFormPage 类型和禁用逻辑**

In `frontend/src/pages/visits/VisitFormPage.tsx`, update `VisitDetail`:

```tsx
type VisitDetail = {
  id: number;
  project_patient: number;
  project_id?: number;
  project_name?: string;
  project_status?: string;
  visit_type: "T0" | "T1" | "T2";
  status: "draft" | "completed";
  visit_date: string | null;
  form_data: {
    assessments: Assessments;
    computed_assessments: Assessments;
    crf?: Record<string, unknown>;
  };
};
```

After `headerExtra`, add:

```tsx
  const isProjectCompleted = visit?.project_status === "archived";
  const isVisitReadonly = visit?.status === "completed" || isProjectCompleted;
```

Render an alert after the computed hint alert:

```tsx
          {isProjectCompleted && (
            <Alert
              type="warning"
              showIcon
              message="项目已完结，访视表单只读。"
            />
          )}
```

For every base `InputNumber`, add:

```tsx
disabled={isVisitReadonly}
```

For `Radio.Group`, add:

```tsx
disabled={isVisitReadonly}
```

Replace extension form disabled prop:

```tsx
disabled={isVisitReadonly}
```

Replace `renderVisitRegistryField` disabled option:

```tsx
disabled: isVisitReadonly,
```

Disable save and complete buttons:

```tsx
disabled={isVisitReadonly}
```

for `保存`, and:

```tsx
disabled={isVisitReadonly}
```

for `标记已完成`.

- [x] **Step 6: 添加 CRF 前端导出仍可用测试**

In `frontend/src/pages/crf/CrfPreviewPage.test.tsx`, update imports:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
```

Update the hoisted mocks:

```tsx
const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));
```

Update the mocked api client:

```tsx
vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}));
```

In `beforeEach`, add:

```tsx
    mockPost.mockReset();
    mockPost.mockResolvedValue({ data: { docx_file: null } });
```

Append this test:

```tsx
  it("keeps DOCX export available for completed project preview", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/?projectPatientId=1"]}>
          <CrfPreviewPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByText("受试者编号");
    const exportButton = screen.getByRole("button", { name: "导出 DOCX" });
    expect(exportButton).toBeEnabled();
    fireEvent.click(exportButton);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/crf/project-patients/1/export/", {});
    });
  });
```

- [x] **Step 7: 运行前端相关测试确认通过**

Run:

```bash
cd frontend && npm test -- EnrollProjectsModal.test.tsx VisitFormPage.test.tsx CrfPreviewPage.test.tsx
```

Expected: PASS。

- [ ] **Step 8: Commit checkpoint（仅用户要求提交时执行）**

```bash
git add frontend/src/pages/projects/ProjectGroupsTab.tsx frontend/src/pages/patients/components/EnrollProjectsModal.tsx frontend/src/pages/patients/components/EnrollProjectsModal.test.tsx frontend/src/pages/visits/VisitFormPage.tsx frontend/src/pages/visits/VisitFormPage.test.tsx frontend/src/pages/crf/CrfPreviewPage.test.tsx
git commit -m "fix(frontend): 完结项目隐藏入组并禁用访视录入"
```

---

## Task 7: 全量验证与文档状态更新

**Files:**
- Modify: `docs/superpowers/specs/2026-05-13-project-detail-completion-and-actions-design.md`
- Modify: `docs/superpowers/plans/2026-05-13-project-detail-completion-and-actions.md`

- [x] **Step 1: 运行后端全量测试**

Run:

```bash
cd backend && pytest
```

Expected: PASS，当前仓库基线约 100+ tests passed。

- [x] **Step 2: 运行前端全量测试**

Run:

```bash
cd frontend && npm run test
```

Expected: PASS。

- [x] **Step 3: 运行前端 lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: 0 error。若仍存在既有 warning，记录 warning 数量，不为本任务扩大范围。

- [x] **Step 4: 运行前端构建**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS。

- [x] **Step 5: 搜索不应残留的用户文案**

Run:

```bash
rg -n "占比与本轮随机结果仅在确认后保存|已归档" frontend/src
```

Expected: 不出现 `占比与本轮随机结果仅在确认后保存`；`已归档` 若只存在历史文档或非前端源码可接受，前端源码中项目状态文案应显示 `已完结`。

- [x] **Step 6: 更新 spec 状态**

In `docs/superpowers/specs/2026-05-13-project-detail-completion-and-actions-design.md`, change:

```markdown
> 状态：review
```

to:

```markdown
> 状态：implemented
```

Add execution record under the frontmatter:

```markdown
> 实施记录（2026-05-13, Codex）：已按计划落地项目详情动作区与项目完结状态门控；验证通过：`cd backend && pytest`、`cd frontend && npm run test`、`cd frontend && npm run lint`、`cd frontend && npm run build`。
```

- [x] **Step 7: 更新本 plan 执行记录**

At the top of this file, under the title and before the agentic workers note, add:

```markdown
执行记录（2026-05-13, Codex）：Task 1-7 已完成；验证通过：`cd backend && pytest`、`cd frontend && npm run test`、`cd frontend && npm run lint`、`cd frontend && npm run build`。
```

- [x] **Step 8: 检查 git 状态**

Run:

```bash
git status --short
```

Expected: 只包含本计划范围内文件修改。

- [ ] **Step 9: Final commit（仅用户要求提交时执行）**

```bash
git add backend/apps/studies/project_status.py backend/apps/studies/views.py backend/apps/studies/tests/test_project_completion.py backend/apps/patients/views.py backend/apps/patients/tests/test_enroll_projects.py backend/apps/visits/serializers.py backend/apps/visits/views.py backend/apps/visits/tests/test_status_transition.py backend/apps/crf/tests/test_project_completion_crf_api.py frontend/src/pages/projects/ProjectDetailPage.tsx frontend/src/pages/projects/ProjectListPage.tsx frontend/src/pages/projects/ProjectGroupingBoard.tsx frontend/src/pages/projects/ProjectGroupingBoard.test.tsx frontend/src/pages/projects/ProjectGroupsTab.tsx frontend/src/pages/patients/components/EnrollProjectsModal.tsx frontend/src/pages/patients/components/EnrollProjectsModal.test.tsx frontend/src/pages/visits/VisitFormPage.tsx frontend/src/pages/visits/VisitFormPage.test.tsx frontend/src/pages/crf/CrfPreviewPage.test.tsx frontend/src/app/App.test.tsx docs/superpowers/specs/2026-05-13-project-detail-completion-and-actions-design.md docs/superpowers/plans/2026-05-13-project-detail-completion-and-actions.md
git commit -m "feat(projects): 支持项目完结只读状态"
```
