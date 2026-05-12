# 前端临时随机与确认入组绑定 Implementation Plan

> **状态：approved → implementing**（计划已批准，正在执行；本计划会**删除后端 randomize / reset-pending / pending 状态字段**，请勿回滚）
> **日期：** 2026-05-12
> **关联 spec：** `docs/superpowers/specs/2026-05-12-frontend-only-randomization-confirmed-binding-design.md`
> **跨工具协作：** 修改本文件前请阅读仓库根 `AGENTS.md` §2。勾选 `- [x]` 时同时在文件顶部"执行记录"区注明 commit short-sha 和工具名（cursor / codex）。
> **不可回退：** 本计划完成后，"批次"概念、"pending 状态字段"在产品中永久消失。若工作区看到 `grouping_status`、`pending`、`randomize` 等代码残留，那是 bug，请清理。
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目分组改为“前端临时随机、确认时才创建已确认入组绑定”，彻底移除 pending、草案、批次式关系。

**Architecture:** 后端只持久化已确认的 `ProjectPatient`，确认接口接收前端提交的 `assignments` 并原子批量创建绑定。前端在项目看板内维护页面级临时随机结果，刷新即丢弃；组列合并展示后端已确认患者和本次随机患者。

**Tech Stack:** Django REST Framework、pytest-django、React 18、TypeScript、Ant Design、TanStack Query、Vitest。

---

## 文件结构

后端：

- Modify: `backend/apps/studies/models.py`，删除 `ProjectPatient.GroupingStatus` 与 `grouping_status` 字段。
- Create: `backend/apps/studies/migrations/0003_remove_projectpatient_grouping_status.py`，删除数据库字段。
- Modify: `backend/apps/studies/serializers.py`，从 `ProjectPatientSerializer` 删除 `grouping_status`；新增确认入组 payload serializer。
- Modify: `backend/apps/studies/views.py`，删除 `randomize`、`reset_pending` action；改造 `confirm_grouping` 为按 `assignments` 批量创建已确认绑定；项目患者列表只返回真实绑定。
- Modify: `backend/apps/patients/views.py`，`enroll_projects` 创建 `ProjectPatient` 时不再写 `grouping_status`。
- Modify: `backend/apps/studies/services/unbind_project_patient.py`，删除 confirmed 状态检查，因为所有 `ProjectPatient` 都是正式绑定。
- Modify: `backend/apps/common/management/commands/seed_demo.py`，创建演示 `ProjectPatient` 时不再写状态字段。
- Modify: `backend/apps/patients/tests/test_enroll_projects.py`，删除 confirmed 状态断言，保留直接入组断言。
- Replace: `backend/apps/studies/tests/test_confirm_grouping.py`，覆盖新确认接口。
- Delete: `backend/apps/studies/tests/test_randomize_grouping.py` 和 `backend/apps/studies/tests/test_reset_pending_grouping.py`，这些接口不再是产品能力。

前端：

- Modify: `frontend/src/pages/projects/groupingBoardUtils.ts`，新增前端随机纯函数，保留比例换算工具。
- Modify: `frontend/src/pages/projects/groupingBoardUtils.test.ts`，覆盖随机函数。
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`，移除后端随机、撤销 pending、拖拽 pending 逻辑；维护本地随机结果。
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`，覆盖全量患者禁选、前端随机、确认提交、已确认置灰展示。
- Modify: `frontend/src/pages/patients/PatientDetailPage.tsx`，删除项目表中的 `grouping_status` 展示。
- Modify: `frontend/src/app/App.test.tsx`，删除项目看板 mock 中的 `grouping_status`。
- Modify: `docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md`，加一段过时说明指向 2026-05-12 新 spec。

---

### Task 1: 后端确认接口测试

**Files:**
- Replace: `backend/apps/studies/tests/test_confirm_grouping.py`

- [ ] **Step 1: 写失败测试**

将 `backend/apps/studies/tests/test_confirm_grouping.py` 替换为：

```python
import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _patient(doctor, name="患者乙", phone="13900000222"):
    return Patient.objects.create(name=name, phone=phone, primary_doctor=doctor)


@pytest.mark.django_db
def test_confirm_grouping_creates_project_patients_from_assignments(doctor, project):
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=1)
    p1 = _patient(doctor, "甲", "13900000001")
    p2 = _patient(doctor, "乙", "13900000002")

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {"assignments": [{"patient_id": p1.id, "group_id": g1.id}, {"patient_id": p2.id, "group_id": g2.id}]},
        format="json",
    )

    assert r.status_code == 200, r.data
    assert r.data["confirmed"] == 2
    assert ProjectPatient.objects.filter(project=project).count() == 2
    assert ProjectPatient.objects.get(project=project, patient=p1).group_id == g1.id
    assert ProjectPatient.objects.get(project=project, patient=p2).group_id == g2.id


@pytest.mark.django_db
def test_confirm_grouping_rejects_patient_already_in_project(doctor, project, patient):
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    ProjectPatient.objects.create(project=project, patient=patient, group=group)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {"assignments": [{"patient_id": patient.id, "group_id": group.id}]},
        format="json",
    )

    assert r.status_code == 400
    assert "已确认入组" in str(r.data)
    assert ProjectPatient.objects.filter(project=project, patient=patient).count() == 1


@pytest.mark.django_db
def test_confirm_grouping_rejects_group_from_other_project(doctor, project, patient):
    other = StudyProject.objects.create(name="其他项目", created_by=doctor)
    other_group = StudyGroup.objects.create(project=other, name="其他组", target_ratio=1)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {"assignments": [{"patient_id": patient.id, "group_id": other_group.id}]},
        format="json",
    )

    assert r.status_code == 400
    assert "分组不属于当前项目" in str(r.data)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()


@pytest.mark.django_db
def test_confirm_grouping_rejects_inactive_group(doctor, project, patient):
    group = StudyGroup.objects.create(project=project, name="停用组", target_ratio=1, is_active=False)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {"assignments": [{"patient_id": patient.id, "group_id": group.id}]},
        format="json",
    )

    assert r.status_code == 400
    assert "分组已停用" in str(r.data)


@pytest.mark.django_db
def test_confirm_grouping_rejects_duplicate_patient_in_payload(doctor, project, patient):
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=1)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {"assignments": [{"patient_id": patient.id, "group_id": g1.id}, {"patient_id": patient.id, "group_id": g2.id}]},
        format="json",
    )

    assert r.status_code == 400
    assert "重复患者" in str(r.data)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend
pytest apps/studies/tests/test_confirm_grouping.py -q
```

Expected: FAIL，至少出现旧接口提示“项目内没有可确认的患者”或 serializer 字段不存在。

- [ ] **Step 3: 提交测试**

```bash
git add backend/apps/studies/tests/test_confirm_grouping.py
git commit -m "test: 覆盖确认入组批量创建接口"
```

---

### Task 2: 后端模型与确认接口实现

**Files:**
- Modify: `backend/apps/studies/models.py`
- Create: `backend/apps/studies/migrations/0003_remove_projectpatient_grouping_status.py`
- Modify: `backend/apps/studies/serializers.py`
- Modify: `backend/apps/studies/views.py`

- [ ] **Step 1: 删除模型状态字段**

在 `backend/apps/studies/models.py` 中把 `ProjectPatient` 改成：

```python
class ProjectPatient(UserStampedModel):
    project = models.ForeignKey(
        StudyProject, on_delete=models.CASCADE, related_name="project_patients"
    )
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="project_links"
    )
    group = models.ForeignKey(StudyGroup, null=True, blank=True, on_delete=models.PROTECT)
    enrolled_at = models.DateTimeField("入组时间", auto_now_add=True)

    class Meta:
        unique_together = [("project", "patient")]
```

- [ ] **Step 2: 创建迁移**

Run:

```bash
cd backend
python manage.py makemigrations studies
```

Expected: 生成 `backend/apps/studies/migrations/0003_remove_projectpatient_grouping_status.py`，操作为 `RemoveField(model_name="projectpatient", name="grouping_status")`。

- [ ] **Step 3: 更新 serializers**

在 `backend/apps/studies/serializers.py` 添加：

```python
class ConfirmGroupingAssignmentSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(min_value=1)
    group_id = serializers.IntegerField(min_value=1)


class ConfirmGroupingSerializer(serializers.Serializer):
    assignments = ConfirmGroupingAssignmentSerializer(many=True, allow_empty=False)
```

同时从 `ProjectPatientSerializer.Meta.fields` 删除 `"grouping_status"`。

- [ ] **Step 4: 改造 views**

在 `backend/apps/studies/views.py`：

1. 删除 `from apps.studies.services.grouping import assign_groups`。
2. 删除 `reset_pending` action。
3. 删除 `randomize` action。
4. 引入 serializer：

```python
from .serializers import (
    ConfirmGroupingSerializer,
    ProjectPatientSerializer,
    StudyGroupSerializer,
    StudyProjectSerializer,
)
```

5. 将 `confirm_grouping` 替换为：

```python
    @action(detail=True, methods=["post"], url_path="confirm-grouping")
    @transaction.atomic
    def confirm_grouping(self, request, pk=None):
        project = self.get_object()
        serializer = ConfirmGroupingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignments = serializer.validated_data["assignments"]

        patient_ids = [item["patient_id"] for item in assignments]
        if len(patient_ids) != len(set(patient_ids)):
            raise ValidationError({"detail": "同一次确认中存在重复患者。"})

        from apps.patients.models import Patient

        existing_patients = set(Patient.objects.filter(pk__in=patient_ids).values_list("pk", flat=True))
        missing_patients = sorted(set(patient_ids) - existing_patients)
        if missing_patients:
            raise ValidationError({"detail": f"以下患者不存在: {missing_patients}"})

        group_ids = [item["group_id"] for item in assignments]
        groups = {
            group.id: group
            for group in StudyGroup.objects.filter(pk__in=group_ids).select_for_update(of=("self",))
        }
        missing_groups = sorted(set(group_ids) - set(groups))
        if missing_groups:
            raise ValidationError({"detail": f"以下分组不存在: {missing_groups}"})

        for item in assignments:
            group = groups[item["group_id"]]
            if group.project_id != project.id:
                raise ValidationError({"detail": "分组不属于当前项目。"})
            if not group.is_active:
                raise ValidationError({"detail": "分组已停用，不能确认入组。"})

        linked_ids = set(
            ProjectPatient.objects.select_for_update(of=("self",))
            .filter(project=project, patient_id__in=patient_ids)
            .values_list("patient_id", flat=True)
        )
        if linked_ids:
            raise ValidationError({"detail": f"以下患者已确认入组: {sorted(linked_ids)}"})

        created = []
        for item in assignments:
            pp = ProjectPatient.objects.create(
                project=project,
                patient_id=item["patient_id"],
                group_id=item["group_id"],
                created_by=request.user,
            )
            ensure_default_visits(pp)
            created.append(
                {
                    "project_patient_id": pp.id,
                    "patient_id": pp.patient_id,
                    "group_id": pp.group_id,
                }
            )

        return Response({"confirmed": len(created), "created": created})
```

- [ ] **Step 5: 阻止已确认关系被 PATCH 改组**

把 `ProjectPatientViewSet.perform_update` 改为：

```python
    def perform_update(self, serializer):
        serializer.validated_data.pop("group", None)
        return super().perform_update(serializer)
```

- [ ] **Step 6: 运行后端确认接口测试**

Run:

```bash
cd backend
pytest apps/studies/tests/test_confirm_grouping.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交实现**

```bash
git add backend/apps/studies/models.py backend/apps/studies/migrations/0003_remove_projectpatient_grouping_status.py backend/apps/studies/serializers.py backend/apps/studies/views.py
git commit -m "feat: 确认入组时创建正式项目患者关系"
```

---

### Task 3: 清理后端 pending 随机测试与患者入组测试

**Files:**
- Delete: `backend/apps/studies/tests/test_randomize_grouping.py`
- Delete: `backend/apps/studies/tests/test_reset_pending_grouping.py`
- Modify: `backend/apps/patients/views.py`
- Modify: `backend/apps/patients/tests/test_enroll_projects.py`
- Modify: `backend/apps/studies/services/unbind_project_patient.py`
- Modify: `backend/apps/studies/tests/test_unbind_project_patient.py`
- Modify: `backend/apps/common/management/commands/seed_demo.py`

- [ ] **Step 1: 删除后端随机与撤销 pending 测试文件**

Run:

```bash
git rm backend/apps/studies/tests/test_randomize_grouping.py backend/apps/studies/tests/test_reset_pending_grouping.py
```

Expected: 两个测试文件被删除。

- [ ] **Step 2: 更新患者直接入组实现**

在 `backend/apps/patients/views.py` 中删除创建 `ProjectPatient` 时的 `grouping_status=ProjectPatient.GroupingStatus.CONFIRMED`，保留：

```python
            pp = ProjectPatient.objects.create(
                project_id=item["project_id"],
                patient=patient,
                group_id=item["group_id"],
                created_by=request.user,
            )
```

- [ ] **Step 3: 更新患者入组测试**

在 `backend/apps/patients/tests/test_enroll_projects.py` 中删除所有 `ProjectPatient.GroupingStatus` 断言。核心断言保留为：

```python
    assert pp1.group_id == g1.id
    assert pp2.group_id == g2.id
```

- [ ] **Step 4: 查找后端剩余待清理引用**

Run:

```bash
rg -n "GroupingStatus|grouping_status|reset-pending|randomize" backend/apps backend/tests
```

Expected: 输出只来自本任务后续步骤会修改或删除的文件，例如 `backend/apps/studies/services/unbind_project_patient.py`、`backend/apps/studies/tests/test_unbind_project_patient.py`、`backend/apps/common/management/commands/seed_demo.py`、`backend/apps/patients/views.py`、`backend/apps/patients/tests/test_enroll_projects.py`。

- [ ] **Step 5: 更新解绑服务**

在 `backend/apps/studies/services/unbind_project_patient.py` 删除状态检查：

```python
    if pp.grouping_status != ProjectPatient.GroupingStatus.CONFIRMED:
        raise ValidationError({"detail": "仅已确认入组患者可从项目移除。"})
```

保留按 `ProjectPatient` 终止处方、清理 CRF 导出和删除关系的逻辑。

- [ ] **Step 6: 更新解绑测试**

在 `backend/apps/studies/tests/test_unbind_project_patient.py` 中删除：

```python
    project_patient.grouping_status = ProjectPatient.GroupingStatus.CONFIRMED
    project_patient.save(update_fields=["grouping_status"])
```

删除旧的 pending 禁止解绑测试完整函数：

```python
@pytest.mark.django_db
def test_unbind_rejects_when_not_confirmed(doctor, project_patient, active_prescription):
    assert project_patient.grouping_status == ProjectPatient.GroupingStatus.PENDING
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/project-patients/{project_patient.id}/unbind/")
    assert r.status_code == 400
    assert ProjectPatient.objects.filter(pk=project_patient.pk).exists()
```

- [ ] **Step 7: 更新演示种子**

在 `backend/apps/common/management/commands/seed_demo.py` 中把 defaults 改为：

```python
            defaults={"group": group},
```

- [ ] **Step 8: 再次扫描后端引用**

Run:

```bash
rg -n "GroupingStatus|grouping_status|reset-pending|randomize" backend/apps backend/tests
```

Expected: 无输出。

- [ ] **Step 9: 运行后端相关测试**

Run:

```bash
cd backend
pytest apps/studies/tests apps/patients/tests -q
```

Expected: PASS。

- [ ] **Step 10: 提交清理**

```bash
git add backend/apps/patients/views.py backend/apps/patients/tests/test_enroll_projects.py backend/apps/studies/tests backend/apps/studies/services/unbind_project_patient.py backend/apps/common/management/commands/seed_demo.py
git commit -m "refactor: 移除后端未确认随机与分组状态"
```

---

### Task 4: 前端随机工具函数

**Files:**
- Modify: `frontend/src/pages/projects/groupingBoardUtils.ts`
- Modify: `frontend/src/pages/projects/groupingBoardUtils.test.ts`

- [ ] **Step 1: 写失败测试**

在 `frontend/src/pages/projects/groupingBoardUtils.test.ts` 增加：

```typescript
import { assignPatientsToGroups } from "./groupingBoardUtils";

it("assigns selected patients to groups by target ratios", () => {
  const result = assignPatientsToGroups(
    [1, 2, 3, 4],
    [
      { id: 10, target_ratio: 1 },
      { id: 11, target_ratio: 1 },
    ],
    123,
  );

  expect(result).toHaveLength(4);
  expect(result.filter((x) => x.groupId === 10)).toHaveLength(2);
  expect(result.filter((x) => x.groupId === 11)).toHaveLength(2);
  expect(new Set(result.map((x) => x.patientId))).toEqual(new Set([1, 2, 3, 4]));
});

it("rejects randomization when groups are empty or invalid", () => {
  expect(() => assignPatientsToGroups([1], [], 1)).toThrow("没有启用分组");
  expect(() => assignPatientsToGroups([1], [{ id: 10, target_ratio: 0 }], 1)).toThrow("分组比例必须大于 0");
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd frontend
npm test -- groupingBoardUtils.test.ts
```

Expected: FAIL，提示 `assignPatientsToGroups` 未导出。

- [ ] **Step 3: 实现前端随机纯函数**

在 `frontend/src/pages/projects/groupingBoardUtils.ts` 末尾添加：

```typescript
export type RandomGroupInput = { id: number; target_ratio: number };
export type LocalAssignment = { patientId: number; groupId: number };

function seededRandom(seed: number) {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function assignPatientsToGroups(
  patientIds: number[],
  groups: RandomGroupInput[],
  seed = Date.now(),
): LocalAssignment[] {
  if (!groups.length) throw new Error("没有启用分组，不能随机分组");
  if (groups.some((g) => g.target_ratio <= 0)) throw new Error("分组比例必须大于 0");

  const random = seededRandom(seed);
  const shuffled = [...patientIds].sort(() => random() - 0.5);
  const totalRatio = groups.reduce((sum, g) => sum + g.target_ratio, 0);
  let remaining = shuffled.length;
  let cursor = 0;
  const result: LocalAssignment[] = [];

  groups.forEach((group, index) => {
    const count =
      index === groups.length - 1
        ? remaining
        : Math.min(remaining, Math.round((shuffled.length * group.target_ratio) / totalRatio));
    for (const patientId of shuffled.slice(cursor, cursor + count)) {
      result.push({ patientId, groupId: group.id });
    }
    cursor += count;
    remaining -= count;
  });

  return result;
}
```

- [ ] **Step 4: 运行工具测试**

Run:

```bash
cd frontend
npm test -- groupingBoardUtils.test.ts
```

Expected: PASS。

- [ ] **Step 5: 提交工具函数**

```bash
git add frontend/src/pages/projects/groupingBoardUtils.ts frontend/src/pages/projects/groupingBoardUtils.test.ts
git commit -m "feat: 增加前端临时随机分组工具"
```

---

### Task 5: 项目分组看板前端测试

**Files:**
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`

- [ ] **Step 1: 替换 mock 数据语义**

把 `ProjectGroupingBoard.test.tsx` 中的 `/patients/` mock 改为 3 类患者：

```typescript
data: [
  { id: 1, name: "未入组甲", gender: "male", phone: "13900000001" },
  { id: 2, name: "未入组乙", gender: "female", phone: "13900000002" },
  { id: 201, name: "已确认丙", gender: "male", phone: "13900000201" },
],
```

把 `/studies/project-patients/` mock 改为只返回已确认患者，且不含 `grouping_status`：

```typescript
data: [
  {
    id: 9001,
    project: 1,
    patient: 201,
    patient_name: "已确认丙",
    patient_phone: "13900000201",
    group: 10,
  },
],
```

- [ ] **Step 2: 写全量患者与置灰禁选测试**

添加测试：

```typescript
it("全量患者中已确认患者置灰禁选，组列仍展示已确认患者", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ProjectGroupingBoard projectId={1} />
      </QueryClientProvider>
    </MemoryRouter>,
  );

  await waitFor(() => expect(screen.getByText(/全量患者|患者选择/)).toBeInTheDocument());
  expect(screen.getByText(/未入组甲/)).toBeInTheDocument();
  expect(screen.getByText(/未入组乙/)).toBeInTheDocument();
  expect(screen.getByText(/已确认丙/)).toBeInTheDocument();
  expect(screen.getAllByText("已确认").length).toBeGreaterThan(0);
});
```

- [ ] **Step 3: 写前端随机不调用后端 randomize 测试**

添加测试：

```typescript
it("随机只生成本地临时结果，不调用后端 randomize", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ProjectGroupingBoard projectId={1} />
      </QueryClientProvider>
    </MemoryRouter>,
  );

  await waitFor(() => expect(screen.getByText("未入组甲")).toBeInTheDocument());
  fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
  fireEvent.click(screen.getByRole("button", { name: "随机分组" }));

  await waitFor(() => expect(screen.getByText("本次随机")).toBeInTheDocument());
  expect(mockPost).not.toHaveBeenCalledWith("/studies/projects/1/randomize/", expect.anything());
});
```

确保文件顶部 import 包含：

```typescript
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
```

- [ ] **Step 4: 写确认提交 assignments 测试**

添加测试：

```typescript
it("确认分组提交本地 assignments 并刷新", async () => {
  mockPost.mockResolvedValueOnce({
    data: { confirmed: 1, created: [{ project_patient_id: 9010, patient_id: 1, group_id: 10 }] },
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ProjectGroupingBoard projectId={1} />
      </QueryClientProvider>
    </MemoryRouter>,
  );

  await waitFor(() => expect(screen.getByText("未入组甲")).toBeInTheDocument());
  fireEvent.click(screen.getByLabelText(/选择患者 未入组甲/));
  fireEvent.click(screen.getByRole("button", { name: "随机分组" }));
  await waitFor(() => expect(screen.getByText("本次随机")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "确认分组" }));

  await waitFor(() => expect(mockPost).toHaveBeenCalled());
  const [url, payload] = mockPost.mock.calls.at(-1) ?? [];
  expect(url).toBe("/studies/projects/1/confirm-grouping/");
  expect(payload.assignments).toHaveLength(1);
  expect(payload.assignments[0].patient_id).toBe(1);
  expect([10, 11]).toContain(payload.assignments[0].group_id);
});
```

- [ ] **Step 5: 运行测试确认失败**

Run:

```bash
cd frontend
npm test -- ProjectGroupingBoard.test.tsx
```

Expected: FAIL，当前组件仍隐藏已确认患者于池外、调用后端 randomize、依赖 `grouping_status`。

- [ ] **Step 6: 提交前端失败测试**

```bash
git add frontend/src/pages/projects/ProjectGroupingBoard.test.tsx
git commit -m "test: 覆盖前端临时随机分组看板"
```

---

### Task 6: 项目分组看板实现

**Files:**
- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`

- [ ] **Step 1: 更新类型与 imports**

从 `ProjectGroupingBoard.tsx` 删除 `@dnd-kit/*` imports 和 `HolderOutlined`。引入随机工具：

```typescript
import { assignPatientsToGroups, ratiosToTargetRatios, targetRatiosToDisplayPercents } from "./groupingBoardUtils";
```

将 `ProjectPatientRow` 改为：

```typescript
type ProjectPatientRow = {
  id: number;
  patient: number;
  patient_name: string;
  patient_phone: string;
  group: number | null;
};
```

新增：

```typescript
type LocalAssignmentRow = {
  patientId: number;
  groupId: number;
};
```

- [ ] **Step 2: 删除拖拽组件并新增卡片组件**

删除 `DroppableGroupBody` 与 `DraggablePpCard`。新增两个小组件：

```tsx
function ConfirmedPatientCard({
  row,
  patientById,
  onRequestUnbind,
}: {
  row: ProjectPatientRow;
  patientById: Record<number, PatientOption>;
  onRequestUnbind: (row: ProjectPatientRow) => void;
}) {
  const p = patientById[row.patient];
  return (
    <Card size="small" style={{ opacity: 0.6, marginBottom: 8 }}>
      <Space direction="vertical" size={4} style={{ width: "100%" }}>
        <Space align="start" style={{ width: "100%", justifyContent: "space-between" }}>
          <Typography.Text strong>{row.patient_name}</Typography.Text>
          <Tag>已确认</Tag>
        </Space>
        <Typography.Text type="secondary">
          {(p && genderLabel[p.gender]) ?? "—"} · 尾号 {phoneTail(row.patient_phone)}
        </Typography.Text>
        <Link to={`/patients/${row.patient}`}>患者详情</Link>
        <Button type="link" danger size="small" style={{ padding: 0 }} onClick={() => onRequestUnbind(row)}>
          从本项目移除
        </Button>
      </Space>
    </Card>
  );
}

function LocalAssignmentCard({
  patient,
  onRemove,
}: {
  patient: PatientOption;
  onRemove: () => void;
}) {
  return (
    <Card size="small" style={{ marginBottom: 8 }}>
      <Space direction="vertical" size={4} style={{ width: "100%" }}>
        <Space align="start" style={{ width: "100%", justifyContent: "space-between" }}>
          <Typography.Text strong>{patient.name}</Typography.Text>
          <Tag color="blue">本次随机</Tag>
        </Space>
        <Typography.Text type="secondary">
          {genderLabel[patient.gender] ?? "—"} · 尾号 {phoneTail(patient.phone)}
        </Typography.Text>
        <Link to={`/patients/${patient.id}`}>患者详情</Link>
        <Button type="link" size="small" style={{ padding: 0 }} onClick={onRemove}>
          从本次结果移除
        </Button>
      </Space>
    </Card>
  );
}
```

- [ ] **Step 3: 更新状态与派生数据**

删除 `sensors`、`draftGroupByPp`、`columnSource`、`hasPending`。新增：

```typescript
  const [localAssignments, setLocalAssignments] = useState<LocalAssignmentRow[]>([]);
```

用已确认患者集合替换 enrolled 语义：

```typescript
  const confirmedPatientIds = useMemo(
    () => new Set((projectPatients ?? []).map((pp) => pp.patient)),
    [projectPatients],
  );

  const confirmedGroupByPatient = useMemo(() => {
    const map: Record<number, number | null> = {};
    for (const pp of projectPatients ?? []) map[pp.patient] = pp.group;
    return map;
  }, [projectPatients]);
```

- [ ] **Step 4: 替换随机与确认 mutation**

删除 `randomizeMutation` 对后端 `/randomize/` 的调用，改为本地函数：

```typescript
  const runLocalRandomize = () => {
    const eligibleIds = poolSelected.filter((id) => !confirmedPatientIds.has(id));
    if (!eligibleIds.length) {
      message.warning("请先选择至少一名未确认入组患者。");
      return;
    }
    try {
      setLocalAssignments(assignPatientsToGroups(eligibleIds, activeGroups, Date.now()));
      message.success("已生成本次随机分组");
    } catch (err) {
      message.error(err instanceof Error ? err.message : "随机分组失败");
    }
  };
```

把 `confirmGroupingMutation` 改为提交 assignments：

```typescript
  const confirmGroupingMutation = useMutation({
    mutationFn: async () => {
      await apiClient.post(`/studies/projects/${projectId}/confirm-grouping/`, {
        assignments: localAssignments.map((a) => ({
          patient_id: a.patientId,
          group_id: a.groupId,
        })),
      });
    },
    onSuccess: async () => {
      message.success("分组已确认");
      setLocalAssignments([]);
      setPoolSelected([]);
      await qc.invalidateQueries({ queryKey: ["project-patients", projectId] });
      await qc.invalidateQueries({ queryKey: ["patients"] });
      await qc.invalidateQueries({ queryKey: ["study-projects"] });
    },
    onError: async (err: { response?: { data?: { detail?: string } } }) => {
      message.error(err.response?.data?.detail ?? "确认失败");
      await qc.invalidateQueries({ queryKey: ["project-patients", projectId] });
      await qc.invalidateQueries({ queryKey: ["study-groups", projectId] });
    },
  });
```

- [ ] **Step 5: 替换患者选择区域**

把标题改为 `全量患者`，`Checkbox.Group` 改为逐项渲染，以便禁用已确认患者：

```tsx
      <Card title="全量患者" size="small">
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          勾选未确认入组患者后点击「随机分组」；勾选只代表本次随机输入，不会创建绑定关系。
        </Typography.Paragraph>
        <Space wrap>
          {(patients ?? []).map((p) => {
            const confirmed = confirmedPatientIds.has(p.id);
            return (
              <Checkbox
                key={p.id}
                value={p.id}
                checked={poolSelected.includes(p.id)}
                disabled={confirmed}
                aria-label={`选择患者 ${p.name}`}
                onChange={(e) =>
                  setPoolSelected((prev) =>
                    e.target.checked ? [...prev, p.id] : prev.filter((id) => id !== p.id),
                  )
                }
              >
                <Tag color={confirmed ? "default" : undefined}>
                  {p.name} · {genderLabel[p.gender] ?? p.gender} · 尾号 {phoneTail(p.phone)}
                  {confirmed ? " · 已确认" : ""}
                </Tag>
              </Checkbox>
            );
          })}
        </Space>
        <Button
          type="primary"
          style={{ marginTop: 12 }}
          disabled={!poolSelected.some((id) => !confirmedPatientIds.has(id)) || !activeGroups.length}
          onClick={runLocalRandomize}
        >
          随机分组
        </Button>
      </Card>
```

- [ ] **Step 6: 替换工具条按钮**

删除“撤销未确认”。确认按钮改为：

```tsx
          <Button
            type="primary"
            disabled={!localAssignments.length}
            loading={confirmGroupingMutation.isPending}
            onClick={() => confirmGroupingMutation.mutate()}
          >
            确认分组
          </Button>
```

提示文案改为：

```tsx
<Typography.Text type="secondary">
  当前随机结果仅保存在本页面；刷新或切换项目会丢弃，点击「确认分组」后才正式入组。
</Typography.Text>
```

- [ ] **Step 7: 替换组列渲染**

删除 `DndContext` 包裹，改为普通列。列头继续使用当前已有的 `title` 内容；只替换卡片列表 body：

```tsx
        <div style={{ display: "flex", gap: 12, overflowX: "auto", alignItems: "flex-start" }}>
          {activeGroups.map((g) => (
            <Card
              key={g.id}
              size="small"
              style={{ minWidth: 240, flex: "0 0 auto" }}
              title={
                <Space direction="vertical" size={4} style={{ width: "100%" }}>
                  <Space style={{ width: "100%", justifyContent: "space-between" }}>
                    <Typography.Text strong>{g.name}</Typography.Text>
                    <Button
                      type="text"
                      danger
                      size="small"
                      onClick={() => openDeleteGroupModal(g)}
                      loading={deleteGroupMutation.isPending}
                    >
                      −
                    </Button>
                  </Space>
                  <Space>
                    <Typography.Text type="secondary">占比 %</Typography.Text>
                    <InputNumber
                      min={0}
                      max={100}
                      size="small"
                      value={percentByGroupId[g.id]}
                      onChange={(v) =>
                        setPercentByGroupId((prev) => ({
                          ...prev,
                          [g.id]: typeof v === "number" ? v : 0,
                        }))
                      }
                    />
                  </Space>
                </Space>
              }
            >
              {(projectPatients ?? [])
                .filter((row) => row.group === g.id)
                .map((row) => (
                  <ConfirmedPatientCard
                    key={`confirmed-${row.id}`}
                    row={row}
                    patientById={patientById}
                    onRequestUnbind={(r) => setUnbindTarget(r)}
                  />
                ))}
              {localAssignments
                .filter((a) => a.groupId === g.id)
                .map((a) => {
                  const patient = patientById[a.patientId];
                  if (!patient) return null;
                  return (
                    <LocalAssignmentCard
                      key={`local-${a.patientId}`}
                      patient={patient}
                      onRemove={() =>
                        setLocalAssignments((prev) => prev.filter((item) => item.patientId !== a.patientId))
                      }
                    />
                  );
                })}
            </Card>
          ))}
        </div>
```

- [ ] **Step 8: 更新分组删除数量统计**

把 `countPatientsInGroup` 改为：

```typescript
  const countPatientsInGroup = (groupId: number) =>
    (projectPatients ?? []).filter((row) => row.group === groupId).length +
    localAssignments.filter((row) => row.groupId === groupId).length;
```

- [ ] **Step 9: 运行看板测试**

Run:

```bash
cd frontend
npm test -- ProjectGroupingBoard.test.tsx groupingBoardUtils.test.ts
```

Expected: PASS。

- [ ] **Step 10: 提交看板实现**

```bash
git add frontend/src/pages/projects/ProjectGroupingBoard.tsx frontend/src/pages/projects/ProjectGroupingBoard.test.tsx
git commit -m "feat: 项目看板改为前端临时随机确认入组"
```

---

### Task 7: 前端周边页面清理

**Files:**
- Modify: `frontend/src/pages/patients/PatientDetailPage.tsx`
- Modify: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: 删除患者详情页状态列类型**

在 `frontend/src/pages/patients/PatientDetailPage.tsx` 中，将项目关系类型里的状态字段删除：

```typescript
type ProjectPatientRow = {
  id: number;
  project: number;
  patient: number;
  patient_name: string;
  patient_phone: string;
  group: number | null;
  group_name: string | null;
  enrolled_at: string;
};
```

- [ ] **Step 2: 删除患者详情页状态列**

在同一文件中删除项目表列：

```typescript
{
  title: "分组状态",
  dataIndex: "grouping_status",
}
```

如果该列使用了 `Tag` 或状态映射，只删除与 `grouping_status` 直接相关的映射，不改动分组名、CRF 入口和项目入口列。

- [ ] **Step 3: 更新 App 测试 mock**

在 `frontend/src/app/App.test.tsx` 中删除 mock `project-patients` 数据里的：

```typescript
grouping_status: "confirmed",
```

和：

```typescript
grouping_status: "pending",
```

保留 `group`、`patient_name`、`patient_phone` 等字段。

- [ ] **Step 4: 扫描前端状态引用**

Run:

```bash
rg -n "GroupingStatus|grouping_status|reset-pending|/randomize/" frontend/src
```

Expected: 无输出。

- [ ] **Step 5: 运行前端相关测试**

Run:

```bash
cd frontend
npm test -- App.test.tsx ProjectGroupingBoard.test.tsx
```

Expected: PASS。

- [ ] **Step 6: 提交前端周边清理**

```bash
git add frontend/src/pages/patients/PatientDetailPage.tsx frontend/src/app/App.test.tsx
git commit -m "refactor: 前端移除分组状态展示"
```

---

### Task 8: 全量验证与文档指向

**Files:**
- Modify: `docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md`

- [ ] **Step 1: 更新旧 spec 指向**

在 `docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md` 顶部标题后增加：

```markdown
> 2026-05-12 更新：分组随机与绑定语义以 `docs/superpowers/specs/2026-05-12-frontend-only-randomization-confirmed-binding-design.md` 为准；本文中 pending、草案或池过滤相关描述已过时。
```

- [ ] **Step 2: 运行后端全量测试**

Run:

```bash
cd backend
pytest -q
```

Expected: PASS。

- [ ] **Step 3: 运行前端测试**

Run:

```bash
cd frontend
npm test
```

Expected: PASS。

- [ ] **Step 4: 运行前端 build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS，`tsc` 与 Vite build 成功。

- [ ] **Step 5: 最终引用扫描**

Run:

```bash
rg -n "GroupingStatus|grouping_status|reset-pending|/randomize/|患者池（全部患者）|尚未加入本项目" backend frontend
```

Expected: 不出现运行时代码引用。若只在历史文档中出现，保持不动或按 Step 1 增加过时说明。

- [ ] **Step 6: 提交文档与验证收口**

```bash
git add docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md
git commit -m "docs: 标注旧分组看板设计已被新语义替代"
```
