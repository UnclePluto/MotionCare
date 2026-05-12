> 状态：approved  
> 日期：2026-05-12  
> 范围：研究录入工作台（访视列表 + 患者 CRF 基线），字段一次性对齐 CRF Word 模板；不实现导出版式像素级一致。  
> CRF 真源（唯一）：`docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx`  
> 关联：`docs/superpowers/specs/2026-05-08-crf-core-patient-fields-mapping-design.md`、`docs/superpowers/specs/2026-05-08-visit-assessments-and-baseline-flow-design.md`、`specs/patient-rehab-system/prd.md`  
> 实施基线 commit：`0461689`

---

## 1. 背景与目标

### 1.1 临床操作链（用户确认）

挂号建档 → 医生录入信息 → 将患者分配到某研究项目的分组 → **T0 基线评估** → 开具处方 → 绑定穿戴设备 → 随访或到期到院 **T1 / T2** → 汇总数据与后续图表。

### 1.2 目标

- 提供**单一主导航入口**的「**研究录入工作台**」，满足偏 **B** 的诉求：以**访视工作列表**为主轴，在同一工作面内可完成**患者 CRF 固化段**与 **T0/T1/T2 访视段**录入。
- **一次性到位**：首版即覆盖 CRF 模板中与一期 Web 录入相关的**全部表格字段**（见第 3 节范围），录入控件、选项、必填规则与 **Word 模板修订稿**一致；允许缺失保存，但**校验规则与 CRF 缺失提示**必须与 registry 同源，避免「录了却导出仍报缺」的双口径。
- **不回归**已冻结决策：`Patient` 全局档案、`PatientBaseline` 固化 + `VisitRecord.form_data` 访视增量、无批次、随机语义维持现状；不在本期新建 `PatientPool` 实体。

### 1.3 非目标（本期不改）

- CRF **DOCX/PDF 版式**像素级还原与自动生成版式导出（仍遵循 PRD 第 13 章既有边界）。
- 电子签名、质控锁定流、基线版本化（仍为一期「只保留最新值」策略）。
- 基于训练完成度的自动算分写入 `computed_assessments`（契约保留，算法不接）。

---

## 2. 信息架构与路由

### 2.1 侧栏

在管理端侧栏新增一项，建议文案：**「研究录入」**（与「CRF 报告」区分：后者偏汇总预览/导出，前者偏一线录入）。

### 2.2 路由与页面结构

- 主路由建议：`/research-entry`（名称可实施时微调，需全局唯一）。
- 页面为**工作台布局**（推荐上下或左右分栏，实施时选一种即可）：
  1. **访视工作列表**：分页表格；筛选条件至少包含：研究项目、访视类型（T0/T1/T2）、状态（草稿/已完成）、患者检索（姓名/手机号，遵守与患者列表一致的**隐私与后端过滤**规则）。
  2. **行操作**：「访视录入」→ 进入现有 `/visits/:visitId` 的**增强版**表单（或工作台内嵌同组件，路由二选一，以复用为优先）。
  3. **同一患者的 CRF 基线**：行内「患者基线」或列表列快捷入口 → 打开 **患者 CRF 基线表单**（数据源 `GET/PATCH /api/patients/{id}/baseline/`，见第 4 节）。支持从患者搜索进入（未入组患者仅有基线、无访视行时仍可录基线）。
- **保留**现有路径：项目详情 → 患者 Tab → T0/T1/T2 链接；工作台为**新增主入口**，不删除旧入口。

### 2.3 权限与数据范围

- 沿用 `IsAdminOrDoctor` 与既有**行级**过滤约定：医生仅能看到自己权限范围内的患者/项目/访视；列表 API 必须在后端完成过滤，前端只做 UX。

---

## 3. CRF 真源、registry 与「一次性到位」范围

### 3.1 Word 模板位置（已确认，无其它模板）

**唯一字段真源**：`docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx`。  
**实施前条件**：从该文件（或经签核的、与该文件逐格一致的导出表）生成 **registry**；禁止仅依赖口头描述或过时截图。  
若仓库内 `backend/config/settings.py` 的 `CRF_TEMPLATE_PATH` 默认值仍指向其它路径，实施时须改为与本路径一致（或通过环境变量覆盖为上述文件）。

### 3.2 模板版本

- 在 registry 根节点声明 `template_id` + `template_revision`（与 Word 文件名/修订记录或封面上版本号对齐）。
- `PatientBaseline` 与 `VisitRecord.form_data` 不强制逐条存版本号；**CRF 导出日志**（若已有）继续记录导出时模板版本；录入侧在「关于本表单」或开发模式下可读 registry 版本，便于排错。

### 3.3 Registry 资产（单一真源）

- 在仓库内新增**机器可读**清单（建议：`specs/patient-rehab-system/crf/registry.v1.yaml`，版本 bump 时 `v2`…），每条字段至少包含：
  - `table_ref`：与 Word 内表编号一致（如 `#T8`…`#T30`）。
  - `field_id`：稳定英文 snake_case，全局唯一。
  - `label_zh`：与 Word 题干一致（含单位说明可放 `hint`）。
  - `widget`：`text` | `number` | `single_choice` | `multi_choice` | `date` | `textarea` | `table_repeat`（多行子表）等。
  - `options`：选择题选项，顺序与 Word 一致。
  - `storage`：`patient_baseline.demographics.xxx` 或 `visit.form_data.crf.xxx` 等明确路径。
  - `required_for_complete`：是否纳入「完整性/导出缺失」强提示（可与 PRD 缺失导出规则区分：允许空保存，但列表可标「未完整」）。
  - `visit_types`：若为访视字段，标注适用 `T0`/`T1`/`T2`（与 Word 中该表出现节点一致）。

### 3.4 一次性覆盖的表集合（与 2026-05-08 mapping 设计对齐）

以下表号集合为**首版必须**在 registry 中落满字段定义并在前后端接线的最小集合（若 Word 另有仅质控、无临床值的表，仍按 Word 控件录入，导出可空）：

| 归属 | Word 表号（示例，以 docx 为准） | 存储 |
|------|----------------------------------|------|
| 患者固化 | `#T8` 人口学 | `PatientBaseline.demographics` |
| 患者固化 | `#T9` 手术史/过敏史 | `PatientBaseline.surgery_allergy` |
| 患者固化 | `#T10` 既往病史与家族史 | `PatientBaseline.comorbidities` |
| 患者固化 | `#T11` 行为习惯史 | `PatientBaseline.lifestyle` |
| 患者固化 | `#T12` 基线用药 | `PatientBaseline.baseline_medications`（注意 ORM 字段名，非 `medications`） |
| 访视增量 | `#T13/#T17/#T24` 身体机能等 | `VisitRecord.form_data` 内与机能相关子树（与现有 `assessments` 对齐或迁移映射见 4.2） |
| 访视增量 | `#T14/#T18/#T25` MoCA 分项与总分 | 同上，**补全分项**，不得仅录总分 |
| 访视增量 | `#T16/#T23` 依从性 | `form_data` 内独立子树 |
| 访视增量 | `#T19/#T26` 满意度 | 同上 |
| 访视增量 | `#T20/#T27` 合并用药变化 | 同上 |
| 访视增量 | `#T21/#T28` 不良事件 | 同上 |
| 访视增量 | `#T29` 完成/退出 | 同上 |
| 访视/封面信息 | `#T0`、`#T3/#T15/#T22` 等识别与访视信息 | 能落在 `PatientBaseline` 的进 baseline；属单次访视语境的进对应 `VisitRecord`（如访视日期已与模型字段 `visit_date` 对齐则复用，其余进 `form_data.crf.meta` 等约定路径） |
| 质控类 | `#T30` | 仅录入、一期不启流程锁，字段仍进 `form_data` 约定路径 |

若 Word 修订稿与上表编号有出入，**以 docx 为准**并更新本 spec 附录表号对照表（实施 PR 中附录一次性更新即可）。

---

## 4. 数据模型与 API 契约

### 4.1 患者基线（已有模型）

- 继续使用 `PatientBaseline` 五段 JSON + `subject_id` / `name_initials`。
- 所有 `#T8`–`#T12` 字段通过 registry 映射到上述键；**禁止**在前端硬编码一套与 registry 分叉的中文 key。

### 4.2 访视 `form_data` 结构（扩展现有契约）

在保留现有键的前提下扩展（与 `2026-05-08-visit-assessments-and-baseline-flow-design.md` 兼容）：

- `assessments`：继续承载机能与 MoCA 等**已存在**路径；新增字段优先**嵌套**在既有对象内（如 `moca.subscores`）或通过 registry 明确的新增 key，避免破坏已有测试与 CRF 聚合读取路径。
- `computed_assessments`：仍仅服务端写入；外部 PATCH 丢弃。
- **新增**统一命名空间 `crf`（建议名）：承载 `#T16`–`#T30` 及不适于放在 `assessments` 的表格化结构；内部按 `table_ref` 分子对象或数组，**具体树形以 registry 的 `storage` 为准**。

### 4.3 关键：PATCH 合并语义（当前实现缺口）

现状：`VisitRecordSerializer.update` 仅对 `form_data.assessments` 做 deep merge，**其余 `form_data` 顶层键在 PATCH 中会被忽略**。  
**本期必须修复**：对所有允许由客户端 PATCH 的 `form_data` 键（至少 `assessments` 与 `crf` 全树，及 registry 声明的其它可写顶层键）采用与 `assessments` 相同的 **deep partial merge**；`computed_assessments` 仍不可由客户端覆盖。  
该修复须有**回归测试**（PATCH 仅带 `crf` 时不丢失 `assessments`；反之亦然）。

### 4.4 校验

- **后端**：根据 registry 做类型、枚举、范围校验；未知字段：若 registry 未声明且不在「允许扩展」白名单，则 400 或剥离（实施时二选一并写清，推荐**剥离 + 日志**以免 docx 微调导致线上保存失败）。
- **前端**：由 registry 生成默认值与控件校验，与后端一致；提交前可做轻量提示，**最终以服务端为准**。

### 4.5 列表 API

- `GET /api/visits/`：增加 `django-filter`（或等价）支持 `project_patient`、`visit_type`、`status`、患者姓名/手机（通过 `project_patient__patient`）、项目 ID；分页默认按 `visit_date` 空值置后或按 `-updated_at`，具体排序在实施计划中定稿。
- 列表序列化：返回嵌套只读字段（患者展示名、手机号展示规则、项目名称、访视类型、状态），避免 N+1。

---

## 5. 前端形态

- **工作台**：Ant Design `Table` + `Filter`；移动端非目标。
- **基线表单**：按 registry 的 `table_ref` 分 `Collapse`/`Tabs`；长表用 `table_repeat` 渲染子表。
- **访视表单**：在 `VisitFormPage` 上扩展为「机能评估 + CRF 访视各表」多块；字段顺序与分组与 Word 表顺序一致（registry 可带 `display_order`）。
- **性能**：首屏可懒加载「非当前 Tab」块；一次性字段多，注意 bundle 与表单分块。

---

## 6. CRF 聚合与缺失字段

- `apps/crf/services/aggregate.py`（及关联测试）必须改为**读取 registry** 或与 registry 同步生成的**单一必填规则源**，使：
  - 工作台「完整性」标识、
  - CRF 预览 `missing_fields`、  
  使用同一套 `required_for_complete` 定义。
- 现有仅校验 `education_years`、SPPB/MoCA 总分的逻辑，扩展为 registry 驱动；**禁止**在 aggregate 内再维护一份与 registry 冲突的硬编码列表。

---

## 7. 测试与验收

- **后端**：`PATCH` 合并、`crf` 校验、列表过滤权限、registry 抽样字段 round-trip。
- **前端**：工作台渲染、筛选、跳转访视与基线；关键表单组件快照或 RTL 冒烟。
- **验收**：持修订稿 Word，逐表抽样对照：标签、选项、顺序、必填行为一致；CRF 预览缺失项与未填控件一致。

---

## 8. 风险与依赖

- **docx 未在 git 中**：阻塞 registry 定稿；须先入库或提供受控副本并完成字段提取签核。
- **工作量**：一次性全表字段开发与联调量大；通过 registry 驱动可降低重复劳动，但首版仍需大量 UI 绑定与边界用例。
- **MoCA 分项**：与现「仅 total」页面对比，属**行为扩展**，需在实施计划中列出对旧数据的兼容（旧数据无分项则显示空）。

---

## 9. 结论

批准实施「**研究录入工作台（B2）+ CRF registry 全量字段一次性到位**」方案：新增主导航与列表能力，扩展 `PatientBaseline` 与 `VisitRecord.form_data` 的录入与校验，并**修复访视 `form_data` PATCH 仅合并 assessments 的缺陷**，使 CRF Word 模板成为通过 registry 可追溯的唯一字段真源。

---

## 附录 A：与既有设计不一致处的处理

- `2026-05-08-crf-core-patient-fields-mapping-design.md` 文中写 `#T12 → PatientBaseline.medications.*`：以 ORM 实际字段 **`baseline_medications`** 为准；registry 的 `storage` 路径与之对齐。

待你审阅本文件后，若无修改意见，下一步由 **`writing-plans`** 产出实施计划（含 registry 提取任务、API、前后端、CRF 聚合、测试拆分顺序）。
