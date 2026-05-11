# 删除批次概念，重构随机/确认/池语义

日期：2026-05-11  
分支：feat/drop-batch-concept（已合并 main）  
基线：main @ fa686e5（以 `git log -1 --oneline` 为准）  
状态：**已落地**；文档/测试收口见 `docs/superpowers/plans/2026-05-11-post-drop-batch-consolidation-execution-plan.md`

---

## 1. 背景

验收反馈：
1. 不存在「患者 ↔ 项目」加入/绑定关系；只有"在某分组中被确认"才形成绑定（即 ProjectPatient.confirmed）。
2. 「患者池」仅是 UI 上表达「所有患者」的虚拟概念，不建模为实体。
3. **彻底删除批次（GroupingBatch）概念**；分组内未确认者 = 未入组；重新随机时所有未确认者都参与；组内列表永远展示全量（含 confirmed）。
4. 已确认者不能再次随机，只能被删除（解绑）；解绑后回到池视图，勾选后可再次参与随机。
5. 已确认者在组内列表中**置灰**显示，**不隐藏**。

澄清问题答复（来自用户）：
- 池显示：已在本项目（pending/confirmed 皆然）的患者**不**在池里展示。
- 重新随机范围：池里勾选 + 项目里所有 pending，一起重新随机；confirmed 保持不动。
- `enroll-projects` API：保留接口，**语义改为「直接确认入组」**（前端需选 group_id 并立即 confirmed）。
- 数据迁移：本地开发，简化为 `manage.py migrate` 直接迁。
- 隔离：开 worktree + 全程 TDD。

---

## 2. 目标模型与 API

### 2.1 模型

- 保留：`StudyProject`、`StudyGroup`、`ProjectPatient`、`Patient`
- 删除：`GroupingBatch` 模型
- 修改：`ProjectPatient.grouping_batch` 字段 → 删除
- 保留：`ProjectPatient.grouping_status`（pending / confirmed）+ `ProjectPatient.group`

### 2.2 API（统一以项目为粒度）

| Method | URL | 语义 |
|---|---|---|
| POST | `/api/studies/projects/{id}/randomize/` | 重新随机：传 `pool_patient_ids`（池里勾选）+ `seed?`，与项目里所有 pending 一起做随机；confirmed 不变；返回当前所有 pending 分配 |
| POST | `/api/studies/projects/{id}/reset-pending/` | 清空：项目下所有 pending 的 `group=null`，可重新选 |
| POST | `/api/studies/projects/{id}/confirm-grouping/` | 确认：项目里所有 pending → confirmed |
| POST | `/api/patients/{id}/enroll-projects/` | **改造**：入参 `[{project_id, group_id}, ...]`，立即建 ProjectPatient 并设为 confirmed |

### 2.3 删除

- `POST /api/studies/projects/{id}/create_grouping_batch/`
- `POST /api/studies/projects/{id}/discard-grouping-draft/`
- 整个 `GroupingBatchViewSet`（含 `/grouping-batches/...` 路由 + `/confirm/`）
- `ProjectPatient.serializer.grouping_batch` 字段、`project-patients/?grouping_batch=` 过滤参数

### 2.4 解绑（unbind）保持原逻辑

- 仅 confirmed 可调用；终止处方；删 ProjectPatient；CRF 清理。
- 删除后该患者重新出现在「池」。

---

## 3. 实施步骤（严格 TDD：红→绿→重构）

### 阶段 A：后端

**A1. 红：新增 `test_reset_pending_grouping.py`**
- 测点：
  - `POST /projects/{id}/reset-pending/` 把项目内 pending 的 `group=null`，confirmed 不动。
  - 没有任何 pending 时返回 400 或 200 空操作（采用 200 + 空 detail，更友好）。

**A2. 绿：在 `StudyProjectViewSet` 新增 `reset_pending` action**

**A3. 红：新增 `test_randomize_grouping.py`**
- 测点：
  - 仅传 `pool_patient_ids=[A,B]`、项目里没有 pending → 创建 2 个 pending ProjectPatient，按 group 比例分配 group_id。
  - 已存在 pending [C,D] + `pool_patient_ids=[E]` → 4 人一起重新随机；C/D 的 group 可能变；confirmed 的 F 保持不动。
  - 池里勾选的患者已经是 confirmed → 跳过且不报错（防御）。
  - 项目没有 active group → 400。
  - `pool_patient_ids` 空 且 项目无 pending → 400「无患者可参与随机」。
  - `pool_patient_ids` 空 但 项目有 pending → 200，对现有 pending 重新洗牌。
  - 不存在的 patient_id → 400。
  - 返回 payload：`{ assignments: [{project_patient_id, group_id}, ...] }`。

**A4. 绿：在 `StudyProjectViewSet` 新增 `randomize` action**
- 步骤：
  1. 验证 active groups 存在；
  2. 验证 pool_patient_ids 全部存在；
  3. 合并集合 = 池里勾选的 patient_id（新建 ProjectPatient pending）+ 项目里所有 pending 的 patient_id；
  4. 若合并集合为空 → 400；
  5. `assign_groups(...)` 返回 `{patient_id: group_id}`；
  6. 对池里勾选：`get_or_create(ProjectPatient)` 后写 group + status=pending；
  7. 对项目原有 pending：update group；
  8. 对池里勾选但已存在且为 confirmed 的：跳过；
  9. 调用 `ensure_default_visits` 仅对新建项。

**A5. 红：新增 `test_confirm_grouping.py`**
- 测点：
  - `POST /projects/{id}/confirm-grouping/` 把项目里所有 pending 改为 confirmed。
  - 没有任何 pending 时返回 400。
  - 已 confirmed 的不动。

**A6. 绿：在 `StudyProjectViewSet` 新增 `confirm_grouping` action**

**A7. 红：重写 `test_enroll_projects.py`**
- 入参从 `{project_ids: [...]}` 改为 `{enrollments: [{project_id, group_id}, ...]}`。
- 测点：
  - 多组直接确认：创建 N 个 ProjectPatient，全部 confirmed，group_id 已写入。
  - 同一患者在同一项目已存在 → 报错或跳过（采取报错 400「该患者已在 X 项目」更明确）。
  - group_id 不属于该 project → 400。
  - 未知 project_id / group_id → 400。

**A8. 绿：改造 `EnrollProjectsSerializer` 与 `enroll_projects` view**

**A9. 删除：原 `test_discard_grouping_draft.py`**

**A10. 删除：`StudyProjectViewSet.create_grouping_batch` + `discard_grouping_draft`、`GroupingBatchViewSet`、URL 注册、`GroupingBatchSerializer`、`ProjectPatient.serializer.grouping_batch`、`get_queryset` 里的 `grouping_batch` 过滤、`select_related("grouping_batch")`**

**A11. 改 `test_study_project_delete_guard.py`**
- 删除 `test_cannot_delete_project_with_pending_batch_only` 测试用例（无批次概念）。
- 新增（可选）：`test_cannot_delete_project_with_pending_project_patient` —— 项目里仅有 pending ProjectPatient 时禁止删除（现有 `ProjectPatient.objects.filter(project=project).exists()` 已经覆盖，不再额外约束）。

**A12. 改 `views.py StudyProjectViewSet.destroy`**：移除 GroupingBatch 检查（直接保留 ProjectPatient 检查即可）。

**A13. Migration：删除 `GroupingBatch` 模型 + `ProjectPatient.grouping_batch` 字段**
- `python manage.py makemigrations studies`
- 提交生成的 0002 文件
- 运行 `python manage.py migrate`（开发库直接迁，不写数据保留逻辑）

**A14. 验证：`pytest` 全绿，特别确认 32 → 应增加到约 32-2(删) + 5-6(新) ≈ 35+**

---

### 阶段 B：前端

**B1. 红：扩充 `App.test.tsx` 中 `/projects/1` 的渲染期望**
- 不再 mock `/studies/grouping-batches/`（删除该 mock）。
- 验证看板渲染："患者池"（去掉"尚未加入本项目"措辞改为更简）+ "随机分组"按钮 + 至少一个分组列。
- mock 新 API：`/studies/projects/1/randomize/`、`reset-pending/`、`confirm-grouping/`。

**B2. 绿：改造 `ProjectGroupingBoard.tsx`**
- 状态：删除 `activeBatchId`、`batchMembers`、`pendingBatches`、`batchPending`；
- 列内显示：直接用 `projectPatients` 中 `group != null` 的所有行（含 pending + confirmed）；
- 池：保留过滤逻辑（剔除任意 ProjectPatient 中的 patient）；
- 「随机分组」按钮：`POST /projects/{id}/randomize/` 传 `pool_patient_ids`；
- 「取消随机」按钮：`POST /projects/{id}/reset-pending/`；空 pending 时按钮 disabled；
- 「确认分组」按钮：`POST /projects/{id}/confirm-grouping/`；项目里无 pending 时 disabled；
- 已 confirmed：opacity 0.72 + 不可拖（保留），新增更明显的视觉提示（如"已确认"Tag）；
- 列表卡片下保留「从本项目移除」按钮（confirmed 时显示）；
- 文案：将"患者池（尚未加入本项目）"改为"患者池（全部患者）"（用户问题 2：池只是表达全量），子标题继续解释。

**B3. 红：写 `ProjectGroupingBoard.test.tsx`（小型单测）**
- 渲染含 2 个 confirmed + 1 个 pending 的项目：
  - 3 张卡片都在列内显示；
  - confirmed 卡片显示「已确认」标签；
  - 池里不包含这 3 位患者。

**B4. 绿：调通 `ProjectGroupingBoard.tsx`**

**B5. 红：写 `EnrollProjectsModal.test.tsx`**
- 选项目 + 选组（按 project 联动 groups 列表）+ 点确认 → 调用 `POST /patients/{id}/enroll-projects/` payload `enrollments: [...]`。

**B6. 绿：改造 `EnrollProjectsModal.tsx`**
- 表格：每行 = 项目 + 该项目下的 group 下拉；
- 提交：构造 `enrollments` 数组；
- 文案：标题"直接确认入组到分组"或"快速入组"；说明文字调整。

**B7. 删除：`GroupingBatchPanel.tsx`、`ProjectPatientsTab.tsx`（均未挂载）**

**B8. 验证：`vitest run` 全绿**

---

### 阶段 C：文档清理

**C1. 更新 `specs/patient-rehab-system/`**
- 在已修改的 README/architecture/changelog 基础上补充：删除批次概念条目。
- 在新的 spec 章节中明确："不存在患者-项目绑定关系，除非确认入组"的术语定义。

**C2. 更新 `docs/superpowers/plans/2026-05-11-patient-project-admin-and-grouping-board.md`**：标注「已过时，被 2026-05-11-drop-batch-concept.md 替代」。

---

## 4. 验收准则

- [x] 后端 pytest 全绿（含 randomize/reset-pending/confirm-grouping/enroll-projects 测试）。*证据：`cd backend && pytest -q` → 0 failures。*
- [x] 前端 vitest 全绿（含 `EnrollProjectsModal` 与 `ProjectGroupingBoard` 测试）。*证据：`cd frontend && npm run test` → 0 failed（执行 consolidation 计划后应 ≥12 tests）。*
- [x] 应用代码（排除 `**/migrations/**`）内**无** `GroupingBatch` / `grouping_batch` / `grouping-batches` / `create_grouping_batch` / `discard-grouping-draft`。*证据：`rg` 仅命中 migrations。*
- [x] 前端 `ProjectGroupingBoard` 行为符合用户描述的 5 点反馈（池过滤、随机 API、撤销/确认、已确认置灰/标签、解绑入口）。*以代码审查 + 本文件阶段 B 为准。*
- [x] `enroll-projects` API 为「直接确认入组」`enrollments` 并通过测试。*见 `apps/patients/tests/test_enroll_projects.py` + `EnrollProjectsModal.test.tsx`。*

---

## 5. 风险与回退

- 删除 `ProjectPatient.grouping_batch` 字段是破坏性 schema 变更：开发库直接迁，生产暂未上线，无需保留兼容。
- 若 confirmed 的 ProjectPatient 与处方/CRF 有外键，删除流程已有保护（unbind 终止处方再删除）。
- 失败回退策略：每个阶段独立提交，回退到上一个 commit 即可恢复。
