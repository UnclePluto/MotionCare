> 状态：approved
> 日期：2026-05-12
> 范围：患者列表、详情只读、独立编辑路由、生日驱动年龄、列表删除与脱敏
> 关联：`docs/superpowers/plans/2026-05-12-patient-list-detail-edit-routing.md`
> 取代说明：覆盖 `2026-05-11-patient-list-actions-privacy-design.md` 中「姓名链进详情」「列表 Modal 编辑」等段落；脱敏规则、删除守卫与主治医生姓名列与其一致。

# 患者列表、详情与编辑路由设计

## 列表 `/patients`

- 手机号：展示层脱敏，11 位为 `前三位 + **** + 后四位`；过短/异常时首尾各 1 位中间 `*`，空为 `—`。
- 点击表格行（`onRow`）进入 `/patients/:id`；操作列「编辑」「删除」`stopPropagation`。
- 操作列：「编辑」→ `/patients/:id/edit`；无「详情」链接；「删除」危险按钮 → 二次确认弹窗（逻辑同详情页：有关联项目则阻断并展示原因；否则可删）。成功后 `invalidateQueries(['patients'])`。
- 列：姓名、性别、年龄、手机号（脱敏）、主治医生（`primary_doctor_name`，无则 `—`）；移除「主治医生 ID」列。
- 移除列表「编辑患者」Modal 及 `editId` 相关状态与请求。

## 详情 `/patients/:id`

- 人口学信息以只读展示（`Descriptions` 或等价）；「编辑档案」按钮 → `/patients/:id/edit`。
- 保留：加入项目、停用/启用、删除、项目参与表、相关 Modal。

## 编辑 `/patients/:id/edit`

- 表单字段：姓名、性别、出生日期、年龄（只读，由出生日期与今天计算）、手机号、备注。
- 未选出生日期：年龄区展示提示文案；保存时 `birth_date: null` 且 `age: null`（与后端 validate 一致）。
- 保存成功 → 提示并 `navigate(/patients/:id)`；取消 → `navigate(-1)` 或回详情。

## 后端

- `PatientSerializer` 增加只读 `primary_doctor_name`（来自 `primary_doctor.name`）。
- 当请求体 **显式包含** `birth_date` 键时：`null` → `age` 置 `null`；有日期 → `age` 按公历周岁重算。其它 PATCH 不强行改 `age`。

## 非目标

- 新建患者 Modal 暂不强制生日 + C2（可后续迭代）。
