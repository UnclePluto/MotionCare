> 状态：approved  
> 日期：2026-05-12  
> 范围：患者 CRF 基线录入页（`/patients/:id/crf-baseline`）的预填、单选控件、「其他」备注、响应式双列、章节标题展示；**不含**访视表单内 CRF 的同类改造。  
> 关联：`docs/superpowers/specs/2026-05-12-research-entry-crf-full-field-workbench-design.md`、`specs/patient-rehab-system/crf/registry.v1.json`  
> 实施基线 commit：e37d8a4

---

## 1. 背景与目标

基线页已按 registry 动态渲染，但存在：未利用患者主档预填、单选题使用下拉、Collapse 标题仅为 Word 表号（如 `#T11`）、宽屏下列利用率低。本设计在**不改动访视侧 CRF 渲染**的前提下，仅优化基线录入页的录入体验与 registry 元数据，并与既有「registry 为字段真源」原则一致。

## 2. 范围与非目标

### 2.1 范围内

- 路由：`/patients/:patientId/crf-baseline`（`PatientCrfBaselinePage`）。
- Registry：`registry.v1.json`（或后续版本）根级与字段级**增量字段**；生成脚本与 docx 同源维护。
- 前端：基线页专用字段渲染（`single_choice` → Radio）、「其他」备注、节标题、响应式双列布局。
- 后端：baseline 写入校验扩展至新增 `other_remark_storage` 路径（与现有 registry 校验同源）。

### 2.2 范围外

- `/visits/:visitId` 内 CRF：继续使用现有 `renderVisitRegistryField` 与 `Select`，不在本期改为 Radio。
- CRF 导出版式、DOCX 像素级一致。
- 新建 `PatientPool` 实体、批次、随机语义变更（遵守 AGENTS 已冻结决策）。

## 3. 已确认决策（会话结论）

| 主题 | 决策 |
|------|------|
| 访视 CRF 是否同步改造 | **否**，仅基线页（选项 A）。 |
| 预填与已有 baseline | **仅填空**：主档只写入 baseline 中当前为空的 `storage` 路径，已有值不覆盖。 |
| 姓名缩写不足四位 | **右侧补 `X`** 至四位（全中心一致）。 |
| 姓名缩写超过四位 | **截断为四位**（取首字母序列前四个字符，大写）。 |
| 「其他」备注存储 | Registry **显式** `other_remark_storage`（完整 `storage` 路径）；校验在 registry 层表达。 |
| 双列布局 | **纯响应式**：达到约定最小宽度（建议 `min-width: 1200px`）时，每个 Collapse 节内字段两列；否则单列。 |

## 4. Registry 契约增量

### 4.1 `table_titles`（根级对象）

- 键：`table_ref`（如 `"#T8"`），与现有字段 `table_ref` 一致。
- 值：与 **CRF docx 章节表题**一致的中文标题（如「手术史与过敏史」「既往病史与家族史」），用于 Collapse 标签展示。
- 展示规则：`label = table_titles[table_ref] ?? table_ref`（缺映射时回退表号，避免空白）。
- 维护：与字段清单同源生成/校对脚本更新，禁止仅手改前端常量作为主真源。

### 4.2 `other_remark_storage`（字段级，可选）

- 适用：`widget === "single_choice"` 且 `options` 中含 **「其他」**（或与 docx 完全一致的「其他」文案）。
- 值：字符串，为 **完整** `storage` 路径，指向 `PatientBaseline` 下 JSON 中可持久化的键（如 `patient_baseline.demographics.ethnicity_other_remark`），须与现有 `demographics` / `surgery_allergy` 等分区一致，避免平铺冲突。
- 完整性：若该题 `required_for_complete === true` 且当前选中值为「其他」，则 **`other_remark_storage` 指向的值** 在「完整/导出缺失」语义下视为必填；非必填题则备注框仍展示，保存允许为空。

### 4.3 可选扩展

- `other_remark_widget`：`text` | `textarea`（默认 `text`），便于长说明字段。

## 5. 预填逻辑

### 5.1 数据来源与请求

- 并行请求已有接口：`GET /api/patients/{id}/` 与 `GET /api/patients/{id}/baseline/`（或当前基线页等价路径）。
- 不在本期强制扩展 `GET baseline` 合并主档（推荐保持 **方案 1：前端合并**）。

### 5.2 合并规则

- 将 baseline 反序列化为表单初值后，对「预填映射表」中每一对 `(patient 字段 → registry storage 路径)`：若 baseline 在该路径上为空（`null`、`undefined`、`""`、或对象树缺省），则写入推导值；否则跳过。
- 性别映射：`Patient.gender` 为 `male` → 「男」，`female` → 「女」；`unknown` **不预填** CRF 性别（避免与选项不一致）。
- 年龄 / 出生日期：优先使用主档已有 `age`、`birth_date`；与患者编辑页日期口径一致（周岁、ISO 日期字符串等按现有 API 约定）。
- **姓名缩写**（仅当 `name_initials` 为空时）：由 `Patient.name` 计算——拼音首字母、**大写**、不足四位 **右侧补 `X`**、超过四位 **截断为四位**；采用拼音库默认读音，**允许用户在表单中修改**（不锁定自动值）。

## 6. 基线页 UI 行为

### 6.1 `single_choice`

- 仅基线页：使用 `Radio.Group` 展示全部选项，**不使用** `Select`。
- 选中「其他」且存在 `other_remark_storage`：显示备注输入控件；失焦/提交行为遵循 Ant Design Form 常规。

### 6.2 布局

- 每个 Collapse 面板内容区使用 CSS Grid（或等价）实现双列；断点以下单列。
- 可适当放宽表单 `maxWidth`（相对当前约 880px），以宽屏下可读为准，不与 `AdminLayout` 冲突。

### 6.3 实现边界

- 基线专用渲染函数与访视共用类型定义（`RegistryField` 等）即可；**不得**改变 `renderVisitRegistryField` 的 `single_choice` 为 Radio，除非未来单独 spec。

## 7. 校验与测试

- **后端**：registry 驱动的 baseline patch 校验需覆盖：选「其他」且该题纳入完整性强提示时，备注路径非空。
- **前端**：单元测试建议覆盖——缩写计算（补 `X`、截断）、预填不覆盖已有值、Radio+其他显隐、断点下列数变化（可用 jsdom + 窗口宽度 mock 或组件级逻辑纯函数测试）。

## 8. 自检记录

- 占位：无 TBD。
- 一致性：与 `2026-05-12-research-entry-crf-full-field-workbench-design.md` 的 registry 真源、baseline API 一致；访视侧明确排除。
- 范围：单页 + registry + 校验扩展，可放入一份 implementation plan。
- 歧义：「其他」文案以 docx/registry `options` 中字面为准；若存在「其它」等异体，实施时以 registry 为准或统一生成脚本。

---

## 9. 后续步骤

实施前由本 spec 派生 `docs/superpowers/plans/` 下 implementation plan（`writing-plans` 工作流）；实施完成后在本文件头部补充「实施基线 commit」短 SHA。
