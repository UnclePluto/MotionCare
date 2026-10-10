# CRF 全字段结构化录入与导出修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 状态：implemented（实施与验收完成，待发布；未提交、推送或上线）  
> 日期：2026-10-08  
> 执行记录（2026-10-08，Codex）：Task1代码、独立审查及隔离镜像实测通过；Task2基线字段、源清单及一次修复复审通过；Task3全561来源合约及一次修复复审通过；Task4校验及重复行修复复审通过；未提交，基线1f74936。  
> 实施基线：`1f7493664223c8fd65a1b4d3139c08a8b12579d9`  
> 执行记录（2026-10-09，Codex）：Task 5 已实施并经两轮定向复审通过，基线 1f74936，改动未提交；Task 6 共享控件及一轮定向复审通过；Task 7 重复明细及矩阵经独立审查通过；Task 8 页面接线及错误兜底一轮复审通过；Task 9 完整性/预览及一轮复审通过；Task 10 原表回填及一轮复审通过；Task 11 双格式导出、真实超时清理及一轮复审通过；Task 12 固定依赖、真实API/最终镜像及独立规格质量审查通过（后端初轮1892/1，受影响部署13复验通过）；Task 13 浏览器、254页视觉及独立规格质量审查通过（143/78/17），最终整体审查及唯一修复复审已执行，I2历史数组父容器缺项判断仍未关闭；未提交发布。
> 最终执行记录（2026-10-09，Codex）：用户“继续吧”授权的追加I2修复限3前端文件，独立范围复审全部关闭，无新增C/I/M；前端全套54文件473项、46组实际前后端完整性及8组父容器issues一致。控制器独立复核378后端/156前端输入与最终API/Web及实际HTTP产物一致；20文档356页证据为23直接观察/333逐页字节复用。北京时间20:20只读线上仍1f74936，发布步骤保持未勾选。  
> 用户意见：采用方案 B；去掉字段旁常驻长说明、来源表号及技术文案，保留必要标签、单位、选项、校验和反馈输入。

**Goal:** 补齐原 CRF 每个填写位置的结构化录入、保存、回读和导出，修复已确认的线上资产缺失、完成时数据丢失与校验/完整性缺陷。

**Architecture:** 保留 `PatientBaseline` 五段 JSON、`VisitRecord.visit_date` 和 `form_data.assessments/crf`。同一 registry 定义字段、选项、条件、数值规则及原表位置；前端以章节、量表矩阵和重复明细组织 AntD 控件，后端共享校验与完整性求值，预览和 DOCX/PDF 消费同一聚合结果。

**Tech Stack:** Python 3.12、Django 5、DRF、PostgreSQL 16、React 18、TypeScript、Node 20、Ant Design 5、Vitest、pytest-django、python-docx；PDF 使用产品镜像内的 LibreOffice Writer 和中文字体。

**Spec:** `docs/superpowers/specs/2026-10-08-crf-full-field-structured-entry-and-export-design.md`（approved）。

## Global Constraints

- 唯一原表：`docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx`，SHA-256 `f031dd59a1e169548fe651555d19c41306cc51e6bfcf7eb933edcee86924102a`；31表、265行、561个原语义填写位置。
- `schema_revision: 2` 描述扩展后的数据合约；`template_revision: "1.1"` 描述原 CRF。不可用项目旧配置冒充实际文件版本。
- 不改变全局患者、最新基线、分组、处方、解绑及 `computed_assessments` 的冻结语义；不读取穿戴健康数据。
- 缺失允许保存、完成和导出；完成状态与填报完整性分别展示。非法的新输入仍返回字段错误。
- 不新建答案数据库模型，不改受控源DOCX，不增加电子签名或质控锁定流程。
- 一般说明不常驻展示：不把 `hint` 拼到标签，不展示 `#Tn`、`registry`、`storage`、原文记录说明或重复章节介绍。保留简短 `ui_label`、单位、选项、必要判定条件、错误和反馈输入。
- 原文本和旧标量不得被新的对象/数组原地覆盖；不猜测其结构化含义。历史未改字段的问题以核对提示呈现，不能阻止无关章节暂存。
- 所有修改沿用实际鉴权/行级策略，保留已完成及归档的既有写保护；创建入口不能绕过校验。
- 使用隔离的 Python 3.12/PostgreSQL 16/Node 20 验收环境，不升级现有开发虚拟环境，不在生产制造测试病例。
- 用户未授权自动提交、推送或发布。每任务完成后只记录结果和勾选；提交命令不作为默认步骤。分支/隔离环境在计划执行阶段按 `using-git-worktrees` 处理。
- 沟通、提交说明及计划执行记录使用简体中文；既有 spec、plan 和变更历史不删除。

## Review Focus

1. 旧数据节点是字符串或非法旧分数：打开仍可查看；编辑其他章节不会丢原值或因无关历史问题失败。Task 4/5/8覆盖。
2. 更新输入后立即完成，或后台重取数据恰好到达：当前值必须保留并与完成状态一起保存，不能被旧响应覆盖。Task 8覆盖。
3. 重复行删除、移动、清空后，未知原因或备注不能错配到另一条事件，纸面容量之外的数据不能截断。Task 7/10覆盖。
4. 非汉/黎/苗的既有民族值、年月日期及部分未知日期：源值不能被错误改成“其他”或虚构的完整日期；纸面表达仍准确。Task 2/6/10覆盖。
5. 直接按项目患者主键预览/导出、伪造访视类型或转移记录到归档项目：沿用权限和写保护，不能从新流程绕过。Task 5/11覆盖。

## 文件职责

- `scripts/crf_registry/`：按原表章节维护字段定义及来源绑定；`scripts/build_crf_registry_v1.py` 为确定性生成入口，保留现有调用方式。
- `specs/patient-rehab-system/crf/registry.v1.json`：前后端合约；`source_slots.v1.json`：独立原填写位清单；前端副本从 canonical JSON 同步。
- `backend/apps/crf/field_values.py`、`field_rules.py`、`completeness.py`：分别负责取值/状态、类型与跨字段规则、完整性统计；`registry_validate.py` 保留现有公开校验函数。
- `frontend/src/crf/components/`：通用控件、部分日期、重复明细、选择矩阵；`CrfSectionForm` 消费 registry；各页面只负责请求、上下文及提交。
- `backend/apps/crf/services/docx_binding.py`、`export_pdf.py`：按格回填及转换；既有聚合、导出服务/API 负责取数据和持久化日志。
- 页面、接口路径、已用标量存储路径保留；针对本任务拆分过大的字段生成/渲染逻辑，不做无关重构。

---

### Task 1：补入生产字段资产，并建立启动/构建检查

**Files:** Modify `backend/Dockerfile`, `backend/apps/crf/registry_loader.py`, `backend/config/settings.py`; Create `backend/apps/crf/checks.py`, `backend/apps/crf/management/commands/check_crf_assets.py`; Test `backend/apps/crf/tests/test_crf_assets.py`。

**Interfaces:** `check_crf_assets(*, registry_path: Path | None = None, template_path: Path | None = None) -> dict` 返回 `template_revision`、registry/template哈希及文件存在性；缺失或版本/源哈希不符抛 `CrfAssetError`。纯资产检查不连接数据库。`load_crf_registry(force_reload=False)` 保留签名。

- [x] 写失败用例 `test_missing_registry_identifies_exact_path`、`test_runtime_assets_load_without_database`：缺文件须指出路径，正常资产能加载且两项纯校验不抛错；`assert validate_patient_baseline_payload({"subject_id": "MC-ASSET-CHECK"}) == {}`。
- [x] 运行 `cd backend && pytest apps/crf/tests/test_crf_assets.py -q`，记录当前失败。
- [x] Dockerfile复制 CRF资产目录到 `/app/specs/patient-rehab-system/crf/`；实现检查命令和 Django 系统检查，构建时在 `/app/backend` 验证资源可读。
- [x] 运行上述测试和 `python manage.py check_crf_assets`；正常镜像无数据库校验退出0；一次性容器删除registry后启动退出1，明确资产绝对路径（镜像sha256:f48ef2f8；最终完整镜像仍由Task12验收）。

### Task 2：确定源填写位合约，补齐基线和文档字段

**Files:** Modify `scripts/build_crf_registry_v1.py`, `specs/patient-rehab-system/crf/registry.v1.json`; Create `scripts/crf_registry/{__init__,schema,source_slots,baseline_fields}.py`, `specs/patient-rehab-system/crf/source_slots.v1.json`; Test `backend/apps/crf/tests/test_registry_source_coverage.py`。

**Interfaces:** `build_baseline_fields() -> list[dict]`；`build_source_slots(document_path: Path) -> dict` 返回 `source_sha256`、`table_count`、`row_count` 和 `slots`；`validate_registry_contract(registry: dict, source_slots: dict) -> list[str]`。每个原位置有稳定ID `T{table:02d}.R{row:02d}.S{slot:02d}`、标签、零起始格位置/填写位顺序、选项及访视上下文；来源清单不从已实现字段反推。

- [x] 写失败用例 `test_source_manifest_covers_all_561_original_slots`（`assert (manifest["table_count"], manifest["row_count"], len(manifest["slots"])) == (31, 265, 561)`、固定源哈希）和 `test_baseline_source_slots_have_writable_bindings`；删除任一来源绑定时后者须失败。
- [x] 运行这两项测试，确认现状未覆盖的源位置失败；静态格不作为填写位。
- [x] 补齐 #T0/#T1 与 #T8–#T12 的所有位置；保留现有编号、缩写和可复用的标量路径。病史补患病人数/备注、月份精度和痛风次数/处理；用药选项按原表多选。旧民族56项下拉继续兼容，原表非三民族回填“其他＋具体民族”，不篡改旧存储值。
- [x] 将与旧文本冲突的明细放到 `surgery_allergy.surgery_records`/`allergy_records`、`lifestyle.activity_record` 等新节点；未知状态统一落到设计指定的 metadata。生成原始填写位清单和 registry，并确保再次生成字节一致。
- [x] 运行源覆盖测试中的基线/文档部分和 `pytest apps/crf/tests/test_registry_baseline_layout.py -q`；检查原表原有各选项及其他说明都有独立提交位置。

### Task 3：补齐各访视及反馈字段和原表绑定

**Files:** Create `scripts/crf_registry/visit_fields.py`; Modify `scripts/build_crf_registry_v1.py`, `scripts/validate_baseline_registry_layout.py`, `specs/patient-rehab-system/crf/registry.v1.json`; Test `backend/apps/crf/tests/test_registry_source_coverage.py`, `test_registry_visit_contract.py`。

**Interfaces:** `build_visit_fields() -> list[dict]`；每条字段包含 `source_positions`、`section`、`ui_label`、`widget`、`storage`、`visit_types`、`validation`、`visible_when`、`required_when`；`table_repeat.children` 使用列的相对路径。条件采用 `all/any` 和 `eq/ne/in/present/contains`，只求值受控数据，不执行表达式。

- [x] 写失败用例 `test_every_original_slot_has_a_renderable_and_exportable_binding`，断言原位置均绑定到字段或明确组合、没有重复歧义，`assert validate_registry_contract(registry, manifest) == []`；`test_t1_t2_bindings_target_their_own_tables` 断言访视日期表为3/15/22，身体机能13/17/24，MoCA14/18/25，反馈对应原表。
- [x] 运行 `pytest apps/crf/tests/test_registry_source_coverage.py apps/crf/tests/test_registry_visit_contract.py -q`，确认当前合并文本和错索引失败。
- [x] 按批准设计§5补齐全部访视细项，保留现有 `assessments.sppb/moca/tug_seconds/grip_strength_kg/frailty` 标量；新增原始测量放相应子树。筛选结构使用 `crf.screening.icf_record/inclusion_items/exclusion_items/enrollment_record`；访视信息使用 `crf.meta`，保留原 `screening.*` 文本。
- [x] 满意度采用设计§8的 `crf.satisfaction.items.*.{score,remark}`、`overall_score`、`total`；依从性拆次数/分钟/原因/处理；用药变化和不良事件在原对象增加 `has_changes/has_events`、`entries`，不覆盖旧 `note`；完成/质控使用 `completion_record/qc_record`。提前退出适用T0/T1/T2，汇总原#T29。
- [x] 将3项SPPB的0–4/总分0–12、MoCA的5/3/6/3/2/5/6及修正0–1/总分0–30、满意度1–5/总分5–25等规则写入合约。普通可选备注不强迫填写；被选择触发的原因和明细参与完整性。
- [x] 运行两组完整覆盖测试；逐表核对561个绑定，不把新增备注替代原位置；确定性生成后同步前端副本，旧生成入口不再把新字段覆盖回187条。

### Task 4：实现类型、状态、日期及跨字段校验

**Files:** Create `backend/apps/crf/{field_values,field_rules}.py`; Modify `backend/apps/crf/registry_validate.py`; Test `backend/apps/crf/tests/test_registry_validate.py`, `test_crf_field_rules.py`, `test_registry_baseline_layout.py`（月份错误文案对齐，仍断言非法输入拒绝与原路径）。

**Interfaces:** `get_field_value(data: dict, field: dict) -> object`；`evaluate_condition(condition: dict | None, data: dict) -> bool`；`validate_fields(registry: dict, data: dict, *, scope: str, visit_type: str | None, changed_paths: set[str] | None = None, baseline: dict | None = None) -> dict[str,str]`。公开的 `validate_patient_baseline_payload(data)` 与 `validate_visit_form_data_patch(data, visit_type)` 保持原返回形态，可扩展可选上下文参数。

- [x] 写参数化失败用例：SPPB -1/4.5/6、MoCA31或非法分项/修正、满意度0/6、175%完成率、布尔/NaN/无穷、非法枚举、`2026-02-31`；合法0及边界值通过。例如：`assert "assessments.sppb.balance" in validate_visit_form_data_patch({"assessments":{"sppb":{"balance":4.5}}}, "T0")`。
- [x] 写 `test_totals_checked_only_when_prerequisites_present`、`test_unknown_reason_is_not_a_numeric_score`、`test_month_and_partial_dates_preserve_precision`；原始值缺失不能被当0求合计，已知非法日期不能靠未知状态掩盖。
- [x] 运行 `pytest apps/crf/tests/test_registry_validate.py apps/crf/tests/test_crf_field_rules.py -q`，确认现状边界失败。
- [x] 实现递归列校验、metadata与部分日期检查；新改动和受影响依赖执行硬校验，未改历史非法值成为核对问题。SPPB、MoCA、满意度、最快步行和最大握力按设计核对；不推断临床阈值、时间窗或完成率口径。
- [x] 同一组测试通过；对旧字符串节点、无分项旧总分、旧完整日期也有明确的兼容测试，禁止猜测迁移。

### Task 5：修复原子保存、部分合并和所有写入口

**Files:** Modify `backend/apps/crf/field_values.py`, `backend/apps/crf/registry_validate.py`（保存前历史结构保护）, `backend/apps/crf/field_rules.py`（实际不存在的部分日期识别接线修复）, `backend/apps/patients/serializers.py`, `backend/apps/patients/views.py`（现有baseline动作事务内锁定入口）, `backend/apps/visits/serializers.py`, `backend/apps/visits/views.py`, `backend/apps/training/services.py`, `backend/apps/training/sets.py`, `backend/apps/prescriptions/services.py`, `backend/apps/prescriptions/cutover.py`（共享项目/绑定锁顺序接线，调用方保留权限、归档与业务判断）; Create `backend/apps/studies/locking.py`; Test `backend/apps/crf/tests/test_crf_field_rules.py`（共享规则聚焦回归）, `backend/apps/patients/tests/test_patient_baseline_api.py`, `backend/apps/visits/tests/{test_visit_form_data_contract,test_status_transition,test_shared_project_patient_locks}.py`。

**Interfaces:** 在 `field_values.py` 定义 `merge_crf_patch(current: dict, patch: dict) -> dict`：对象递归、数组替换、`null`明确清除、未提交键保留。serializer校验合并后的候选数据，校验/保存和完成状态为同一操作；基线取值通过现有权限接口。CREATE与PATCH共享registry规则。

- [x] 写失败用例：基线仅改教育年限保留性别/民族；访视只改原因保留量表；`[]`清空明细、`null`清空值；新建非法字段同样400；完成同时保存日期/反馈且非法输入整次回滚；`assert merge_crf_patch({"a": {"b": 0, "c": 2}}, {"a": {"c": None}}) == {"a": {"b": 0, "c": None}}`。
- [x] 写 `test_cannot_move_or_create_visit_into_archived_project`、`test_visit_type_change_cannot_escape_validation`，保留已完成只读和服务端computed不可改用例。
- [x] 运行两目录相关API测试，记录失败点。
- [x] 为基线增加deep merge；访视校验解析当前/目标访视上下文，所有写入口检查归档/权限；保存前锁定或在事务内以当前记录合并，避免把候选数据基于旧记录直接覆盖。
- [x] 运行 `pytest apps/patients/tests/test_patient_baseline_api.py apps/visits/tests -q`；断言所有失败请求均未改变持久化值或状态。

### Task 6：建立共享前端控件、值转换及精简文字

**Files:** Modify `frontend/src/crf/types.ts`, `renderRegistryFields.tsx`, `renderBaselineRegistryFields.tsx`, `visitFormPaths.ts`; Reuse `frontend/src/crf/baselineFormPaths.ts`（既有基线相对路径契约已满足，无需无行为改动）; Create `frontend/src/crf/{fieldState,formValues,fieldCalculations}.ts`, `components/CrfField.tsx`, `components/CrfDateField.tsx`; Test `frontend/src/crf/{fieldState,formValues,fieldCalculations}.test.ts`, `components/CrfField.test.tsx`。

**Interfaces:** `CrfField({field, name, disabled?})`；`CrfDateField({field,name,disabled?})`；`normalizeCrfFormValues(values: Record<string,unknown>): Record<string,unknown>`；`buildCrfPatch(before: Record<string,unknown>, after: Record<string,unknown>): Record<string,unknown>` 明确保留清除值及数组。在 `fieldCalculations.ts` 定义 `calculateCrfDerivedValue(kind: "sppb_total" | "moca_total" | "satisfaction_total" | "fastest_walk" | "maximum_grip" | "count_ratio" | "time_ratio", values: Record<string,unknown>): number | null`；缺前提返回null。`visit_date`不再被storage映射丢掉；数值和状态metadata保持分离。

- [x] 写输入/回读测试：Radio/Select/多选、0、清空为null、月份只提交年月、未知日期有状态/原因，原值日精度未改动时不自动截断；`expect(buildCrfPatch({score: 0}, {score: null})).toEqual({score: null})`。控件保留真实数据字段，同时不渲染“原文记录/registry/#T13”等常驻说明。
- [x] 运行 `cd frontend && npm run test -- src/crf`，确认当前缺多选、月份和状态等失败。
- [x] 扩展类型并实现控件：短选项Radio，长选项搜索Select，多选Checkbox/Select，带单位及范围的InputNumber；日期表单store保持原始字符串，只在组件展示层转Dayjs，用户修改后再输出该字段精度。标签使用 `ui_label ?? label_zh`，不拼接hint。
- [x] 仅在需要填写时出现原因输入；普通选择未选、测量未录均不默认否或0。短提示只用于必要错误、单位和关键判断条件；反馈字段不因删说明而被删掉。
- [x] 实现及测试“使用计算结果”的显式操作；三项SPPB为4/3/2时计算9，五题满意度5/4/5/4/5时计算23，MoCA按 `min(30, 分项和+修正)`，最快步行取min，最大握力取max；缺前提或0分母返回null。次数/时长比值分别展示，不擅自替换原完成率。
- [x] 运行本任务测试、`npm run lint`及类型构建；确认清除、0和部分日期均实际进入提交值。

### Task 7：实现明细与评分/判定矩阵

**Files:** Create `frontend/src/crf/components/{CrfRepeatTable,CrfChoiceMatrix,CrfSectionForm}.tsx`; Modify `frontend/src/crf/BaselineLayoutTable.tsx`, `frontend/src/crf/components/{CrfField,CrfDateField}.tsx`, `frontend/src/crf/fieldState.ts`（可选Form.List注册前缀，完整store路径语义保持）; Test新建的三个组件对应 `.test.tsx`、`frontend/src/crf/BaselineLayoutTable.test.tsx` 及 `frontend/src/crf/fieldState.test.ts`; Regression run现有 `frontend/src/crf/components/CrfField.test.tsx`（含日期控件，缺省接口保持，用既有回归；新列表前缀交互集中于真实Form.List的CrfRepeatTable.test.tsx）。

**Interfaces:** `CrfRepeatTable({field,name,disabled?})` 消费 `table_repeat.children`；`CrfChoiceMatrix({fields,disabled?})`；`CrfSectionForm({sections,form,disabled?,onDirty?})`。重复行持久化稳定 `_row_id` 及自己的 `_field_meta`，所有Form依赖包括数组行路径。共享控件可增可选 `registrationPrefix`：完整 `name` 仍用于store取值、watch、setFields和依赖，仅当前Form.List内部Form.Item注册名使用剥离前缀后的相对名；缺省行为不变。

- [x] 写失败用例：新增4条手术/3条过敏/3条用药/4条不良事件并保留全部；移动、删行和清空后该行备注/未知原因仍匹配同一row_id；满意度五题各自评分/备注进入独立键，总体评分不参加/25合计。填4条事件后 `expect(form.getFieldValue(["crf", "adverse_events", "entries"])).toHaveLength(4)`。
- [x] 运行这些组件测试，确认新组件未实现或原自由文本无法完成行为。
- [x] 用Form.List实现窄屏分组/宽屏表格；用矩阵呈现纳排、病史、药物、满意度和质控；机能按测试分组。按父答案控制子项适用性，保留隐藏已录值，别从页面卸载中误清除。
- [x] 基线布局只消费合约中的字段ID和章节，不能再漏掉布局表之外的字段；禁止显示开发表号及来源说明。
- [x] 完成本任务测试；用所有列有值的数据验证未挂载章节及多行值仍在 `getFieldsValue(true)` 中。

### Task 8：接入基线与访视页面，完成当前草稿的正确提交

**Files:** Modify `frontend/src/pages/patients/PatientCrfBaselinePage.tsx`, `frontend/src/pages/visits/VisitFormContent.tsx`, `frontend/src/crf/registryVisitExtensions.ts`, `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx`, `frontend/src/app/App.tsx`（等价data router接线，以支持完整离开守护）; Create `frontend/src/crf/{useCrfDraft,visitSubmission}.ts`; Test `frontend/src/crf/visitSubmission.test.ts`, `frontend/src/crf/useCrfDraft.test.tsx`（真实data router跳转、后退和留下/离开）及对应页面现有 `.test.tsx`；Regression run `frontend/src/app/App.test.tsx`（既有路由、鉴权及重定向）。

**Interfaces:** `useCrfDraft({form, serverValues, recordKey})` 输出初始值、dirty、patch及提交后重置方法；在 `visitSubmission.ts` 定义 `buildVisitSubmission(values: Record<string,unknown>, before: Record<string,unknown>, options: {complete: boolean}): {visit_date?: string | null; form_data?: Record<string,unknown>; status?: "completed"}`，供暂存和完成使用。

- [x] 写 `test_complete_submits_unsaved_measurement_feedback_and_visit_date`，断言单次PATCH含当前值及completed，`expect(payload).toMatchObject({visit_date: "2026-10-08", status: "completed"})` 并精确断言新反馈/测量字段；`test_refetch_does_not_overwrite_dirty_values`；`test_clear_and_unchanged_legacy_values_are_not_confused`。
- [x] 写T0/T1提前退出、基线prefill只填空、章节切换保持明细及标签精简的实际渲染/提交用例。
- [x] 运行对应页面测试，确认当前“完成只提交status”等缺陷失败。
- [x] 接入章节表单；统一原手写量表/扩展表单的提交源，消除同storage重复控件。日期可编辑并提交；完成前展示未处理项但仍允许缺失完成。两种操作使用同一payload构建，加载期间防重复提交。
- [x] 将服务端字段错误定位到具体输入；保存反馈显示成功时间；重取数据仅在无dirty或本次提交确认后初始化。移除重复章节介绍及字段来源说明，离开有未保存数据时提示。
- [x] 全部页面测试通过；保留已完成/归档只读及患者预填既有测试。

### Task 9：统一完整性求值与逐项预览

**Files:** Create `backend/apps/crf/completeness.py`; Modify `backend/apps/crf/services/aggregate.py`, `frontend/src/pages/crf/CrfPreviewPage.tsx`; Create `frontend/src/crf/components/CrfReadOnlySections.tsx`; Test `backend/apps/crf/tests/test_crf_aggregate.py`, `frontend/src/pages/crf/CrfPreviewPage.test.tsx`。

**Interfaces:** `evaluate_completeness(registry: dict, baseline: dict, visits: dict[str,dict]) -> dict` 返回 `sections`、`missing_fields`、`issues`及normal/unknown/not_applicable/unresolved计数；聚合继续保留旧顶层identity/visits字段。`CrfReadOnlySections({sections})`只显示标签、值、必要状态/原因和全部明细。

- [x] 写“仅旧11项不完整”、全适用项完整、NA/unknown缺原因、可选备注为空、父项否不要求子项、缺记录、旧总文本不代表细项齐全的失败用例；旧11项病例须 `assert result["missing_fields"]`，全适用项病例须 `assert result["missing_fields"] == []` 且无矛盾问题。
- [x] 运行聚合和预览测试，确认旧摘要不能满足预期。
- [x] 实现条件求值、状态统计及完整section投影；完成状态与字段齐全分开。原始旧记录以单独补充记录展示，完整性不擅自推断其内容。多个提前退出/完成记录冲突时提示复核，不默默覆盖。
- [x] 预览呈现全部字段、反馈及明细，去掉“暂无缺失字段”对11项摘要的误导；无缺失但有未知时明确显示数量。
- [x] 两组测试通过；取两个字段值相同但访视不同的病例验证来源未串T0/T1/T2。

### Task 10：原表按格回填及无限于纸面行数的DOCX

**Files:** Create `backend/apps/crf/services/docx_binding.py`; Modify `backend/apps/crf/services/export_docx.py`, `backend/apps/crf/registry_loader.py`; Create `backend/apps/crf/tests/test_crf_docx_binding.py`, `backend/tests/fixtures/crf_sentinel_cases.py`（后端测试共享夹具）；Test `backend/apps/crf/tests/test_crf_assets.py`（运行时受控源位置清单）。

**Interfaces:** `fill_crf_document(document: Document, preview: dict, registry: dict) -> Document`；`resolve_source_cells(document: Document, position: dict) -> list[_Cell]` 按明确的 `index_space="xml_tc"` 解析真实XML物理格（包括cell_indices跨格组），不能把物理格号直接用于python-docx逻辑网格；`export_preview_to_docx(preview: dict, output_path: Path) -> Path` 保留签名。每个格依据source_positions及明确的组合渲染规则回填，不做全文件首个同名/下划线替换。

- [x] 写每个原填写位的唯一哨兵值测试，检索对应表/行/格，不只检查值在文件任何地方出现，`assert sentinel in resolve_source_cells(saved_document, position)[0].text`，含T09.R02物理格1而逻辑网格2的合并格回归；检查三访视独立、未选择框不误勾、普通缺失保留空白、未知/NA的99/88及原因、月份与部分日期、民族其他表达。 单格文本位置使用上述断言；跨格选择组核对实际选中格与各未选中格，同源受试者编号在合法病例中保持一致。有限枚举不能伪造唯一合法字符串：几何单元测试可独立构造可识别标记，合法数据病例另按字段/访视/行及格组精确核对，不能把几何标记声称为真实API合法值，也不在产品增加测试模式。
- [x] 写 `test_repeat_rows_beyond_original_capacity_are_all_exported` 和 `test_hidden_old_entries_are_not_exported_as_active`。
- [x] 运行 `pytest apps/crf/tests/test_crf_docx_binding.py -q`，确认现有导出原表未填的失败。
- [x] 实现按格文本/勾选/日期/组合渲染，保留题干和静态提示；复制明细样式行扩展容量。额外状态原因、旧文本在可追溯的相应备注/补充区域输出。
- [x] 全部绑定测试通过；与原模板比较静态题干、固定版本和非填写格，避免把模板内容删掉。用python-docx重新读取文件验证持久化值，而非仅内存文档对象。

### Task 11：PDF转换、成功日志与访问策略

**Files:** Create `backend/apps/crf/services/export_pdf.py`; Modify `backend/apps/crf/views.py`, `backend/config/settings.py`, `backend/Dockerfile`, `frontend/src/pages/crf/CrfPreviewPage.tsx`; Reuse `backend/apps/crf/serializers.py`（已有实际版本及DOCX/PDF只读文件字段）；Test `backend/apps/crf/tests/test_crf_export_api.py`, `backend/apps/crf/tests/test_project_completion_crf_api.py`（既有归档导出消费者，仅转换进程边界fake）, `frontend/src/pages/crf/CrfPreviewPage.test.tsx`。

**Interfaces:** `convert_docx_to_pdf(docx_path: Path, output_dir: Path, *, timeout_seconds: int = 120) -> Path`；转换异常为 `CrfPdfConversionError`。独立工作目录和LibreOffice用户profile，不共享并发锁文件；生成DOCX/PDF成功后记录actual `template_revision`和可用文件字段。失败清理本次文件并返回明确错误，不能返回伪成功。

- [x] 写转换超时/失败、并发工作目录隔离、PDF缺失、日志版本与实际模板一致、输出目录配置可变及失败无残留测试；写受控权限范围外的preview/export拒绝用例。转换失败须 `assert CrfExport.objects.count() == before_count`，成功须 `assert pdf_path.read_bytes().startswith(b"%PDF-")`。
- [x] 运行导出API测试，确认当前PDF为空及直接查询范围问题失败；单元测试可替换转换进程，不替代最终真实转换验收。
- [x] 产品镜像增加 `libreoffice-writer`、`fonts-noto-cjk`；实现120秒有界转换和CJK输出；API沿用已有项目患者访问策略，FileField路径按MEDIA_ROOT处理。复用填好的同一DOCX，不另造PDF数据模板。 前端展示成功返回的DOCX/PDF下载入口，失败可理解且不伪报成功；移除过时“PDF后续接入”及media等实现文案，切换患者后不展示旧目标或晚到响应的文件。
- [x] 单元/API测试及一次修复复审已通过（最终21项）；本机真实转换成功。Task12/13及最终修复镜像真实中文双导出、各页文本、成功日志和逐页视觉证据已核对；最终修复Linux真实端到端19项通过。

### Task 12：固定依赖解析与全链路验收门禁

**Files:** Create `backend/requirements.lock.txt`, `backend/requirements-dev.lock.txt`, `scripts/verify_crf_release.py`, `backend/apps/crf/tests/test_crf_end_to_end.py`; Modify `backend/Dockerfile`, `backend/pyproject.toml`（仅固定pypdf开发依赖声明）、`.github/workflows/deploy-production.yml`、`backend/tests/fixtures/crf_sentinel_cases.py`, `backend/apps/crf/tests/test_crf_aggregate.py`（共享合法完整病例提取，既有断言保持）、`backend/apps/training/tests/{test_motion_analysis,test_motion_analysis_internal_claim_api,test_motion_analysis_storage,test_tracking_api}.py` 中仅骨架路径日期夹具。

**Interfaces:** `verify_crf_release(*, repo_root: Path, registry_path: Path, template_path: Path) -> dict` 返回资产、源位置覆盖及合约一致性结果；CLI失败非0退出。runtime/dev锁定清单在Python3.12解析，CI与镜像 `pip install -r` 同一runtime固定版本再无依赖安装本地包；CI后端验证在独立venv安装，避免其他worker验证依赖污染。固定开发解析器为`pypdf==6.10.0`，只用于真实PDF各页文本断言，不加入runtime依赖。

- [x] 写依赖锁未生效/缺资产/副本不同/源表被改时门禁失败的用例，异常CLI须 `assert process.returncode != 0`；端到端病例经真实API写入所有字段实例并回读preview、DOCX及PDF，不依赖仅字段清单或mock数据库。
- [x] 运行新测试确认旧流程不能通过；使用独立PostgreSQL16实例执行迁移，禁止`--nomigrations`作为最终结果。
- [x] 修正原有8项跨月份失效的测试夹具：合法骨架路径中的年月从对应 `training_video.training_date` 生成，日期不符的负例使用明确不同的年月；不改训练生产代码。已有失败证据见隔离基线日志，覆盖这8项并检查原路径拒绝测试继续失败/通过预期。
- [x] 生成可复现runtime/dev锁，修改CI和镜像安装；把资产、registry来源覆盖和纯校验探针加入构建/部署门禁。生成的运行镜像再次检查资源，不能只在构建阶段检查源码目录。
- [x] 执行完整 `cd backend && pytest`、Ruff、迁移检查；`cd frontend && npm run test && npm run lint && npm run build`，并运行release检查。全部真实检查通过才标本任务完成。
- [x] 保存完整、部分、未知/NA、重复行超容量、提前退出、旧数据兼容的端到端核对结果；逐格覆盖561个原位置，扩展备注另计。

### Task 13：浏览器与逐页验收，交付可发布结果

**Files:** 修改范围以此前任务为准；验收产物保存临时/用户可访问输出目录，不创建额外无关README。仅在实施发现实际缺陷时返回所属任务补测试并修复。 已发现的真实QA缺陷最小修复在既有 `CrfField/CrfDateField/fieldState` 及控件测试、`aggregate.py/test_crf_aggregate.py`、`docx_binding.py/test_crf_docx_binding.py/test_crf_end_to_end.py`；生成文档仅在T20/T21/T27/T28四个单段表补首个真实表头前的连续header前缀，T9多段表保持原header属性，原模板与样式/行高/字体不改，实际Linux长反馈跨页与已填/超容量原格复验；既有 `CrfPreviewPage/其测试` 及必要的 `CrfReadOnlySections` 纯显示helper对齐访视摘要与受控日期投影。

**Interfaces:** 消费Task12的最终镜像、Task10/11的导出文件和原位置清单；输出未处理问题、浏览器/逐页检查证据、精确测试结果、待发布改动范围。

- [x] 在隔离环境使用同一组最终镜像走基线、T0/T1/T2、Radio/Select/多选、年月/未知日期、满意度反馈、增删明细、暂存、直接完成、回读、预览及下载。
- [x] 检查宽屏及较窄容器，无字段长说明/来源技术文案，同时标签、单位、关键选择和反馈输入可见；键盘能操作，错误能定位。
- [x] 用文档工具渲染已填DOCX和PDF，逐页查看中文、勾选、长备注及超出纸面行数的记录；修复截断/重叠/乱码，并核对哨兵值没有只进入补充摘要。
- [x] 完成最终独立审查，并按实际修改补跑必要检查；报告具体代码变化、覆盖记录、通过数和限制。不在未授权时提交、推送或上线。
- [ ] 用户明确授权发布后沿用受控生产链路；发布完成再次核对线上实际镜像/提交、registry与模板哈希、公开前端产物和纯校验探针。未执行发布时将此项保持未勾选，并明确“待发布”。

## 自查与执行交接

- 设计§1/5/6 → Task2/3：全原位置、字段合约和无技术文案的数据映射。
- 设计§7/8/9 → Task4/6/7/8：状态、精度、反馈提交、组件与简洁录入。
- 设计§10 → Task4/5/8：规则、PATCH合并、当前输入原子完成。
- 设计§11 → Task9/10/11：真实完整性、逐格DOCX、同源PDF和访问范围。
- 设计§12/13 → Task1/12/13：资产/依赖可复现、PostgreSQL/浏览器/逐页/线上证据。
- Review Focus五项均已有所属测试；计划没有以模拟或SQLite成功代替最终验收。
- 计划自查（2026-10-08）：已逐节核对设计，补入显式计算操作、明确共享PATCH/访视提交函数所属文件，核对原公开函数签名；暂无未分配到任务的设计要求。

- [x] 用户审阅并批准实施；采用推荐的逐任务实施与独立复核。
- [x] 执行时读取设计和计划，保留用户已确认的方案B及精简说明要求；每任务先失败用例、后实现和验证，再更新勾选。

建议逐任务实施并独立复核：本次13个任务相互依赖字段合约，错误可能跨保存、完整性及原表导出传播，分段审查能尽早发现同源映射问题。也可由当前会话直接实施，再做一次整体独立复核。两种方式都执行同一套逐字段验收，区别在审查节奏和上下文成本。


## 最终整体审查修复（2026-10-09）

> 状态：implemented（原5项Important及M1均关闭，用户授权的追加I2范围复审通过，无新增C/I/M；验收完成、待发布）；原最终审查及每次修复、失败和复审记录保留，未提交发布。

- [x] I1：历史非法/null/标量日期叠加unknown/NA不得导致整份导出失败；无效原文保留核对区，合法部分日期正常原位，不能猜测为正常日期。
- [x] I2：当前草稿全部适用完整性、重复行子项、trim原因、部分日期/历史issue与未采纳计算值一致提示；仍允许缺失完成，完整列表可定位。追加验证空/非空数组、null及标量祖先与unknown/NA组合，合法重复行数字索引保持正常。
- [x] I3：已知合法metadata核心与附加旧键前后端观测一致，旧键保留，非法核心不放宽；条件区可录入并正确提交。
- [x] I4：生日仅切表示方式、部分未知和无效中间态不清除独立年龄；保留原合法联动，真实保存/刷新验证。
- [x] I5：所有重复行删除有中文后果说明及取消/确认，取消不改store/dirty，相邻ID和原因不受影响。
- [x] M1：与I2共用语义的章节进度、未处理列表/定位及固定操作栏，宽窄/键盘可用不遮挡；不另造完整性规则或重设计。
- [x] 聚焦真实失败→修复→相关测试、最终镜像重建/指纹、受影响真实UI及导出/变化页验证；一次定向复审及用户授权的追加I2范围复审通过，交付为待发布，发布步骤保持未勾。

文件范围：backend/apps/crf/services/docx_binding.py、completeness.py、field_rules.py（仅必要共享状态边界）及对应已有测试；frontend/src/crf/fieldState.ts、visitSubmission.ts、components/CrfRepeatTable.tsx、CrfSectionForm.tsx、pages/patients/PatientCrfBaselinePage.tsx、pages/visits/VisitFormContent.tsx、pages/research-entry/ProjectPatientResearchEntryPage.tsx（仅必要接线）及对应已有测试。允许必要的单一frontend草稿完整性纯helper与其测试，集中复用而非重复规则；其他产品文件如确需改动先给控制器具体风险/范围，不自行扩大。原DOCX/模型/生产数据/依赖版本不改。

执行记录（2026-10-09，Codex）：唯一最终修复19个产品/测试文件，后端相关221、前端相关80及最终焦点定向38、Linux真实双导出19项通过；378后端/156前端输入与实际验收镜像及HTTP产物独立核对一致。最终定向复审final-fix-re-review-report.md：I1/I3/I4/I5/M1及显式同值采用关闭，I2仍有历史assessments.sppb=[]叠加unknown原因的前后端完整性误判，状态保持implementing。20原件356页证据最终为23直接观察/333全字节复用，10份DOCX非body保真通过。浏览器删除取消的旧dirty文案选择器不能单独作证，采用真实Form store/touched断言。额外一轮定向修复的授权问题已提出，答复前不进入产品修改；未提交、推送或发布。

执行授权（2026-10-09）：用户答复“继续吧”，明确追加一轮I2历史数组父容器判断的定向修复与复审，覆盖上文一次最终修复的流程上限；不扩大其他功能，不提交/推送/发布。

最终验收记录（2026-10-09，Codex）：追加I2修复先复现helper 6失败及实际页面1失败；恰3文件，唯一产品改动为draftCompleteness.ts的父容器读取，数组只在下一段为数字索引时合法，issues优先于unknown/NA。当前候选、章节/完成清单、单次PATCH、无关暂存、刷新只读与旧原文/原因无损均有实际页面和HTTP证据，新非法数组在draft时400。前端最终全套473通过，lint 0错误/2既有警告，主机与最终Linux前端构建成功；中途HTTP mock返回旧draft的1失败及修正后全套输出保留。46组状态矩阵及8组×4项issue与实际后端逐项一致；final-i2-array-fix-review-report.md全部ADDRESSED，无新增Critical/Important/Minor。

根代理12:15 UTC独立核对当前378后端输入、156前端输入及动态枚举，与运行API dc79b742、新Web a458a073及不可变构建阶段75a74c69一致，58080的HTML/CSS/JS均200且逐字节一致，errors=[]。后端/registry/模板不变，复用已通过的后端相关221项、实际Linux双格式导出19项及20文档356页闭合视觉/包保真证据（23直接观察/333已观察图像逐页字节复用），不称追加修复重新运行后端全套或重新观察356页。早期后端全套1892通过/1部署静态检查失败及修正后整个部署文件13通过保留，不改写为初轮全绿。根代理另直接查看本次两个完整UI原图，四项SPPB核对错误、完成允许缺失及只读/布局证据成立。

线上12:20 UTC（北京时间20:20）只读运行镜像仍为backend/web-1f7493664223c8fd65a1b4d3139c08a8b12579d9，与本次验收修复不同；未提交、推送、部署或修改生产数据库，隔离工作树和审查快照保留。Minor边界仍为主包首次加载成本、既有工具/测试告警及源模板/多平台分页留白；字段全561原语义位置覆盖不等于既有真实患者数据已填满，也不担保任意未来历史形态、设备或字体环境。发布与发布后身份/兼容验收仍待用户单独授权。


## 2026-10-10 合并与生产发布授权

用户完成本地验收后明确要求：“没问题，合并代码到主分支，然后发布到线上”。此前禁止自动提交/推送/上线的约束在本次授权范围内解除；全部CRF修复及后续语义排版、三项知情同意、MoCA范围提示统一从验收工作树合并到main，并沿用GitHub Actions受控发布链路。发布前对最终源码快照重新运行完整验证，生产步骤仍须待新验证通过后执行。发布后核对实际镜像版本、源码、纯资源/依赖门禁、公开前端资源与健康，以及现有数据库备份完整性；不读取生产患者表。最终发布证据保存在/private/tmp/crf-production-release-20261010/。

执行记录（2026-10-10，Codex）：已验收CRF实现与spec/plan保存于7af6435。发布前完整后端1933项、前端519项通过；前端lint与构建通过。随后修整12个后端文件的72处格式问题，可执行AST与1933项测试版本逐文件一致；修整后相关193项、Ruff、迁移检查及CRF纯资源发布门禁通过，定向独立复审无新增阻断。准备合并main；线上发布结果待实际运行确认。

执行记录（2026-10-10，Codex）：主分支合并fc7ea2e后，正式流水线38043257583的worker协议513项、后端1933项及Ruff/迁移/CRF资源检查通过；管理端首次出现5项默认5000ms超时及1项后续页面缺失，故未构建镜像或部署。原始Node20两文件34项均通过，复杂交互约2.7–4.0秒。仅两个测试文件为对应5个声明（含each的2场景）设置15000ms总时限，操作、断言与findBy/waitFor时限保持原样；定向复审无新增阻断。调整后Node20完整前端519项、lint（0错误/3既有警告）与构建通过；后端及产品逻辑未变，继续由最终提交重新执行受控发布流程。
