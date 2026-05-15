> 状态：approved
> 日期：2026-05-14
> 范围：微信小程序患者端二版一期；患者日常工作台、处方训练闭环、动作历史、健康日数据。
> 关联：`specs/patient-rehab-system/prd.md`、`docs/superpowers/specs/2026-05-14-prescription-motion-training-design.md`
> 实施基线 commit：981c652

# 微信小程序患者日常工作台设计

## 背景

MotionCare 第一版 PRD 明确以医院 Web 后台研究数据闭环为目标，不包含微信小程序患者端。现在项目进入二版逐步推进阶段，本设计作为二版患者端一期范围，不回退第一版边界，而是在既有后台模型、处方、训练记录和健康日数据基础上新增患者侧入口。

现有系统中，患者是全局档案，`ProjectPatient` 是患者在某个研究项目中的已确认绑定关系；处方和训练记录均围绕 `ProjectPatient` 展开。小程序一期应尊重这一业务模型：患者端先绑定到一个项目患者身份，围绕该身份展示处方、训练任务和健康填报。

## 已确认决策

1. **小程序端作为二版新增范围推进**：不修改第一版“不包含微信小程序”的历史定位。
2. **同仓库多前端项目**：在仓库根目录新增 `miniapp/`，与医生后台 `frontend/` 并列，共用 `backend/`。
3. **技术栈采用 Taro + React + TypeScript**。
4. **一期采用绑定码绑定**：医生后台在某个 `ProjectPatient` 上生成绑定码，患者在小程序输入绑定码完成绑定。
5. **一期只支持单项目身份**：患者端 token 只对应一个 `ProjectPatient`，多项目切换后置。
6. **小程序不直接复用医生后台 API**：后端新增患者端 API 命名空间，统一做患者端鉴权和行级过滤。
7. **一期功能为患者日常工作台**：包含首页、当前处方、本周运动进度、训练入口、动作训练历史和健康日数据填报。
8. **处方页必须提供训练入口**：患者可针对处方动作进入单动作训练页并提交训练记录。
9. **处方页展示本周患者运动进度**：按每个处方动作的结构化每周目标次数统计。
10. **动作历史一期只查当前处方动作的历史**：不跨旧处方版本聚合。
11. **同一动作一天内允许多次训练记录**：本周进度按完成次数累计，超出目标也保留记录。
12. **处方动作新增结构化每周目标次数**：例如 `weekly_target_count`，禁止从频次文案中解析目标值。
13. **健康日数据继续按全局 `Patient + record_date` 唯一**：小程序通过已绑定的 `ProjectPatient` 找到患者后写入该患者当天健康记录。

## 目标

- 建立微信小程序患者端独立工程。
- 支持患者通过医生提供的绑定码绑定单个项目患者身份。
- 提供患者日常首页，展示今日训练、健康数据状态和本周训练概览。
- 提供当前处方页，展示处方动作、本周进度、训练入口和动作历史入口。
- 提供单动作训练页，允许患者按处方动作提交训练结果。
- 提供动作历史页，查看当前处方动作近 7 天和近 30 天完成近况。
- 提供今日健康数据填报页，写入全局患者健康日数据。
- 后端保证患者端 token 只能访问绑定的 `ProjectPatient` 相关数据。

## 非目标

- 不做多项目切换。
- 不做微信手机号自动匹配患者档案。
- 不做研究进度展示。
- 不做 T0/T1/T2 访视问卷或量表填写。
- 不做推送提醒。
- 不做 AI 动作识别、摄像头采集或动作自动评分。
- 不做视频上传、对象存储、防盗链或签名 URL。
- 不做训练计划日历化排程。
- 不做患者主动搜索或选择项目。

## 项目结构

新增小程序前端工程：

```text
MotionCare/
├── backend/
│   ├── apps/patient_app/      # 患者端绑定、鉴权、聚合 API
│   ├── apps/prescriptions/    # 处方与处方动作，新增每周目标次数
│   ├── apps/training/         # 训练记录，患者端提交复用服务层
│   └── apps/health/           # 健康日数据，继续 Patient + 日期唯一
├── frontend/                  # 医生 Web 后台
└── miniapp/                   # Taro + React + TypeScript 微信小程序
```

`miniapp/` 独立维护自己的构建配置、页面路由、API client、状态管理和样式体系。它不依赖 `frontend/` 的 Ant Design、React Router 或后台鉴权代码。

## 后端边界

新增 `backend/apps/patient_app/`，专门承载患者端绑定、会话和 API 聚合。患者端接口必须通过患者端 token 定位唯一的 `ProjectPatient`，禁止由前端传入任意 `patient_id` 或 `project_patient_id` 来决定数据范围。

医生后台仍通过现有 session + CSRF 鉴权访问后台 API。小程序患者端采用独立 token 鉴权，不使用后台 session。

### 绑定码模型

建议新增 `PatientAppBindingCode`：

```text
PatientAppBindingCode
- project_patient
- code_hash
- expires_at
- used_at
- created_by
- revoked_at
- created_at
- updated_at
```

规则：

- 绑定码属于单个 `ProjectPatient`。
- 绑定码为 4 位纯数字字符串，允许前导零，例如 `0387`。
- 明文绑定码只在生成接口响应中返回一次，数据库只保存哈希。
- 绑定码固定有效期为 15 分钟，从医生端点击生成绑定码的时间开始计算。
- 过期、已使用、已撤销的绑定码不可绑定。
- 同一 `ProjectPatient` 可以重新生成绑定码，但旧有效绑定码应按业务规则撤销或作废，避免多码并存造成运营混乱。
- 4 位数字码只要求在当前有效窗口内全局唯一；过期、已使用或已撤销的历史码允许后续复用，避免 0000-9999 的历史全局唯一池被耗尽。

### 患者端会话模型

建议新增 `PatientAppSession`：

```text
PatientAppSession
- project_patient
- patient
- wx_openid
- token_hash
- expires_at
- last_seen_at
- is_active
- created_at
- updated_at
```

规则：

- 绑定成功后生成患者端 token。
- token 只代表一个 `ProjectPatient`。
- `patient` 字段从 `project_patient.patient` 冗余保存，方便健康日数据查询和审计。
- 正式小程序环境下，绑定接口需要结合 `wx.login` 获取微信身份，并保存 `wx_openid`；本地开发和自动化测试可以通过后端配置使用模拟 openid。
- 撤销绑定后，对应 session 置为 inactive。

## API 设计

### 小程序患者端 API

统一挂在 `/api/patient-app/`：

```text
POST /api/patient-app/bind/
GET  /api/patient-app/me/
GET  /api/patient-app/home/
GET  /api/patient-app/current-prescription/
POST /api/patient-app/training-records/
GET  /api/patient-app/actions/{prescription_action_id}/history/
GET  /api/patient-app/daily-health/today/
PUT  /api/patient-app/daily-health/today/
```

接口规则：

- 除 `bind/` 外，均要求患者端 token。
- token 校验后得到唯一 `ProjectPatient`。
- `current-prescription/` 只返回当前 active 处方。
- `training-records/` 只允许提交当前 active 处方下的动作。
- `actions/{id}/history/` 只允许查询当前 active 处方下的 `PrescriptionAction`。
- `daily-health/today/` 按 token 绑定的患者写入今日健康数据。

### 医生后台 API

在 `ProjectPatient` 维度新增绑定管理动作：

```text
POST /api/studies/project-patients/{id}/binding-code/
GET  /api/studies/project-patients/{id}/binding-status/
POST /api/studies/project-patients/{id}/revoke-binding/
```

规则：

- 生成绑定码需要医生或管理员权限，并受既有项目/患者行级权限约束。
- `binding-status/` 返回是否存在有效绑定、最近绑定时间、是否存在有效绑定码等运营信息，不返回历史明文绑定码。
- `revoke-binding/` 用于停用患者端 session，必要时也撤销未使用绑定码。

## 处方与训练进度

`PrescriptionAction` 需要新增结构化字段：

```text
weekly_target_count: PositiveIntegerField
```

含义：

- 表示该处方动作每周目标完成次数。
- 医生开具或调整处方时逐动作填写。
- active 处方动作的 `weekly_target_count` 必须大于 0。
- 动作库建议频次可以作为默认值来源，但最终以处方动作快照上的结构化字段为准。
- 小程序本周进度不解析 `frequency`、`suggested_frequency` 这类文本字段。

本周进度统计：

- 周期按 Asia/Shanghai 自然周统计：周一 00:00:00 到周日 23:59:59。
- 统计字段按 `TrainingRecord.training_date`，不按记录创建时间。
- 完成次数默认统计 `TrainingRecord.status = completed`。
- `partial` 和 `missed` 记录保留在历史中，但不计入完成次数。
- 同一动作一天内允许多次记录。
- 超过目标的记录继续累计，例如目标 2 次、完成 3 次时展示为 `3/2`，前端可标记“已超额完成”。

训练提交规则：

- 小程序训练页针对单个 `PrescriptionAction` 提交。
- 后端根据 token 找到 `ProjectPatient`，再校验该动作属于当前 active 处方。
- 创建 `TrainingRecord` 时自动写入 `project_patient`、`prescription`、`prescription_action`。
- 前端可提交 `training_date`、`status`、`actual_duration_minutes`、`note` 和分类表单数据。

## 小程序页面

一期页面结构：

```text
miniapp/
└── src/
    ├── pages/
    │   ├── bind/              # 绑定码输入页
    │   ├── home/              # 首页工作台
    │   ├── prescription/      # 当前处方 + 本周进度 + 动作列表
    │   ├── training/          # 单动作训练提交
    │   ├── action-history/    # 单动作训练历史
    │   └── daily-health/      # 今日健康数据填报
    ├── api/
    ├── auth/
    └── components/
```

### 绑定页

- 用户输入医生提供的 4 位数字绑定码。
- 绑定码输入采用四格验证码样式展示，底层输入只保留数字，最大长度 4 位。
- 输入控件唤起数字键盘；不足 4 位时禁止提交绑定。
- 调用 `POST /api/patient-app/bind/`。
- 成功后保存 token，跳转首页。
- token 失效或被撤销时回到绑定页。

### 首页工作台

调用 `GET /api/patient-app/home/`，展示：

- 患者姓名。
- 项目名称。
- 今日训练任务摘要。
- 本周训练完成概览。
- 今日健康数据是否已填写。
- 当前处方入口。
- 继续训练入口。
- 健康填报入口。

### 当前处方页

调用 `GET /api/patient-app/current-prescription/`，展示：

- 当前处方版本和生效时间。
- 本周整体进度。
- 处方动作列表。
- 每个动作的每周目标次数、已完成次数、最近完成时间。
- 每个动作提供“开始训练”和“历史”入口。

### 单动作训练页

- 根据 `prescription_action_id` 展示动作名称、动作说明、处方参数和视频 URL 或图文说明。
- 患者提交完成状态、实际时长、备注。
- 调用 `POST /api/patient-app/training-records/`。
- 提交成功后返回处方页或首页，并刷新本周进度。

### 动作历史页

调用 `GET /api/patient-app/actions/{prescription_action_id}/history/`，展示：

- 近 7 天完成次数。
- 近 30 天完成次数。
- 最近完成时间。
- 当前处方动作下的训练记录列表。

一期只查当前处方动作的历史，不跨旧处方版本聚合。

### 健康填报页

- 调用 `GET /api/patient-app/daily-health/today/` 拉取今日已有数据。
- 调用 `PUT /api/patient-app/daily-health/today/` 保存。
- 写入或更新全局患者当天 `DailyHealthRecord`。

## 健康日数据规则

继续沿用当前模型语义：`DailyHealthRecord` 按全局 `Patient + record_date` 唯一。

小程序写入流程：

1. 通过患者端 token 找到 `ProjectPatient`。
2. 从 `ProjectPatient` 找到全局 `Patient`。
3. 对该患者今日健康记录执行 upsert。

这样同一患者即使未来参与多个项目，也不需要为同一天重复填写健康数据。项目 CRF 汇总时仍从患者维度读取对应日期健康数据。

## 权限与安全

- 患者端 token 和后台 session 完全分离。
- 小程序接口不得信任前端传入的患者 ID、项目 ID 或项目患者 ID。
- 所有患者端资源访问都从 token 绑定的 `ProjectPatient` 推导。
- 绑定码明文只返回一次，数据库保存哈希。
- 绑定码固定 15 分钟过期；患者端 token 也需要过期机制。
- 医生撤销绑定后，患者端 token 应立即失效。
- 后台绑定管理接口必须沿用医生端权限和行级过滤。

## 测试与验收

### 后端测试

- 绑定码只能绑定对应 `ProjectPatient`。
- 新生成的绑定码是 4 位数字字符串，且有效期为生成后 15 分钟。
- 当前仍有效的未使用绑定码不能重复；过期、已使用或已撤销的历史码允许复用。
- 过期、已使用、已撤销绑定码不能绑定。
- 患者端 token 只能访问自己的 `ProjectPatient` 数据。
- 当前处方接口返回本周进度、动作列表、最近完成摘要。
- 训练提交允许同一动作同一天多条记录。
- 训练提交拒绝非当前 active 处方动作。
- 动作历史只返回当前处方动作的记录。
- 健康日数据按 `Patient + record_date` upsert。
- 医生后台生成、查看、撤销绑定码接口有权限校验。

### 小程序测试

- 绑定成功后进入首页。
- 未绑定或 token 失效时回到绑定页。
- 首页能进入处方、训练、健康填报。
- 处方页展示本周进度和动作入口。
- 训练提交后刷新本周进度。
- 动作历史展示近 7 天和近 30 天完成近况。
- 健康填报保存后首页状态更新。

## 实施提示

- 第一阶段先落后端患者端身份、绑定码和 API 合同，再建 `miniapp/` 工程。
- 患者端 API 可以复用处方、训练、健康模块的服务层，但不要复用后台 ViewSet。
- `weekly_target_count` 是小程序本周进度的关键字段，应先改处方模型和医生端开方表单。
- 实施计划需要明确微信登录接入深度：若一期暂不接真实 `wx.login`，也要保留模型字段和 API 扩展点，避免后续改表结构过大。
