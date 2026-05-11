# 患者 / 项目 / 分组看板实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md` 与线框 `docs/superpowers/brainstorm/2026-05-11-grouping-board-wireframe.html` 交付：患者编辑/删除保护、多项目入组、患者详情项目表与 CRF；项目列表列调整与删除保护；项目详情看板式分组工作台（患者池、随机分组、列占比、悬浮减号删组、新增分组、拖拽草稿、批次确认）。

**Architecture:** 纵向三切片顺序交付——先患者域与 API 规则，再项目列表与删除，最后聚合 `ProjectDetailPage` 为看板组件并对接既有 `GroupingBatch` / `create_grouping_batch` / `confirm`。比例展示与写回沿用 `StudyGroup.target_ratio`；前端占比控件与后端互转单独小模块（纯函数 + 单测）。拖拽推荐 `@dnd-kit/core` + `@dnd-kit/sortable`（与 React 18 兼容），若团队更熟 `react-beautiful-dnd` 需评估维护状态后再定。

**Tech Stack:** Django、DRF、pytest、React 18、TypeScript、TanStack Query v5、Ant Design 5、（可选）@dnd-kit。

**线框与 spec 对齐备忘（实现时纳入验收）：** 患者池标签尺寸对齐 Ant Design Tag/可选中样式；患者池下主按钮「随机分组」；分组标题行仅「新增分组」；悬浮整列时列头右上角「−」去掉分组；顶栏保留配置/确认/生成批次等与线框一致或按产品收口合并文案。

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
| `frontend/src/pages/projects/ProjectGroupingBoard.tsx`（新建） | 患者池、随机分组、列、拖拽、批次工具条 |
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

请求体：`{"project_ids": [1, 2, 3]}`。对每个 `project_id`：`get_or_create(ProjectPatient)`；已存在则跳过并在响应中返回 `skipped_project_ids` 与 `created` 列表。创建后按 spec 提示需「按比例分组」：可复用 `StudyProject.create_grouping_batch` 中单次 `assign_groups` 逻辑抽取为服务函数，或在入组后对**新创建**的 `ProjectPatient` 同步写入 `group`（若产品要求入组即分组，而非等批次；**以 spec「提示自动按比例」为准**：至少保证新 `ProjectPatient` 有一条明确的 `group` 分配策略——若当前产品为「入组后进批次再分」，则本 action 仅创建链接并返回 `detail` 提示进入项目看板完成随机分组；**实现前再读 spec 第 3 节与已定稿对话**二选一写死，避免半套逻辑。）

**推荐实现（与现有批次模型一致）：** 本 action 仅 `get_or_create` `ProjectPatient`（`group` 可为空），响应 `detail` 携带中文提示「请到项目详情看板选择患者并随机分组」；比例分配仍在 `create_grouping_batch`。若产品坚持入组瞬间分组，则调用 `assign_groups` 并直接写 `group_id`（不再走 pending），需在 spec 增补一句后再编码。

- [ ] **Step 2: 单测：多项目、幂等跳过**

- [ ] **Step 3: Commit** `feat(patients): 批量加入研究项目`

---

### Task 4: 切片一 · 前端患者列表与详情

**Files:**

- Modify: `frontend/src/pages/patients/PatientListPage.tsx`（行内「编辑」→ Modal + `PATCH /api/patients/:id/`）
- Modify: `frontend/src/pages/patients/PatientDetailPage.tsx`（`Form` 编辑、`DELETE` 或停用 `PATCH`、`enroll-projects` Modal、项目表 + `Link` 到 `/crf?projectPatientId=`）
- 可能新增: `frontend/src/pages/patients/usePatientProjects.ts`（`GET /api/studies/project-patients/?patient=<id>` 若需新 query；若后端无 `patient` 过滤，则在 Task 3 同步加 `get_queryset` 过滤）

- [ ] **Step 1: 若缺失 `patient` query  on `ProjectPatientViewSet`，后端补过滤并单测**

- [ ] **Step 2: 详情页拉取 `project_patients` 列表渲染表格**

- [ ] **Step 3: 入组 Modal：`useQuery` 拉项目列表，`disabled: enrolled`**

- [ ] **Step 4: 随访占位 `Alert` 文案（spec 非目标）**

- [ ] **Step 5: 手动验证 + commit** `feat(frontend): 患者编辑、删除保护与多项目入组`

---

### Task 5: 切片二 · 项目列表

**Files:**

- Modify: `frontend/src/pages/projects/ProjectListPage.tsx`
- Modify: `backend/apps/studies/serializers.py` + `views.py`（可选 `patient_count` annotate）

- [ ] **Step 1: 移除 CRF 列；增加「详情」「删除」列**

- [ ] **Step 2: 删除 `Modal.confirm` + `DELETE /api/studies/projects/:id/`**，处理 400 `detail`

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

- Create: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
- Modify: `frontend/src/pages/projects/ProjectDetailPage.tsx`（移除 `Tabs` 中 CRF Tab；嵌入看板 + 可选抽屉打开原 `ProjectGroupsTab` 表单逻辑）

- [ ] **Step 1: `useQuery` groups / project-patients / patients / pending batches**

- [ ] **Step 2: 渲染患者池（Ant Design `Checkbox` + `Space`/`Tag` 勾选样式按设计）**

- [ ] **Step 3: 患者池下 `Button type="primary"`「随机分组」→ 调用 `POST .../projects/:id/create_grouping_batch/`**，body `patient_ids` 来自勾选，`seed` 可选 `Date.now()`**

- [ ] **Step 4: 列头 `InputNumber` 占比联动，失焦或「应用」时 `PATCH` 各 `StudyGroup`**

- [ ] **Step 5: 列右上角 `Button` 悬浮显示「−」→ `Modal.confirm` 后 `DELETE /api/studies/groups/:id/`**（若后端禁止删非空组，展示 `detail`）

- [ ] **Step 6: 「新增分组」→ 复用原创建 Modal 或 `Modal`+`Form`**

- [ ] **Step 7: 顶栏「确认分组」调用既有 `POST .../grouping-batches/:id/confirm/`** payload 与 `GroupingBatchPanel` 对齐

- [ ] **Step 8: Commit** `feat(frontend): 项目分组看板初版`

---

### Task 8: 拖拽调整草稿分组

**Files:**

- Modify: `frontend/src/pages/projects/ProjectGroupingBoard.tsx`
- `package.json` / lockfile：添加 `@dnd-kit/core` `@dnd-kit/sortable` `@dnd-kit/utilities`

- [ ] **Step 1: 安装依赖**

Run: `cd frontend && npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities`

- [ ] **Step 2: 每列 `Droppable`，卡片 `Draggable`，`onDragEnd` 更新本地 state 并 `PATCH /api/studies/project-patients/:id/` 的 `group`**

- [ ] **Step 3: 已 `CONFIRMED` 的 `ProjectPatient` 禁止改组（与后端 `perform_update` 一致，前端禁用拖拽）**

- [ ] **Step 4: Commit** `feat(frontend): 看板拖拽更新草稿分组`

---

## 自检（对照 spec）

| Spec 要点 | 覆盖 Task |
|-----------|-----------|
| 患者删除保护 | Task 1 |
| 项目删除保护 | Task 2 |
| 多项目入组 + 置灰 + 提示 | Task 3、4 |
| 患者详情项目行 CRF | Task 4 |
| 列表隐藏 CRF、详情/删除 | Task 5 |
| 批次保留、确认、随机 | Task 7 |
| 占比尾差 | Task 6、7 |
| 线框：随机分组按钮、减号、新增分组 | Task 7、8 |
| CRF 主路径不在项目详情 Tab | Task 7 |
| 随访占位 | Task 4 |

**占位扫描：** Task 3 中「入组是否立即写 group」依赖产品最终一句话；实现前在 spec 增加一句并删除本计划中的分支说明。

---

## 执行方式

计划已保存到 `docs/superpowers/plans/2026-05-11-patient-project-admin-and-grouping-board.md`。

**1. Subagent-Driven（推荐）** — 每任务独立子代理，任务间人工复核，迭代快。  
**2. Inline Execution** — 本会话内用 executing-plans 按勾选逐步执行、设检查点。

你更倾向哪一种？
