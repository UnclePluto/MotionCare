# 项目详情页回归分组看板设计

日期：2026-05-13  
范围：MotionCare 管理端项目详情页、项目患者入口、分组看板患者详情跳转、旧分组状态类型残留。  
状态：待用户 review 后进入实现计划。

## 背景

`30d6088 merge(codex): 前端临时随机与确认入组绑定` 已将项目分组语义收敛为：

- 患者与项目不存在预绑定关系。
- 只有患者确认加入某项目的某个分组后，才创建正式 `ProjectPatient`。
- 项目分组随机只在前端页面内存中发生。
- 项目页不应存在“直接添加患者到项目”的入口。

后续 CRF/项目患者入口改动在项目详情页新增了 `ProjectPatientsTab`。该 Tab 提供“添加患者”按钮，并尝试 `POST /studies/project-patients/` 直接创建项目患者关系。后端当前已经拒绝该接口，但前端入口仍会误导用户，也重新引入了被删除的“项目患者直接绑定”产品语义。

## 目标

项目详情页重新回到单一分组看板：

- 不展示“项目患者”Tab。
- 不展示“添加患者到项目”入口。
- 不展示项目详情页顶部固定 CRF/访视提示文案。
- 不展示项目详情页顶部 `CRF 模板版本`、状态、描述等说明块。
- 组内患者卡片保留“患者详情”跳转，后续 CRF、访视、基线等录入入口由患者详情页承接。
- 清理当前代码中与本问题直接相关的旧语义残留。

## 非目标

- 不改变 `ProjectGroupingBoard` 的本地随机、确认入组、解绑、已确认置灰逻辑。
- 不改变后端 `confirm-grouping`、`ProjectPatientViewSet`、`enroll-projects` 的接口语义。
- 不新增 CRF、T0、T1、T2 在项目详情页的快捷入口。
- 不大规模翻修历史计划文档中已经标记过时的 pending、randomize、患者池描述。
- 不改患者详情页已有 CRF 或访视入口。

## 前端页面设计

`frontend/src/pages/projects/ProjectDetailPage.tsx` 保留项目标题和右上角“新增分组 / 元数据”按钮。项目内容区直接渲染 `ProjectGroupingBoard`。

需要移除：

- `Tabs` 容器。
- `ProjectPatientsTab` 引用。
- “项目患者”Tab。
- 顶部 `Typography.Paragraph` 说明块。
- 固定文案：
  - `CRF 模板版本：...`
  - `状态：...`
  - `CRF 录入请从「患者详情」对应项目行进入`
  - `访视评估可从「项目患者」页 T0/T1/T2 进入`

`frontend/src/pages/projects/ProjectPatientsTab.tsx` 直接删除。该文件的“添加患者”入口与产品规则冲突，不保留为未引用死代码。

`ProjectGroupingBoard` 内的已确认患者卡片继续提供 `患者详情` 链接。该链接是项目页进入患者后续资料与录入入口的唯一项目页路径。本次不在卡片上新增 CRF 或访视快捷入口。

## 清理范围

清理直接相关残留：

- 删除 `frontend/src/pages/projects/ProjectPatientsTab.tsx`。
- 从 `ProjectDetailPage.tsx` 删除不再使用的 import、状态映射和项目说明渲染。
- 删除 `frontend/src/pages/patients/PatientListPage.tsx` 中 `ProjectPatientRow.grouping_status` 类型字段。当前后端序列化已不返回该字段，且患者删除确认逻辑只需要 `project`。
- 更新相关前端测试，确保测试不再依赖项目患者 Tab 或固定 CRF 文案。

保留非直接相关内容：

- 后端迁移中的历史 `grouping_status` 引用。
- 已标记过时的历史设计/计划文档。
- 分组看板测试中“不调用 randomize”的防回归断言。

## 数据与接口

本设计不新增接口，不修改后端模型。

项目详情页仍通过分组看板使用现有接口：

- `GET /api/patients/`
- `GET /api/studies/groups/?project={id}`
- `GET /api/studies/project-patients/?project={id}`
- `POST /api/studies/projects/{id}/confirm-grouping/`
- `POST /api/studies/project-patients/{id}/unbind/`

不再从项目详情页调用：

- `POST /api/studies/project-patients/`

这保持了“确认加入某项目分组后才存在正式绑定”的边界。

## 测试与验收

前端测试应覆盖：

- 打开项目详情页时能看到分组看板内容，例如“全量患者”或“随机分组”。
- 页面不出现“项目患者”Tab。
- 页面不出现“添加患者”按钮。
- 页面不出现 `CRF 模板版本`。
- 页面不出现 `CRF 录入请从`。
- 页面不出现 `访视评估`。
- 删除 `ProjectPatientsTab.tsx` 后不存在任何引用。
- `PatientListPage.tsx` 中不再存在 `grouping_status` 类型残留。
- 既有 `ProjectGroupingBoard` 测试继续通过，证明本地随机与确认入组逻辑未被改坏。

验收时，项目详情页应只呈现：

- 项目标题。
- “新增分组 / 元数据”按钮。
- 分组看板。
- 分组配置 Drawer。

项目页不得提供任何“直接添加患者到项目”的入口。

