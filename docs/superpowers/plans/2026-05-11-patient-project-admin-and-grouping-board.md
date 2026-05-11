# 患者 / 项目 / 分组看板实现计划

> **状态：已过时 / SUPERSEDED**（2026-05-11）：用户验收反馈后已彻底删除"批次"概念。后续以 `docs/superpowers/plans/2026-05-11-drop-batch-concept.md` 为准。本文件仅作历史留档。

> **修订：** 2026-05-11 按 `writing-plans` 规范对齐最新 spec（停用二次确认、无批次 UI、解绑与 CRF/处方、全局确认 Modal、Task 9–10）。执行请用 **executing-plans**（或 subagent-driven-development），勿用 executing-plans「生成」文档。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md`（含多次修订）与线框 `docs/superpowers/brainstorm/2026-05-11-grouping-board-wireframe.html` 交付：患者编辑、**物理删除与停用**（均须 **二次确认 + 影响/关联说明**）、删除保护、多项目入组（入组后引导至看板分组）；患者详情项目表与 CRF；项目列表列调整与删除（同上确认规则）；项目详情 **看板式分组工作台**：**产品不暴露「批次」**（可本地草稿 + 可选单工作集后端）、勾选集合、随机/取消随机、列占比、删组、新增分组、拖拽 **仅未确认**、已确认置灰、**解绑项目**（删除 `ProjectPatient` + **CRF 作废/处方无效** + 医生端过滤）；全局删除类 **阻断式 Modal** 与 spec 一致。

**Architecture:** 纵向三切片不变。看板层：**UI 不出现批次列表/编号**；随机与确认可继续复用现有 `create_grouping_batch` / `confirm` 作过渡实现，或收敛为「单项目单 pending 工作集」API（实现前对比 spec「实现备注」二选一，在 Task 7 首步写死）。**解绑**独立事务：先作废/软删 CRF 相关（`VisitRecord` / `CrfExport` 等）、处方置 **TERMINATED**（或扩展状态），再删 `ProjectPatient`。**全局确认**：抽取可复用 `DestructiveActionModal`（ props：`title`、`impactSummary[]`、`onConfirm`、禁止态仅展示 `reason` ）。比例与拖拽策略同前。

**Tech Stack:** Django、DRF、pytest、React 18、TypeScript、TanStack Query v5、Ant Design 5、（可选）@dnd-kit。

**线框与 spec 对齐备忘（实现时纳入验收）：** 患者池 Tag/勾选样式；主按钮「随机分组」；列头「新增分组」、悬浮「−」删组；顶栏 **不得出现「生成批次」「批次 #」** 等文案——改为「取消随机」「确认分组」等与 spec 一致；解绑入口在已确认卡片上且走二次确认 + CRF/处方警告。

---

## 文件与职责总览

| 路径 | 职责 |
|------|------|
| `backend/apps/patients/views.py` | `destroy` 保护；可选 `@action` 批量入组 |
| `backend/apps/patients/serializers.py` | 入组请求体验证（若新增 action body） |
| `backend/apps/patients/tests/` | 删除保护、入组 API 单测（新建目录） |
| `backend/apps/studies/views.py` | `StudyProjectViewSet.destroy` 保护；可选列表 annotate `patient_count` |
| `backend/apps/studies/serializers.py` | 项目序列化器暴露 `patient_count`（若列表需要） |
| `backend/apps/studies/tests/test_grouping.py` 或新建 `test_project_patient_admin.py` | 项目删除、入组幂等等 |
| `frontend/src/pages/patients/PatientListPage.tsx` | 行内编辑入口 |
| `frontend/src/pages/patients/PatientDetailPage.tsx` | 编辑表单、删除/停用、多项目入组、项目行 + CRF |
| `frontend/src/pages/patients/components/`（新建） | 可复用：入组 Modal、项目参与表 |
| `frontend/src/pages/projects/ProjectListPage.tsx` | 列、删除、详情按钮 |
| `frontend/src/pages/projects/ProjectDetailPage.tsx` | 组装看板，去掉 CRF Tab |
| `frontend/src/pages/projects/ProjectGroupingBoard.tsx`（新建/改） | 患者池、勾选、随机/取消随机、列、拖拽、确认；**无批次 UI**；解绑 |
| `frontend/src/pages/components/DestructiveActionModal.tsx`（新建，路径可调整） | 统一二次确认 + 影响列表 + 禁止时仅展示原因 |
| `backend/apps/studies/services/unbind_project_patient.py`（新建，路径可调整） | 解绑事务：CRF 作废、处方无效、删 `ProjectPatient` |
| `frontend/src/pages/projects/groupingBoardUtils.ts`（新建） | 占比 ↔ `target_ratio` 换算与尾差 |
| `docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md` | 若实现中发现与线框不一致，增量修订一节「线框定稿」 |

---

### Task 1: 患者删除保护（后端）

**Files:**

- Modify: `backend/apps/patients/views.py`
- Create: `backend/apps/patients/tests/test_patient_delete_guard.py`
- Create: `backend/apps/patients/tests/conftest.py`（若尚无：提供 `doctor`、`patient` fixture，可复制 `apps/studies/tests/conftest.py` 最小子集）

- [ ] **Step 1: 编写失败用例（存在 ProjectPatient 时禁止 DELETE）**

```python
# backend/apps/patients/tests/test_patient_delete_guard.py
import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject


@pytest.mark.django_db
def test_cannot_delete_patient_with_project_link(doctor, patient, project):
    group = StudyGroup.objects.create(project=project, name="G1", target_ratio=1)
    ProjectPatient.objects.create(project=project, patient=patient, group=group)

    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.delete(f"/api/patients/{patient.id}/")
    assert r.status_code == 400
    assert "detail" in r.data
    assert Patient.objects.filter(pk=patient.pk).exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest apps/patients/tests/test_patient_delete_guard.py::test_cannot_delete_patient_with_project_link -q`  
Expected: **FAIL**（例如 204 或 200，因尚未实现 `destroy` 逻辑）

- [ ] **Step 3: 在 `PatientViewSet` 中实现 `destroy`**

```python
# backend/apps/patients/views.py — 在 PatientViewSet 类体内增加
from rest_framework.exceptions import ValidationError
from apps.studies.models import ProjectPatient

def destroy(self, request, *args, **kwargs):
    patient = self.get_object()
    if ProjectPatient.objects.filter(patient=patient).exists():
        raise ValidationError({"detail": "该患者已关联研究项目，无法删除。请先移除项目关联或停用档案。"})
    return super().destroy(request, *args, **kwargs)
```

（若项目中对「CRF 数据」另有独立模型判定，在本步之后追加 `if crf_has_data(...):` 与对应单测。）

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest apps/patients/tests/test_patient_delete_guard.py -q`  
Expected: **PASS**

- [ ] **Step 5: Git 提交**

```bash
git add backend/apps/patients/views.py backend/apps/patients/tests/
git commit -m "feat(patients): 存在项目关联时禁止删除患者"
```

---

### Task 2: 项目删除保护（后端）

**Files:**

- Modify: `backend/apps/studies/views.py`（`StudyProjectViewSet`）
- Create: `backend/apps/studies/tests/test_study_project_delete_guard.py`

- [ ] **Step 1: 编写失败用例**

```python
# backend/apps/studies/tests/test_study_project_delete_guard.py
import pytest
from rest_framework.test import APIClient

from apps.studies.models import GroupingBatch, ProjectPatient, StudyGroup


@pytest.mark.django_db
def test_cannot_delete_project_with_project_patient(doctor, project, patient):
    g = StudyGroup.objects.create(project=project, name="G", target_ratio=1)
    ProjectPatient.objects.create(project=project, patient=patient, group=g)
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.delete(f"/api/studies/projects/{project.id}/")
    assert r.status_code == 400


@pytest.mark.django_db
def test_cannot_delete_project_with_pending_batch(doctor, project, patient):
    g = StudyGroup.objects.create(project=project, name="G", target_ratio=1)
    batch = GroupingBatch.objects.create(project=project, status=GroupingBatch.Status.PENDING)
    ProjectPatient.objects.create(
        project=project, patient=patient, group=g, grouping_batch=batch, grouping_status="pending"
    )
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.delete(f"/api/studies/projects/{project.id}/")
    assert r.status_code == 400
```

（第二用例若与「仅禁止有患者」重复，可合并为一条业务规则单测；以产品最终文案为准。）

- [ ] **Step 2: 运行测试 → 预期 FAIL**

Run: `cd backend && pytest apps/studies/tests/test_study_project_delete_guard.py -q`

- [ ] **Step 3: 实现 `StudyProjectViewSet.destroy`**

```python
# backend/apps/studies/views.py — StudyProjectViewSet 内
from rest_framework.exceptions import ValidationError

def destroy(self, request, *args, **kwargs):
    project = self.get_object()
    if ProjectPatient.objects.filter(project=project).exists():
        raise ValidationError({"detail": "项目中仍有患者，无法删除。"})
    if GroupingBatch.objects.filter(project=project, status=GroupingBatch.Status.PENDING).exists():
        raise ValidationError({"detail": "存在待确认的分组批次，无法删除。"})
    return super().destroy(request, *args, **kwargs)
```

- [ ] **Step 4: pytest 通过**

- [ ] **Step 5: Commit** `feat(studies): 项目删除前校验患者与待确认批次`

---

### Task 3: 患者批量加入多项目（后端 API）

**Files:**

- Modify: `backend/apps/patients/views.py`
- Modify: `backend/apps/patients/serializers.py`（如需要 `EnrollProjectsSerializer`）
- Create/Modify: `backend/apps/patients/tests/test_enroll_projects.py`

- [ ] **Step 1: 新增 `POST /api/patients/{id}/enroll-projects/`**（或等价路径，与 `backend/config/urls.py` 中 patients 路由前缀对齐）

请求体：`{"project_ids": [1, 2, 3]}`。对每个 `project_id`：`get_or_create(ProjectPatient)`；已存在则跳过并返回 `skipped_project_ids` 与 `created`。**已定稿（spec）：** 仅创建 `ProjectPatient`（`group` 可空、`grouping_status` 与现有默认一致）；响应 `detail` 固定提示「请到各项目详情看板勾选患者并完成随机分组」。**禁止**在本 action 内自动 `assign_groups` 或静默写 `group_id`。

- [ ] **Step 2: 单测：多项目、幂等跳过**

- [ ] **Step 3: Commit** `feat(patients): 批量加入研究项目`

---

### Task 4: 切片一 · 前端患者列表与详情

**Files:**

- Modify: `frontend/src/pages/patients/PatientListPage.tsx`（行内「编辑」→ Modal + `PATCH /api/patients/:id/`）
- Modify: `frontend/src/pages/patients/PatientDetailPage.tsx`（`Form` 编辑、**物理删除** 与 **停用**、`enroll-projects` Modal、项目表 + `Link` 到 `/crf?projectPatientId=`）
- Create: `frontend/src/pages/components/DestructiveActionModal.tsx`（或同职责组件；可被 Task 5、7 复用）
- 可能新增: `frontend/src/pages/patients/usePatientProjects.ts`（`GET /api/studies/project-patients/?patient=<id>` 若需新 query；若后端无 `patient` 过滤，则在 Task 3 同步加 `get_queryset` 过滤）

- [ ] **Step 1: 若缺失 `patient` query  on `ProjectPatientViewSet`，后端补过滤并单测**

- [ ] **Step 2: 详情页拉取 `project_patients` 列表渲染表格**

- [ ] **Step 3: 入组 Modal：`useQuery` 拉项目列表，`disabled: enrolled`**

- [ ] **Step 4: 物理删除：点击后打开 `DestructiveActionModal`；先 `GET` 患者详情或专用 `.../delete-preflight/`（若无则前端根据已拉取的项目表拼装影响摘要）展示关联项；确认后 `DELETE`；若 400 用 Modal 展示 `detail`（禁止 toast-only）**

- [ ] **Step 5: 停用：点击「停用」→ **二次确认 Modal**，文案说明影响（如：列表默认隐藏、不可再入组——与后端 `is_active` 语义一致）；确认后 `PATCH /api/patients/:id/` `{"is_active": false}`**

- [ ] **Step 6: 随访占位 `Alert` 文案（spec 非目标）**

- [ ] **Step 7: 手动验证 + commit** `feat(frontend): 患者编辑、删除/停用确认与多项目入组`

---

### Task 5: 切片二 · 项目列表

**Files:**

- Modify: `frontend/src/pages/projects/ProjectListPage.tsx`
- Modify: `backend/apps/studies/serializers.py` + `views.py`（可选 `patient_count` annotate）

- [ ] **Step 1: 移除 CRF 列；增加「详情」「删除」列**

- [ ] **Step 2: 删除：使用与 Task 4 同构的 **二次确认 Modal**（可复用 `DestructiveActionModal`）；文案须含「将删除项目及…」等 **关联影响**（患者入组数、待确认分组工作集等，以前端已知字段 + 可选预检为准）；确认后 `DELETE`；400 时 Modal 展示原因**

- [ ] **Step 3: `patient_count`（若后端未返回，先显示「—」占位，后续 Task 补字段）**

- [ ] **Step 4: Commit** `feat(frontend): 研究项目列表操作与列调整`

---

### Task 6: 占比纯函数与单测（前后端择一或双份）

**Files:**

- Create: `frontend/src/pages/projects/groupingBoardUtils.ts`
- Create: `frontend/src/pages/projects/groupingBoardUtils.test.ts`（Vitest 若已配置；否则 Jest；若全无则仅手动表 + 后端 `apps/studies/tests/test_ratio_display.py`）

逻辑示例（概念，实现时写满边界）：

```typescript
// groupingBoardUtils.ts — 示例签名
export function ratiosToTargetRatios(pcts: number[]): number[] {
  /* 尾差：如 [33,33,34] 或全 33 与权重 1:1:1 一致 */
}
export function targetRatiosToDisplayPercents(ratios: number[]): number[] {
  /* 展示百分比整数，和为 100 */
}
```

- [ ] **Step 1: 为 1:1:1、1:2:1 写单测**

- [ ] **Step 2: 实现函数**

- [ ] **Step 3: Commit** `feat(frontend): 分组占比展示与权重换算`

---

### Task 7: 切片三 · `ProjectGroupingBoard` 壳与数据

**Files:**

- Create/Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
- Modify: `frontend/src/pages/projects/ProjectDetailPage.tsx`（移除 `Tabs` 中 CRF Tab；嵌入看板 + 可选抽屉打开原 `ProjectGroupsTab` 表单逻辑）

- [ ] **Step 1: `useQuery` groups、`project-patients`、患者池数据源；**不渲染「批次 #」下拉**——内部可持 `currentBatchId` state（由创建随机接口返回），对用户仅表现为「当前待确认草案」**

- [ ] **Step 2: 渲染患者池（`Checkbox` + Tag 样式）；已入本项目者在池中置灰/不可选**

- [ ] **Step 3: 「随机分组」→ `POST .../projects/:id/create_grouping_batch/`** body `patient_ids` = **勾选 ∩ `grouping_status` 仍为 pending 且未确认分组**（与 spec 一致）；成功后列内展示草案；可选 `sessionStorage` 持久化本地草稿键（spec：可不存）**

- [ ] **Step 4: 列头 `InputNumber` 占比联动，`PATCH` 各 `StudyGroup`**

- [ ] **Step 5: 列头「−」删组：须 **二次确认 Modal** + 关联说明（组内患者数等），再 `DELETE /api/studies/groups/:id/`**

- [ ] **Step 6: 「新增分组」→ `Modal`+`Form`**

- [ ] **Step 7: 「取消随机」**：放弃当前未确认草案（实现首步阅读 `backend/apps/studies/views.py`：或删除 pending `GroupingBatch`、或清空 `ProjectPatient` 上 pending 草案字段；**与解绑 ProjectPatient 业务分离**；前后端选定一种并补单测）**

- [ ] **Step 8: 「确认分组」→ `POST .../grouping-batches/:id/confirm/`**（payload 与现有 `confirm` 对齐；**按钮文案不出现「批次」**）**

- [ ] **Step 9: 已确认卡片置灰、禁用拖拽；解绑按钮 → 调 **Task 9** 暴露的 API，Modal 含 CRF/处方警告**

- [ ] **Step 10: Commit** `feat(frontend): 项目分组看板（无批次 UI）`

---

### Task 8: 拖拽调整草稿分组

**Files:**

- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
- `package.json` / lockfile：添加 `@dnd-kit/core` `@dnd-kit/sortable` `@dnd-kit/utilities`

- [ ] **Step 1: 安装依赖**

Run: `cd frontend && npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities`

- [ ] **Step 2: 每列 `Droppable`，卡片 `Draggable`，`onDragEnd` 更新本地 state 并 `PATCH /api/studies/project-patients/:id/` 的 `group`**

- [ ] **Step 3: 已 `CONFIRMED` 的 `ProjectPatient` **禁止跨列拖拽**（与后端一致）；**未确认**可拖**

- [ ] **Step 4: Commit** `feat(frontend): 看板拖拽更新草稿分组`

---

### Task 9: 解绑 ProjectPatient（后端：CRF 作废 + 处方无效）

**Files:**

- Modify: `backend/apps/studies/views.py`（新增 `@action` 于 `ProjectPatientViewSet` 或 `StudyProjectViewSet`，如 `POST /api/studies/project-patients/{id}/unbind/`）
- Create: `backend/apps/studies/services/unbind_project_patient.py`（或 `apps/studies/services/project_patient_unbind.py`）
- Create: `backend/apps/studies/tests/test_unbind_project_patient.py`
- Modify: `apps/visits/models.py` 仅在需 **软删/作废字段** 时加 migration（若 spec 采用「标记作废」而当前无字段，本任务含 migration；若暂用 `VisitRecord.status` 扩展枚举，须迁移数据）

- [ ] **Step 1: 单测骨架 — 解绑后处方均为 TERMINATED（或选定无效状态）、访视作废语义可断言**

```python
# backend/apps/studies/tests/test_unbind_project_patient.py
import pytest
from rest_framework.test import APIClient

from apps.prescriptions.models import Prescription


@pytest.mark.django_db
def test_unbind_terminates_prescriptions_and_removes_link(doctor, project_patient, active_prescription):
    assert active_prescription.project_patient_id == project_patient.id
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/project-patients/{project_patient.id}/unbind/")
    assert r.status_code == 200
    active_prescription.refresh_from_db()
    assert active_prescription.status == Prescription.Status.TERMINATED
    assert not __import__(
        "apps.studies.models", fromlist=["ProjectPatient"]
    ).ProjectPatient.objects.filter(pk=project_patient.pk).exists()
```
（Step 1 运行后预期 **FAIL**：404 或 405，直至 Step 3 实现 `unbind` 路由。）

- [ ] **Step 2: 实现服务函数**（`@transaction.atomic`）：  
  `select_for_update` 锁定 `ProjectPatient` → 将该 PP 下所有 `Prescription` 更新为 `TERMINATED`（排除已是 TERMINATED）→ `VisitRecord` / `CrfExport` 按 spec **作废**（加 `voided_at` 或 `is_voided` 字段，或写入 `form_data` 元数据 —— **选一种并在单测中断言不可再用于 CRF preview 有效路径**）→ 删除 `ProjectPatient`（若需保留审计行则改为软删，**须与 spec「解绑」一致**）。

- [ ] **Step 3: View 调用服务；仅 `grouping_status=CONFIRMED` 或产品允许的状态可解绑；权限 `IsAdminOrDoctor`**

- [ ] **Step 4: `pytest apps/studies/tests/test_unbind_project_patient.py -q` 全绿**

- [ ] **Step 5: Commit** `feat(studies): 解绑项目患者并作废CRF相关与处方`

---

### Task 10: 医生端 / 处方列表默认过滤（若仅后端）

**Files:**

- Modify: `backend/apps/prescriptions/views.py` 的 `get_queryset`：`PrescriptionViewSet` 默认 **排除** `TERMINATED` 及解绑产生的无效状态（若新增枚举则一并过滤）
- Modify: `frontend/src/pages/prescriptions/PrescriptionPanel.tsx`（若仍展示已终止，改为 Tab「历史」或隐藏——**与 spec「医生端不展示」对齐**；管理端若共用组件则按路由区分）

- [ ] **Step 1: 后端单测：列表接口不返回已终止处方（医生角色）**

- [ ] **Step 2: 前端验证处方面板仅展示可用版本**

- [ ] **Step 3: Commit** `fix(prescriptions): 默认列表隐藏无效/终止处方`

---

## 自检（对照 spec）

| Spec 要点 | 覆盖 Task |
|-----------|-----------|
| 患者删除保护 | Task 1 |
| 项目删除保护 | Task 2 |
| 多项目入组 + 置灰 + 看板提示 | Task 3、4 |
| 患者详情项目行 CRF | Task 4 |
| **物理删除 / 停用** 二次确认 + 影响说明 | Task 4、`DestructiveActionModal` |
| 列表隐藏 CRF、详情/**删除 Modal** | Task 5 |
| **无批次 UI**、随机/取消/确认、已确认置灰、解绑 | Task 7、8、9 |
| 解绑后 CRF 作废、处方无效、医生端不展示 | Task 9、10 |
| 占比尾差 | Task 6、7 |
| 线框：随机分组、减号、新增分组 | Task 7、8 |
| CRF 主路径不在项目详情 Tab | Task 7 |
| 随访占位 | Task 4 |

**占位扫描：** Task 3 入组行为已在 spec 定稿（仅创建链接 + 提示看板）；Task 7 Step 7「取消随机」须在编码前读 `views.py` 选定实现并删掉本句提醒。

---

## 执行方式

计划文件：`docs/superpowers/plans/2026-05-11-patient-project-admin-and-grouping-board.md`（**2026-05-11 已按最新 spec 修订**：无批次产品语义、解绑与 CRF/处方、全局删除/停用确认、Task 9–10）。

**说明：** `superpowers:executing-plans` 用于 **按本计划逐步执行编码与验证**，不负责「生成计划」；本文件由 `writing-plans` 规范 **修订生成**。

**1. Subagent-Driven（推荐）** — 每任务独立子代理，任务间人工复核。  
**2. Inline Execution** — 本会话或后续会话使用 **executing-plans**，按 Task 顺序执行并设检查点。

你更倾向哪一种？
