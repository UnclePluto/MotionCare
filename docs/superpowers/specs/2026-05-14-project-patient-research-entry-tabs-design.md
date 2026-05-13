> 状态：approved
> 日期：2026-05-14
> 范围：研究录入改为项目患者维度列表与 T0/T1/T2 Tab 录入页；基线资料命名与入口重组；完成态访视只读。
> 关联：`docs/superpowers/specs/2026-05-08-crf-core-patient-fields-mapping-design.md`、`docs/superpowers/specs/2026-05-08-visit-assessments-and-baseline-flow-design.md`、`docs/superpowers/specs/2026-05-12-research-entry-crf-full-field-workbench-design.md`
> 实施基线 commit：e3797df

# 项目患者维度研究录入与基线资料设计

## 背景

当前「研究录入」页面以 `VisitRecord` 为列表实体，导致同一项目患者按 T0/T1/T2 拆成多行。医生的实际工作流是先定位「某患者在某研究项目中的录入任务」，再选择 T0/T1/T2 访视填写。因此本设计将研究录入的信息架构改为 `ProjectPatient` 维度。

同时，当前产品文案把人口学、手术史/过敏史、既往史/家族史、生活方式、基线用药等患者长期信息称作「CRF 基线」。这容易与 T0 基线评估混淆。本设计统一改称「基线资料」，页面标题为「患者基础基线资料」。

## 已确认决策

1. **研究录入列表一行等于一个 `ProjectPatient`**：同一患者参与两个项目时显示两行，按项目拆分。
2. **不做随访入口**：本期仅支持 T0 / T1 / T2。
3. **新增项目患者研究录入页**：路径为 `/research-entry/project-patients/:projectPatientId`，通过 query `visit=T0|T1|T2` 定位 Tab。
4. **完成态访视只读**：`status=completed` 的访视可以查看，不允许继续编辑；草稿态允许编辑和标记完成。该规则覆盖旧 PRD/旧设计中「已完成访视仍允许授权医生编辑」的口径。
5. **基线资料为患者维度一人一份**：继续使用 `PatientBaseline`，编辑覆盖最新值；CRF 生成时从 `patient.baseline` 读取。
6. **基线资料不包含 T0 评估**：身体机能、MoCA、筛选/访视类内容仍属于 T0 访视。
7. **患者详情去掉 CRF 入口**：CRF 更贴近项目语境，不再从患者详情的参与项目行直接打开。

## 目标

- 将「研究录入」列表从访视行改为项目患者行。
- 为每个项目患者提供独立录入页，顶部通过 T0/T1/T2 Tab 切换。
- 在 Tab 上展示访视状态，并在 Tab 内容顶部展示固定时间说明。
- 完成态只读，草稿态可编辑。
- 将现有「患者 CRF 基线信息」产品文案改为「患者基础基线资料」。
- 调整患者详情、项目详情、研究录入页中的入口关系，使 CRF 入口保留在项目相关语境。

## 非目标

- 不新增随访表单。
- 不改 `PatientBaseline` / `VisitRecord` 数据库结构。
- 不实现 T1/T2 时间窗校验；本期只展示时间说明。
- 不做电子签名、质控锁定流、完整审计日志。
- 不把基线资料做成按项目或按入组快照的版本化数据。

## 信息架构

### 研究录入列表

「研究录入」页面改为项目患者列表。主要列：

| 列 | 来源 | 说明 |
| --- | --- | --- |
| 患者 | `ProjectPatient.patient` | 显示患者姓名与手机号。 |
| 项目 | `ProjectPatient.project` | 显示项目名称。 |
| 分组 | `ProjectPatient.group` | 无分组时显示 `—`。 |
| 入组时间 | `ProjectPatient.enrolled_at` | 用于区分同患者多个项目。 |
| T0/T1/T2 | `VisitRecord` 摘要 | 显示草稿、已完成、访视未生成，以及访视日期。 |
| 操作 | 前端路由 | `录入`、`基线资料`。 |

交互：

- 点击 `录入`：进入 `/research-entry/project-patients/:id`，默认打开第一个未完成访视，顺序 T0 → T1 → T2；若三个都完成，则默认打开 T0 查看。
- 点击 T0/T1/T2 状态：进入同一页面并定位对应 Tab。
- 点击 `基线资料`：进入患者维度基线资料页。

### 项目患者研究录入页

页面结构：

1. 顶部摘要：患者姓名、项目名、分组、入组时间、项目状态。
2. 右上动作：`基线资料`、`打开 CRF`。
3. T0 / T1 / T2 Tab：每个 Tab 展示访视类型、状态、访视日期。
4. Tab 内顶部：固定时间说明。
5. Tab 表单：复用现有访视表单能力。

时间说明文案：

| Tab | 文案 |
| --- | --- |
| T0 | 筛选/入组节点；填写访视信息、知情同意、纳排、筛选结论，以及 T0 基线评估类字段。 |
| T1 | 干预 12 周节点；填写依从性、身体机能、MoCA、满意度、合并用药变化、不良事件等。 |
| T2 | 干预后 36 周节点；填写依从性、身体机能、MoCA、满意度、合并用药变化、不良事件、完成/退出与质控核查字段。 |

### 患者详情

- 顶部按钮：`基线资料`，进入患者维度基线资料页。
- 研究项目参与表：去掉 `打开 CRF`。
- 每个项目行提供 `研究录入`，进入对应 `ProjectPatient` 的研究录入页。

### 项目详情

- 项目详情、分组看板或组内患者卡片属于项目语境，应提供 `研究录入` 与 `打开 CRF`。
- `打开 CRF` 必须使用对应 `ProjectPatient`，与 `/crf?projectPatientId=` 一致。

## 数据与接口

### `ProjectPatient`

继续作为患者-项目-分组关系的唯一承载。现有 `/studies/project-patients/` 已返回 `visit_ids`，本期扩展为同时返回 `visit_summaries`，并保留 `visit_ids` 兼容旧调用。

响应片段：

```json
{
  "id": 9001,
  "project": 1,
  "project_name": "海南认知衰弱研究",
  "project_status": "active",
  "patient": 201,
  "patient_name": "张三",
  "patient_phone": "13800000000",
  "group": 10,
  "group_name": "试验组",
  "enrolled_at": "2026-05-12T10:00:00+08:00",
  "visit_ids": { "T0": 11, "T1": 12, "T2": 13 },
  "visit_summaries": {
    "T0": { "id": 11, "status": "completed", "visit_date": "2026-05-12" },
    "T1": { "id": 12, "status": "draft", "visit_date": null },
    "T2": { "id": 13, "status": "draft", "visit_date": null }
  }
}
```

列表筛选：

- 保留现有 `project`、`patient` 过滤。
- 增加 `patient_name` / `patient_phone` 过滤，供研究录入页查询使用。
- API 形状仍返回数组，前端可使用本地分页，避免破坏患者详情等现有调用。

### `VisitRecord`

继续使用现有接口：

- `GET /visits/:id/`：读取单个 Tab 的表单数据。
- `PATCH /visits/:id/`：保存草稿。
- `PATCH /visits/:id/ { "status": "completed" }`：草稿态标记完成。

规则变更：

- 当 `status=completed` 时，后端拒绝会修改 `form_data`、`visit_date`、`status` 等写入的请求，保证前后端一致只读；重复提交 `status=completed` 也拒绝，并且不产生写入副作用。
- 当项目状态为 `archived` 时，沿用现有项目完结只读规则。

### `PatientBaseline`

继续使用现有接口：

- `GET /patients/:id/baseline/`
- `PATCH /patients/:id/baseline/`

产品命名：

- 页面标题：`患者基础基线资料`。
- 入口按钮：`基线资料`。
- 不再使用 `CRF 基线` 作为用户可见文案。
- 保留现有 `/patients/:id/crf-baseline` 路由以兼容旧链接；用户可见文案必须按新命名展示。

CRF 聚合：

- `build_crf_preview(project_patient)` 继续从 `project_patient.patient.baseline` 读取基线资料。
- T0/T1/T2 评估和事件数据继续从对应 `VisitRecord` 读取。

## 前端组件边界

实现时将现有 `VisitFormPage` 中的表单主体拆为可复用组件：

- `VisitFormContent`：负责单条 `VisitRecord` 的加载、保存、标记完成、只读态、registry 字段渲染。
- `VisitFormPage`：保留旧 `/visits/:visitId` 入口，包一层 `VisitFormContent`，并采用完成态只读规则。
- `ProjectPatientResearchEntryPage`：加载 `ProjectPatient` 摘要，渲染 T0/T1/T2 Tabs，每个 Tab 内使用 `VisitFormContent`。
- `ResearchEntryPage`：改为项目患者列表。

这样可以减少重复实现，并让旧深链和新工作流共享同一套只读、保存、完成逻辑。

## 错误处理

- 项目患者不存在或无权限：展示 `记录不存在或无权限访问`。
- 某个访视缺失：列表对应状态显示 `访视未生成`；Tab 内展示可读错误，不跳转空表单。
- 某个 Tab 加载失败：只影响该 Tab，页面摘要和其他 Tab 保留。
- 已完成访视：前端表单只读，不显示可用的保存/标记完成动作；后端拒绝写入。
- 已完结项目：所有访视 Tab 只读，沿用当前已完结项目门控。
- 基线资料保存失败：沿用现有 registry 校验错误展示。

## 测试策略

### 后端

- `ProjectPatientSerializer` 返回 `project_name`、`project_status`、`visit_summaries`。
- `/studies/project-patients/` 支持 `patient_name` / `patient_phone` 过滤。
- 草稿访视 PATCH `form_data` 成功。
- 完成态访视 PATCH `form_data` 被拒绝。
- 完成态访视重复标记完成被拒绝，且不产生写入副作用。
- 已完结项目访视仍拒绝写入。
- CRF 聚合继续从 `PatientBaseline` 读取基线资料。

### 前端

- 研究录入列表按 `ProjectPatient` 展示，不再按访视行展示。
- 同一患者参与两个项目时显示两行。
- 点击 `录入` 打开第一个未完成 Tab。
- 点击 T1 状态打开 T1 Tab。
- 三个访视都完成时默认打开 T0 查看。
- 已完成 Tab 表单只读，保存和标记完成不可操作。
- 患者详情项目行没有 `打开 CRF`，有 `研究录入`。
- 项目语境入口可打开 CRF。
- 基线资料页标题为 `患者基础基线资料`。
- 用户可见文案中不再出现 `CRF 基线`。

## 验收点

1. 进入「研究录入」，同一患者参与两个项目时按项目显示两行。
2. 某项目患者 T0 已完成、T1 草稿、T2 草稿时，点击 `录入` 默认进入 T1。
3. 点击 T0 状态进入 T0 Tab，表单只读。
4. 在 T1 Tab 修改字段并保存草稿成功；标记完成后重新进入只读。
5. 患者详情的参与项目表不显示 `打开 CRF`，显示 `研究录入`。
6. 点击 `基线资料` 进入页面，标题为 `患者基础基线资料`。
7. CRF 预览仍能读取基线资料和 T0/T1/T2 访视数据。

## 兼容与风险

- 路由兼容：保留旧 `/visits/:visitId` 和 `/patients/:id/crf-baseline` 深链，避免外部链接失效；但用户可见文案按新设计展示。
- 规则覆盖：完成态只读会改变旧行为，实施时必须同步前后端测试，防止仅前端禁用但后端仍允许写入。
- 列表 API：为避免破坏患者详情现有数组调用，本期不强制把 `/studies/project-patients/` 改成分页响应；研究录入页可使用本地分页。
- 基线资料仍是患者最新值：若未来需要按项目导出入组时快照，需要另行设计版本化或快照机制。
