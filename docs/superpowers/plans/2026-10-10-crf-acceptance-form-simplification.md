# CRF 验收表单简化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans 或 superpowers:subagent-driven-development 逐任务执行；本计划推荐当前会话串行实施。每一步使用复选框跟踪。

**Goal:** 修复用户提出的全部五项问题，使患者基线归属正确、答案与不详共用字段、日期与预填易用、布局紧凑，并在同一本地入口完成真实验收。

**Architecture:** 普通答案保留原类型，不详/不适用使用同一业务路径下的带标识对象，前后端共享解析语义。原生访视日期保留完整日期投影；文档修订位置独立分类，项目封面进入T0。网页用统一答案控件和内容栅格，保持原表导出绑定及旧数据兼容。

**Tech Stack:** Django 5 / DRF / PostgreSQL / React 18 / TypeScript / Ant Design 5 / TanStack Query v5 / pytest-django / Vitest / LibreOffice。

**Spec:** `docs/superpowers/specs/2026-10-10-crf-acceptance-form-simplification-design.md`，2026-10-10用户回复“方案A吧”批准。

> 状态：implemented；2026-10-10按用户批准的方案A及“执行吧”完成当前会话串行实施
> 日期：2026-10-10
> 实施基线：1f7493664223c8fd65a1b4d3139c08a8b12579d9 + 已验收未提交CRF修复
> 工作树：/Users/nick/.codex/worktrees/crf-complete-entry/MotionCare
> 执行记录（2026-10-10，Codex）：Task1–6均已实施并验证；后端1933通过、前端58文件502通过、lint/build/source/migration门禁通过。58080已更新，382后端/159前端输入及6静态资源hash一致；原验收记录逐字段不变，旧实例保留。全部改动未提交，既有修复和历史资料保留。

## Global Constraints

- 本次覆盖全部五点，不以只删除状态下拉或只补CSS完成任务。
- 单字段对象：`{"__crf_answer__":1,"state":"unknown","value":6,"reason":null}`；普通答案保留原有数字、字符串、列表、null。身份字段没有不详按钮。
- 新编辑不再写入平行_field_meta/_crf_field_meta；未改字段、旧附加键及历史异常保留；打开页面不触发写入或批量迁移。
- 通用不详原因可选；原表不能完成原因、反馈、处理、其他说明及退出原因保持字段、条件和校验。
- 保留Session/CSRF、接口和行级权限、已完成/归档写保护、原子“当前答案+完成”PATCH、离开守护及晚到响应保护；缺失允许保存、完成和导出。
- ProjectPatient是唯一已确认项目关系；患者全局，多项目数据隔离；不恢复批次、后端临时随机或pending模型。
- DateField只存真实完整日期/null；不能用88/99冒充临床分数。部分日期不虚构日期，T1/T2不采用创建时间作实际访视日期。
- 日期使用Asia/Shanghai；仅首次缺失预填，已有值、0、明确清空/不详及手填草稿不覆盖；计算建议仍须明确采用。
- 内容宽度至少1000px三列、至少640px两列、小于640px一列；长备注、长选择组和重复明细跨行。
- schema_revision=3，template_revision=1.1。源DOCX SHA256=f031dd59a1e169548fe651555d19c41306cc51e6bfcf7eb933edcee86924102a；31表/265行/561来源位置保留。
- 沿用现有依赖和Web后台Ant Design样式；不引入小程序字号/色彩，不新增模型字段，检查意外迁移。
- 用户未授权提交、推送、发布，不自动进行；每任务记录验证结果及未提交状态。禁止回退、删除既有工作；大型改动前补充完整只读快照，不能用提交覆盖用户偏好。

## Review Focus

1. 旧metadata与新不详对象冲突、取消不详：以明确编辑的新答案为准，正常值不能残留state/reason；Task1/2断言原子替换和无关旧键保留。
2. 历史非法父对象/重复行身份及排序：不详不能将坏父容器算为已处理，重排不能把答案/原因串给另一行；Task1断言[]父容器与_row_id重排。
3. enrolled_at跨上海日期边界、多项目及延迟回读：预填按当前项目、已有/清空/不详优先，晚响应不覆盖草稿；Task3断言17:30Z转次日、两个项目及重取。
4. 原生日期的未知/部分精度与完成只读：请求必须在DRF DateField前解析，投影为null，实际日期不虚构；Task2/4覆盖真实PATCH及禁用全部日期/更多动作。
5. 真实窄容器、隐藏条件及键盘错误定位：无空首列/空行/双线，更多与弹层可操作、固定保存栏不挡内容；Task5/6覆盖三张截图位置和1440/760/390视口下的实际内容宽度。

---

## 文件职责与执行顺序

六项串行任务依赖Task1答案合约。解析与PATCH协调分别留在共享模块；日期投影放独立适配器；预填纯函数与草稿生命周期分离。共享控件和布局不各自复制状态/条件规则。现有大型导出模块只调整读取边界，不做无关重构。

### Task 1：同一字段答案合约与历史兼容

**Files:**
- Create: `frontend/src/crf/answerValues.ts`、`backend/apps/crf/answer_values.py`
- Modify: `frontend/src/crf/types.ts`、`fieldState.ts`、`formValues.ts`、`draftCompleteness.ts`、`fieldCalculations.ts`、`visitSubmission.ts`（均在frontend/src/crf）
- Modify: `backend/apps/crf/field_values.py`、`field_rules.py`、`completeness.py`、`registry_validate.py`
- Modify: `backend/apps/patients/serializers.py`、`backend/apps/visits/serializers.py`的手填量表类型校验
- Test: `frontend/src/crf/answerValues.test.ts`、`fieldState.test.ts`、`formValues.test.ts`、`draftCompleteness.test.ts`、`visitSubmission.test.ts`
- Test: `backend/apps/crf/tests/test_crf_answer_values.py`、`test_crf_field_rules.py`、`backend/apps/patients/tests/test_patient_baseline_api.py`、`backend/apps/visits/tests/test_visit_form_data_contract.py`

**Interfaces:**
- Produces TS: `CrfMarkedAnswer = {__crf_answer__:1;state:'unknown'|'not_applicable';value:unknown;reason:string|null}`。
- Produces TS: `decodeCrfAnswer(value:unknown,legacyMeta?:unknown):{state:'value'|'unknown'|'not_applicable';value:unknown;reason:string|null;marked:boolean;error:string|null}`；`setCrfAnswerState(value:unknown,state:'value'|'unknown'|'not_applicable',legacyMeta?:unknown):unknown`；`setCrfAnswerReason(value:CrfMarkedAnswer,reason:string|null):CrfMarkedAnswer`；`isCrfMarkedAnswer(value:unknown):value is CrfMarkedAnswer`。
- Produces Python: `decode_crf_answer(value:object, legacy_meta:object=None)->dict`返回同名键；`is_crf_marked_answer(value:object)->bool`；`reconcile_answer_patch(current:dict,patch:dict,fields:list[dict])->dict`返回副本，只协调明确编辑路径的旧状态/通用原因，保留附加键。
- Existing interfaces remain: `get_field_value`与`getCrfFieldRawValue`返回原始答案；`get_observed_value`与`getObservedCrfValue`仅返回校验有效的普通观察值。changed_crf_paths/buildCrfPatch/merge_crf_patch把带标识对象作为原子答案。

- [x] Step1：写失败用例。共享输入向量覆盖普通0/否/[]/空白/null、不详保留值6/可选原因、不适用、旧meta、两套冲突、标识bool/版本2/非法state/reason和陌生对象。断言无原因unknown为已处理；非法父容器`sppb=[]`叠加unknown仍unresolved；正常原值不因空meta变为未填。重复行按稳定_row_id重排后值和原因仍属于原行；无ID用严格位置兼容。
  ```ts
  expect(setCrfAnswerState({__crf_answer__:1,state:'unknown',value:6,reason:null},'value')).toBe(6);
  expect(buildCrfPatch({score:6},{score:{__crf_answer__:1,state:'unknown',value:6,reason:null}})).toEqual({score:{__crf_answer__:1,state:'unknown',value:6,reason:null}});
  ```
  ```python
  assert merge_crf_patch({'score': {'__crf_answer__': 1, 'state': 'unknown', 'value': 6, 'reason': '旧'}}, {'score': 0}) == {'score': 0}
  ```
- [x] Step2：分别运行`cd frontend && npm run test -- src/crf/answerValues.test.ts src/crf/formValues.test.ts src/crf/draftCompleteness.test.ts`及`cd backend && pytest apps/crf/tests/test_crf_answer_values.py apps/crf/tests/test_crf_field_rules.py -q`，记录缺失解析/替换行为的失败；环境故障不当作功能失败。
- [x] Step3：实现上述解析/切换签名。无标识对象沿用旧校验；有标识对象核心严格校验，保留raw供历史追溯。unknown不参加条件、分数/日期/比值计算；旧与新祖先结构错误均保留问题。原子diff/替换，不递归混合对象内容；不详generic reason_required约束取消，原表临床原因仍按registry独立检查。
- [x] Step4：在患者/访视PATCH协调明确编辑的旧metadata，更新已知量表类型校验为使用解析后的值并保留JSON父类型限制。新非法对象返回原业务字段错误；未改历史异常不阻断无关保存；新客户端不提交旧状态，新旧客户端读取保持兼容。
- [x] Step5：运行Step2及两组API测试、fieldState/formValues/visitSubmission原测试，全部通过。检查数据库GET普通与unknown来回后只保留一套新答案，旧附加键不丢；保存、完成提醒、预览counts与前端逐项一致。
- [x] Step6：记录本任务结果和改动范围，不提交。

### Task 2：访视日期单字段接口与原生日期投影

**Files:**
- Create: `backend/apps/visits/crf_date_answer.py`
- Modify: `backend/apps/visits/serializers.py`、`backend/apps/crf/field_values.py`、`field_rules.py`
- Modify: `frontend/src/crf/fieldState.ts`、`types.ts`、`visitSubmission.ts`、`frontend/src/pages/visits/VisitFormContent.tsx`
- Test: `backend/apps/visits/tests/test_visit_form_data_contract.py`、`test_status_transition.py`、`frontend/src/crf/visitSubmission.test.ts`

**Interfaces:**
- Consumes Task1 decode/原子PATCH；详情logical visit_date为普通日期string/null或CrfMarkedAnswer。
- Produces Python: `CrfVisitDateAnswerField(serializers.Field)`用作详情serializer的visit_date；`read_visit_date_answer(visit_date:object,form_data:dict)->object`新路径优先，兼容旧parts/native；`project_visit_date_answer(answer:object)->date|None`仅合法YYYY-MM-DD投影。
- Produces Python: `prepare_visit_date_patch(patch:dict)->dict`保留原签名，显式提交logical visit_date时更新`form_data.crf.meta.visit_date_answer`并协调旧parts；未提交不清洗。validate阶段用logical candidate校验，再给模型attrs native投影；ListSerializer仍提供native DateField，详情提供logical答案。
- Produces TS: `buildVisitSubmission`的visit_date返回类型扩为`string|CrfPartialDate|CrfMarkedAnswer|null`以兼容历史，仍只提交一个logical visit_date键；已有form_data路径类型不变。

- [x] Step1：写真实API失败测试`test_visit_date_answer_round_trip_and_projection`，完整日期2026-10-10→unknown→取消→null，GETlogical与DBprojection分别正确；年2026/月2026-10投影null，旧parts/native冲突只在明确编辑协调，未改冲突完整保留；同PATCH完成包含最新答案，completed/archived拒绝写入。额外断言body同时提供两种不同新日期值返回字段错误，不能静默覆盖。
- [x] Step2：运行`cd backend && pytest apps/visits/tests/test_visit_form_data_contract.py -q`确认DateField当前拒绝unknown的失败，记录错误。
- [x] Step3：实现日期Field先解析后投影，扩展allow_partial_date合法YYYY/YYYY-MM及旧parts校验。非真实日期/标识bool/非法precision仍错误；两种不一致显式新输入拒绝，同值接受；未编辑旧记录不迁移。调整前端serverValues和提交类型，日期详情展示读新答案。
- [x] Step4：运行Step2、状态迁移测试和visitSubmission测试，断言本地真实API无类型绕过；`python manage.py makemigrations --check --dry-run`应无意外模型更改。
- [x] Step5：记录本任务结果和未提交状态。

### Task 3：文档归属、项目封面与不会覆盖草稿的系统预填

**Files:**
- Modify: `scripts/crf_registry/baseline_fields.py`、`visit_fields.py`、`schema.py`、`scripts/build_crf_registry_v1.py`、`scripts/verify_crf_release.py`
- Generate: `specs/patient-rehab-system/crf/registry.v1.json`、`frontend/src/crf/registry.v1.json`；来源清单不改变位置或原文
- Create: `frontend/src/crf/visitPrefill.ts`、`backend/apps/crf/services/project_cover.py`
- Modify: `frontend/src/pages/patients/PatientCrfBaselinePage.tsx`、`frontend/src/pages/visits/VisitFormContent.tsx`、`frontend/src/crf/useCrfDraft.ts`、`registryVisitExtensions.ts`、`types.ts`
- Modify: `backend/apps/crf/services/aggregate.py`、`completeness.py`、`services/docx_binding.py`（兼容来源的接入点）
- Test: `backend/apps/crf/tests/test_registry_source_coverage.py`、`test_registry_visit_contract.py`、`test_crf_aggregate.py`、`test_crf_assets.py`、`test_crf_end_to_end.py`
- Test: `frontend/src/crf/visitPrefill.test.ts`、`useCrfDraft.test.tsx`、`frontend/src/pages/patients/PatientCrfBaselinePage.test.tsx`、`frontend/src/pages/visits/VisitFormPage.test.tsx`

**Interfaces:**
- Produces registry `document_bindings: {binding_id:string;kind:'template_static';source_positions:SourcePosition[]}[]`，两个修订姓名源位置从clinical fields移到此清单。validate_registry_contract同时检查clinical/document绑定，总561位置无遗漏/重复；静态修订姓名不填编造值。
- Retains doc_protocol_number/doc_enrolled_on/doc_investigator_name的field_id，storage改为`visit.form_data.crf.cover.protocol_number|enrolled_on|investigator_name`，visit_types=['T0']，section/table_ref='study_cover'。两项修订不再出现在基线字段或计数。
- Produces Python `resolve_project_cover(project_patient,t0_form_data:dict,baseline:dict)->dict`纯投影，不save；当前项目已存键（含null）优先，单一已确认项目才取旧demographics.document；多项目legacy放历史补充不自动copy。未存enrolled_on用真实入组上海日期。aggregate/界面投影共用同一来源优先级。
- Produces TS `buildVisitPrefill(input:{visitType:'T0'|'T1'|'T2';serverValues:Record<string,unknown>;enrolledAt?:string;doctorName?:string;legacyCover?:Record<string,unknown>;confirmedProjectCount:number;readOnly:boolean}):Record<string,unknown>`返回副本。医生姓名、已有实际访视日期可预填assessor_name/assessed_on，不推断T1/T2事件日。
- `useCrfDraft`新增`prefillNames?:CrfName[]`，记录same-record明确操作和已初始化字段；同记录刷新不重新预填明确清空/unknown，也不能reset旧草稿。computed的adoptableNames语义不变。

- [x] Step1：写失败断言：基线tabs/进度无“文档修订”及两修订字段；来源31/265/561且document绑定恰好两个；三个封面为T0当前项目字段；既有原文哈希不变。两个项目入组分别2026-10-09T17:30:00Z和另一日期，第一预填2026-10-10；既有值/null/unknown/0优先，匿名医生不编造名。单项目旧cover可读，多项目不复制；完整旧原文仍在历史补充。
- [x] Step2：运行`cd frontend && npm run test -- src/crf/visitPrefill.test.ts src/crf/useCrfDraft.test.tsx src/pages/patients/PatientCrfBaselinePage.test.tsx`与`cd backend && pytest apps/crf/tests/test_registry_source_coverage.py apps/crf/tests/test_crf_aggregate.py -q`确认对应失败。
- [x] Step3：实现来源分类和项目cover解析，schema_revision升3并更新所有版本门禁；执行`python scripts/build_crf_registry_v1.py`及`cd frontend && npm run sync-crf-registry`，生成器是唯一字段修改源。不能降低覆盖门槛或删除来源项让测试通过。明确文档绑定的只读来源验证，保留修订模板页。
- [x] Step4：接入当前ProjectPatient入组事实与useAuth().me.name，即使props.patientId已提供仍获得当前绑定事实；复用现有项目患者及患者接口取confirmedProjectCount，权限不足或未返回时不启用旧cover回退。预填纯函数用于初始化，不在渲染或后台响应时调用PATCH；锁定记录只显示系统事实，不修改答案。
- [x] Step5：实现草稿prefillNames生命周期，测试`test_clear_then_refetch_does_not_reprefill`、切章/切访视/延迟响应、完成只读及明确采用computed同值。运行Step2及visit表单测试、全部source/contract/assets门禁。
- [x] Step6：记录旧设计被替代的具体文档/状态/日期/布局条款，在changelog只追加本次已批准决定，不改历史；记录未提交。

### Task 4：统一“更多→不详”和简单日期组件

**Files:**
- Create: `frontend/src/crf/components/CrfAnswerControl.tsx`、`CrfMoreOptions.tsx`
- Modify: `frontend/src/crf/components/CrfField.tsx`、`CrfDateField.tsx`、`CrfChoiceMatrix.tsx`、`CrfRepeatTable.tsx`、`CrfReadOnlySections.tsx`
- Test: `frontend/src/crf/components/CrfAnswerControl.test.tsx`、`CrfDateField.test.tsx`、`CrfField.test.tsx`、`CrfChoiceMatrix.test.tsx`、`CrfRepeatTable.test.tsx`

**Interfaces:**
- Consumes Task1 decode/set-state；Task2/3 registry和日期逻辑。
- Produces `CrfAnswerControl({field,value,onChange,disabled,legacyMeta,children}:{field:RegistryField;value?:unknown;onChange?:(value:unknown)=>void;disabled?:boolean;legacyMeta?:unknown;children:(props:{value:unknown;onChange:(value:unknown)=>void;disabled:boolean})=>ReactNode})`，一个Form.Item与业务name绑定，不注册平行metadata。
- Produces `CrfMoreOptions({field,answer,onChange,disabled,datePrecision,onDatePrecisionChange})`，answer为unknown，精度为'day'|'month'|'year'；标签旁入口用AntD Popover/Checkbox，state切换互斥，通用原因在弹层可选。
- CrfField/CrfDateField保留现有`field,name,registrationPrefix,disabled`Props，以免破坏Form.List索引。DatePicker完整日期YYYY-MM-DD、年月YYYY-MM、年YYYY；精度改动产生同一业务答案，旧parts不能合法表达时紧凑展示原值及核对信息。

- [x] Step1：写交互失败用例：文本/数字0/单选否/多选/矩阵分数/重复子项均无“填写状态”combobox；更多勾选unknown后输入、采用计算、清除禁用，取消恢复原值；理由不填可保存，反馈/退出/不能完成独立条件字段仍出现并提交。数字0在勾选/取消后仍0，Form.List行调序不串原因。只读更多和日期精度也不可修改。
- [x] Step2：运行`cd frontend && npm run test -- src/crf/components/CrfAnswerControl.test.tsx src/crf/components/CrfDateField.test.tsx src/crf/components/CrfField.test.tsx src/crf/components/CrfRepeatTable.test.tsx`确认失败。
- [x] Step3：实现两个组件并由所有控件复用，删除CrfField及MatrixField各自的状态/通用原因Form.Item，补齐未知disabled及旧meta读取；保留长说明精简及临床说明字段。identity/canonical只读不出现未知入口。
- [x] Step4：CrfDateField改用单DatePicker，删除常驻“分别填写年月日”、三组分量状态和独立清除按钮；更多仅允许字段支持的精度。保留无法表示的旧日期原文及冲突提醒，明确编辑才协调。其他量表选项优先Radio/Checkbox，长选项Select且label可搜索。
- [x] Step5：运行Step2加matrix、只读、访视表单测试，验证提交body只有一套业务字段及临床反馈。菜单键盘可打开/关闭，禁用后仍可从更多取消unknown，通用原因的错误能定位。
- [x] Step6：记录控件与payload证据，不提交。

### Task 5：内容栅格、紧凑编排及三张截图样式

**Files:**
- Create: `frontend/src/crf/components/CrfFieldGrid.tsx`
- Modify: `frontend/src/crf/components/CrfChoiceMatrix.tsx`、`CrfSectionForm.tsx`、`CrfField.tsx`、`frontend/src/crf/BaselineLayoutTable.tsx`、`frontend/src/styles/global.css`
- Test: `frontend/src/crf/components/CrfFieldGrid.test.tsx`、`CrfChoiceMatrix.test.tsx`、`CrfSectionForm.test.tsx`、`frontend/src/crf/BaselineLayoutTable.test.tsx`

**Interfaces:**
- Consumes `evaluateCrfCondition`及Task4CrfField，没有新条件执行器。
- Produces `CrfFieldGrid({fields,disabled}:{fields:{field:RegistryField;name:CrfName}[];disabled?:boolean})`，先从完整Form store求可见字段，再DOM排序。普通字段div栅格、长字段span全列；明确量表组保留评分矩阵内容，矩阵行不渲染空单元格。
- CrfSectionForm保留现有Props和进度/保存栏；普通网页章节不再使用纸面table布局。BaselineLayoutTable保留旧layout数据兼容入口但过滤空/不可见内容，不作为新版普通字段布局；真实重复明细仍是table。

- [x] Step1：写失败断言：父条件隐藏field1而field2/3可见时第一个DOM字段为field2，无空td；婚姻/民族和手术/过敏段没有嵌套装饰表格；所有子项隐藏时没有空组/行；短字段同容器，textarea/长选择/明细span全列。进度定位和dirty守护仍用业务字段name。
- [x] Step2：运行`cd frontend && npm run test -- src/crf/components/CrfFieldGrid.test.tsx src/crf/components/CrfChoiceMatrix.test.tsx src/crf/components/CrfSectionForm.test.tsx src/crf/BaselineLayoutTable.test.tsx`确认失败。
- [x] Step3：实现CrfFieldGrid与基于内容容器的CSS断点1000/640px，宽度稳定、label/更多/输入/单位同块；按语义测试组排列，不按存储父路径产生稀疏三列。移除普通字段table的内外border叠加；不要去掉真实明细表头/边界。
- [x] Step4：运行Step2，并在真实页面逐一切换手术/过敏条件，验证婚姻/民族单一必要区分、无末尾空行多边线；访视评估者姓名/日期左侧开始，无第一空列。
- [x] Step5：记录真实宽窄布局坐标与截图，测试1440/760/390视口，并按实际内容宽度断言列数（不能把浏览器宽度当内容宽度）。检查长标签、错误、菜单、日期弹层、固定保存栏、键盘焦点无遮挡；根代理直接查看对应三处最终截图。
- [x] Step6：记录布局结果，不提交。

### Task 6：全链路回归、独立复核及本地验收更新

**Files:**
- Modify/Test: `backend/apps/crf/tests/test_crf_end_to_end.py`、`test_crf_docx_binding.py`、`test_crf_export_api.py`、`backend/tests/fixtures/crf_sentinel_cases.py`、`frontend/src/pages/crf/CrfPreviewPage.test.tsx`
- Modify if needed: `backend/apps/crf/services/docx_binding.py`、`frontend/src/pages/crf/CrfPreviewPage.tsx`，只修Task1新投影/文档绑定的展示适配
- Update: 本计划和关联spec完成证据；运行报告放`/private/tmp/crf-acceptance-simplification-20261010/`，不新建无关README

**Interfaces:**
- Consumes所有Task1–5产物，`build_crf_preview(project_patient)->dict`、`fill_crf_document(document,preview,registry)->Document`现有入口不变。
- Produces验收矩阵：五项要求分别列源码、实际请求/回读/数据库、渲染/导出证据及通过/未通过；不得使用旧镜像/旧截图代替新验证。

- [x] Step1：扩展端到端用例`test_single_answer_acceptance_round_trip`：普通、全空、unknown/NA无通用原因、旧meta冲突、旧日期、历史非法父、重复超过模板容量、满意度反馈/处理/退出。真实API保存→GET→DB→预览→DOCX原位→Linux LibreOffice PDF；比对保存的完整答案，不只断言HTTP200。DOCX/PDF显示99/88且临床JSON没有假分数；原记录及补充无损。
- [x] Step2：运行端到端焦点测试，确认新案例缺陷后针对所属模块修复，不删除用例或临床源位置。DOCX检查全部非正文部件及源文件哈希，修订页模板原样；实际PDF每页文本和视觉无裁切/乱码/丢行，重复第5行及新日期/unknown页面根代理直接查看。
- [x] Step3：运行后端全套`cd backend && pytest`，前端全套`cd frontend && npm run test`、`npm run lint`、`npm run build`；`python manage.py makemigrations --check --dry-run`；`python scripts/verify_crf_release.py`；`git diff --check`。使用Python>=3.12、既有锁定测试环境与Node20；命令因环境失败必须修环境并重跑，报告警告及仍失败项。
- [x] Step4：按用户选定的执行工作流做最终独立审查，输入批准spec、本计划及本次范围diff，覆盖上述Review Focus和全部五项；真实重要缺陷修复后验证再报告，不拿旧审查通过作新证据。
- [x] Step5：用当前源码建立新的本地API/Web镜像，绑定现有本地数据库/media，不重建或清空验收病例。先在临时端口验证；启动参数沿用本地服务配置，不输出密钥。记录源码输入、registry/template、镜像身份及frontend dist和HTTP资源SHA相等；旧镜像保持可恢复，用户有未保存页面不自动reload。
- [x] Step6：更新同一本地入口`http://127.0.0.1:58080`，检查基线`/patients/14/crf-baseline`、研究录入`/research-entry/project-patients/13`及`/crf?projectPatientId=13`。保留原本地病例与账号，可使用新增合成病例作破坏性测试；手工验收页面只做读取，不替用户完成访视。
- [x] Step7：根代理逐要求完成审计：1基线文档移除和source分类；2全组件单字段unknown/反馈；3真实系统预填与日期；4宽窄编排；5三图样式；补充旧数据/接口/导出/权限和版本一致性。证据缺失保持未完成，全部满足才标spec/plan implemented并更新goal complete；最终提供本地链接和验证结论，不提交/推送/上线。

## 计划自查与批准状态

- [x] spec每项均分配Task及直接证据：1→Task3/6，2→Task1/2/4/6，3→Task2/3/4，4/5→Task5/6。
- [x] 原生DateField、源561位置、身份字段、已完成/归档写保护及旧metadata/部分日期/附加键均明确。
- [x] 五个Review Focus分别有Task1–6对应失败用例；正常/空/否/0/unknown/NA、结构异常、多项目/重取和重复行不会漏掉。
- [x] 签名在消费任务一致；保留现有共享入口，不新增重复状态或条件规则；无占位设计和未归属验收。
- [x] 确认本计划只记录执行决定，不提前勾选实施步骤或报告产品已修复。
- [x] 用户审阅本计划，2026-10-10回复“执行吧”；按推荐当前会话串行实施。

推荐当前会话串行实施：六项任务密切依赖同一答案/日期接口，避免多次重复上下文和同时编辑共享控件；全部实现后再独立审查。

## 最终验收证据（2026-10-10，Codex）

证据目录：`/private/tmp/crf-acceptance-simplification-20261010/`；逐要求矩阵：`acceptance-final-audit.json`。最终后端全量1933项通过（832.67秒），前端58文件502项通过；lint 0错误/3条既有fast-refresh警告、构建通过且既有bundle体积警告保留、只读pytest缓存警告1条。无需模型迁移。

实际原病例基线、研究录入与CRF预览已检查，未替原病例保存预填或完成访视；合成病例验证真实保存、数据库回读、反馈导出及完成后拒绝写入。15页实际导出与17页扩展案例PDF逐页及关键行视觉已核对。原表31表/265行/561来源位置完整，两修订位置独立静态绑定，源文件hash不变。

本地入口`http://127.0.0.1:58080`已更新。当前运行镜像输入、测试后端快照、构建输出和实际HTTP静态资源均一致；旧API/Web实例可恢复，数据库及media沿用。仅本地更新，未提交、推送或部署线上。


## 2026-10-10 合并与生产发布授权

用户完成本地验收后明确要求：“没问题，合并代码到主分支，然后发布到线上”。此前禁止自动提交/推送/上线的约束在本次授权范围内解除；全部CRF修复及后续语义排版、三项知情同意、MoCA范围提示统一从验收工作树合并到main，并沿用GitHub Actions受控发布链路。发布前对最终源码快照重新运行完整验证，生产步骤仍须待新验证通过后执行。发布后核对实际镜像版本、源码、纯资源/依赖门禁、公开前端资源与健康，以及现有数据库备份完整性；不读取生产患者表。最终发布证据保存在/private/tmp/crf-production-release-20261010/。
