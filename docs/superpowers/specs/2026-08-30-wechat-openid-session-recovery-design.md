> 状态：approved
> 日期：2026-08-30
> 范围：小程序使用真实 OpenID 建立持久账号绑定，并在缓存或 token 丢失后自动恢复登录
> 关联：`docs/superpowers/plans/2026-08-30-wechat-openid-session-recovery.md`

# 微信小程序 OpenID 自动恢复登录设计

## 1. 背景与问题

小程序当前把本地 `motioncare_patient_app_token` 作为唯一登录依据。缓存被清理后，绑定页无法识别用户曾经绑定过账号，会直接要求再次输入绑定码。

现有真实绑定流程还有一个更基础的问题：小程序把 `Taro.login()` 返回的一次性 code 直接作为 `wx_openid` 提交并写入 `PatientAppSession`。该 code 不是稳定的 OpenID，后端也没有调用微信 `code2Session`，所以现有数据无法支持按微信账号恢复登录。

本设计建立可信、持久的一对一微信绑定，并把它与 30 天 token 会话分离。完成一次真实 OpenID 绑定后，清缓存、重装小程序、更换设备或 token 过期都不再要求重新输入绑定码。

## 2. 已确认的产品规则

- 客户端不提交或声明 OpenID，只提交 `wx.login()` 返回的一次性 code；后端向微信换取可信 OpenID。
- 一个 OpenID 同时只能绑定一个 `ProjectPatient`。
- 一个 `ProjectPatient` 同时只能绑定一个 OpenID。
- 使用绑定码建立新绑定时，自动替换 OpenID 原绑定和目标 `ProjectPatient` 原绑定。
- 上述替换只影响患者端微信绑定和患者端 token，不调用项目级 `unbind`，不删除 `ProjectPatient`、处方、训练记录或其他研究数据。
- token 继续保持 30 天有效期；只要持久微信绑定未被撤销，即使 token 过期也可按 OpenID 自动签发新 token。
- 指导老师执行现有“撤销患者端绑定”后，持久微信绑定和相关 token 一并失效，用户不能再自动恢复。
- 只有后端明确确认当前 OpenID 未绑定时，小程序才展示绑定码输入；网络或微信接口故障不能被当作未绑定。
- OpenID 的恢复范围是同一微信账号、同一小程序 AppID。更换微信账号、再次迁移 AppID 或明确撤销绑定后，需要重新输入绑定码。

## 3. 非目标

- 不改变 `ProjectPatient` 的研究项目绑定语义。
- 不新增项目级解绑、患者删除或研究数据清理行为。
- 不引入多账号选择器；一对一约束消除账号选择问题。
- 不使用客户端持久化的 OpenID、UnionID 或长期 refresh token 作为身份依据。
- 不把微信 `session_key` 下发给小程序，也不使用它替代 MotionCare 自有 token。
- 不改变演示模式的数据隔离规则。
- 不重做 Web 管理端患者绑定卡片的布局和操作流程；只补充持久微信绑定状态语义。

## 4. 数据模型

### 4.1 新增 `PatientAppWechatBinding`

新增当前态模型，专门表示持久微信绑定：

```text
PatientAppWechatBinding
- project_patient: OneToOneField(ProjectPatient, on_delete=CASCADE)
- wx_openid: CharField(max_length=128, unique=True)
- created_at
- updated_at
```

约束含义：

- `wx_openid` 唯一，保证一个微信账号最多绑定一个项目账号。
- `project_patient` 一对一，保证一个项目账号最多绑定一个微信账号。
- 该表只保存当前有效绑定。换绑或撤销时删除旧记录；历史关系继续由 `PatientAppSession` 保留审计线索。
- 删除 `ProjectPatient` 时级联删除患者端微信绑定，但不反向触发任何额外项目数据删除。

### 4.2 调整 `PatientAppSession`

`PatientAppSession` 继续表示可过期的 Bearer token 会话：

- `expires_at` 继续使用 30 天 TTL。
- `is_active` 继续控制 token 是否可用。
- `wx_openid` 改为可空，仅记录创建该会话时已经由后端验证的真实 OpenID，供审计使用。
- 不通过 session 是否过期推导持久绑定是否有效。

数据 migration 将所有历史 `PatientAppSession.wx_openid` 清空，因为当前版本写入的全部是一次性 `wx.login code`，不能作为真实身份继续使用。migration 不根据历史值创建 `PatientAppWechatBinding`。

## 5. 微信身份交换组件

在 `backend/apps/patient_app/` 内新增独立微信身份提供器，业务接口只依赖以下边界：

```text
exchange_login_code(wx_code) -> wx_openid
```

实现要求：

- 使用现有 `httpx` 依赖调用微信 `code2Session`。
- 请求参数来自服务端配置的 AppID、AppSecret、`wx_code` 和固定授权类型。
- 设置明确的连接与读取超时，不无限等待微信响应。
- 只把经过格式校验的 OpenID 返回给业务层。
- `session_key`、AppSecret、完整临时 code 不写日志、不入库、不返回小程序。
- 微信返回无效 code、频率限制、非 JSON、缺少 OpenID、HTTP 错误或超时时，转换为内部明确但对外安全的异常。
- 客户端提交的 `wx_openid` 字段不再被 API 接受。

## 6. API 合同

### 6.1 启动恢复接口

```text
POST /api/patient-app/wechat-session/
Authorization: Bearer <旧 token>  # 可选，仅用于保留现有会话或迁移老用户

{
  "wx_code": "wx.login 返回的一次性 code"
}
```

已绑定时返回 `200`：

```json
{
  "status": "authenticated",
  "token": null,
  "project_patient_id": 1,
  "patient": {"id": 1, "name": "..."},
  "project": {"id": 1, "name": "..."}
}
```

`token` 为可空字符串：需要签发新 token 时返回明文 token；可继续使用请求中的有效旧 token 时返回 `null`。

明确未绑定时返回 `200`：

```json
{
  "status": "unbound"
}
```

`unbound` 是正常业务状态，不用 `401` 或 `404` 表示。该接口使用容错的可选 token 解析，不套用“无效 token 立即抛出 `401`”的常规患者端认证流程；无效的可选旧 token 不阻断 OpenID 恢复，也不能单独证明用户未绑定。

### 6.2 绑定码接口

保留现有路径：

```text
POST /api/patient-app/bind/

{
  "code": "四位绑定码",
  "wx_code": "本次重新调用 wx.login 获得的 code"
}
```

成功响应继续返回新 token 和绑定身份。旧字段 `wx_openid` 从请求合同中删除；多传该字段不能影响服务端解析出的身份。

### 6.3 医生端绑定状态

现有医生端接口继续保留：

```text
GET /api/studies/project-patients/{id}/binding-status/
```

响应新增：

```json
{
  "has_wechat_binding": true,
  "wechat_bound_at": "2026-08-30T10:00:00+08:00"
}
```

- `has_wechat_binding` 和 `wechat_bound_at` 表示不会随 token 过期而消失的持久微信绑定。
- 现有 `has_active_session`、`last_bound_at` 和 `active_session_expires_at` 继续只描述当前可用 token session。
- Web 管理端的“患者绑定状态”和“撤销绑定”能力以持久微信绑定为主，同时在迁移期兼容尚未补建持久绑定的有效旧 session。
- 页面布局、生成绑定码与撤销二次确认流程保持不变。

### 6.4 错误分类

- `400`：请求字段无效或微信临时 code 无效/已使用。
- `409`：并发换绑导致数据库唯一性竞争，客户端可重新发起完整流程。
- `429`：启动恢复或绑定请求超过限流。
- `503`：微信服务超时、上游异常或运行时身份配置不可用。

错误响应只提供安全、可操作的中文提示，不回传微信原始响应、密钥、token 或完整临时 code。

## 7. 后端业务流程

### 7.1 自动恢复或静默迁移

`wechat-session/` 在一次微信 code 交换后按以下优先级处理：

1. 若真实 OpenID 已存在 `PatientAppWechatBinding`，该持久绑定是身份真相来源。
2. 若请求携带的旧 token 仍有效且对应同一 `ProjectPatient`，保留当前 token 并返回 `token: null`；若该 session 的 `wx_openid` 为空，则补写真正 OpenID。
3. 若本地 token 缺失、无效、过期或指向其他账号，停用当前绑定两侧的旧活动 session，签发新 token。
4. 若 OpenID 尚未绑定，但请求携带有效旧 token，且该 token 对应的 `ProjectPatient` 也尚无持久微信绑定，则静默创建绑定；这是升级前老用户的迁移路径。
5. 若 OpenID 未绑定，且没有满足迁移条件的有效旧 token，返回 `status: unbound`。

若 OpenID 已绑定账号 A，而可选旧 token 指向账号 B，以持久 OpenID 绑定 A 为准；旧 token 不能覆盖它。若 OpenID 未绑定但旧 token 对应账号已绑定另一个 OpenID，也不能静默抢占，返回 `unbound`，必须通过绑定码显式换绑。

### 7.2 使用绑定码换绑

先在数据库事务之外使用本次 `wx_code` 换取真实 OpenID，避免等待微信网络响应时占用数据库锁。身份交换成功后，在单个数据库事务中：

1. 验证并锁定四位绑定码及其目标 `ProjectPatient`。
2. 锁定能够找到的 OpenID 当前绑定、目标账号当前绑定及相关 `ProjectPatient`，锁顺序保持确定。
3. 删除满足 `wx_openid = 当前 OpenID` 或 `project_patient = 目标账号` 的旧持久绑定。
4. 停用满足 `wx_openid = 当前 OpenID` 或 `project_patient = 目标账号` 的全部活动 session。
5. 创建唯一的新 `PatientAppWechatBinding` 和新 `PatientAppSession`。
6. 标记四位绑定码已使用并返回新 token。

事务失败时不消耗绑定码、不留下半完成绑定。唯一约束负责数据库最终兜底；无法安全重试的并发冲突返回 `409`。

### 7.3 撤销绑定

现有 `revoke_project_patient_binding(project_patient)` 扩展为同一事务内：

- 撤销未使用的四位绑定码；
- 删除该 `ProjectPatient` 的 `PatientAppWechatBinding`；
- 停用该 `ProjectPatient` 的所有活动 session。

撤销后，原 OpenID 的下一次启动恢复必须得到 `unbound`。

## 8. 小程序启动状态机

绑定页增加明确的启动状态：

```text
checking -> authenticated -> 跳转首页
         -> unbound       -> 展示绑定码
         -> error         -> 展示登录检查失败与重试
```

冷启动或被 `401/403` 导回绑定页时：

1. 若当前为进程内演示会话，继续沿用现有演示逻辑。
2. 页面进入 `checking`，不立即渲染绑定码输入。
3. 调用 `Taro.login()`，再调用 `wechat-session/`；本地存在 token 时放入 Authorization header。
4. `authenticated`：若响应包含新 token 则覆盖本地 token，否则保留现有 token；随后进入首页。
5. `unbound`：清除无效本地 token 并展示绑定码输入。
6. 请求异常：进入 `error`，保留重试入口，不展示真实账号绑定提示。

用户提交四位绑定码时必须重新调用 `Taro.login()`，不能复用启动阶段已消耗的 code。演示绑定码仍在本地进入隔离演示模式，不调用真实绑定 API。

## 9. 配置与部署

新增服务端配置：

```text
WECHAT_MINIAPP_APP_ID
WECHAT_MINIAPP_APP_SECRET
WECHAT_MINIAPP_CONNECT_TIMEOUT_SECONDS
WECHAT_MINIAPP_READ_TIMEOUT_SECONDS
WECHAT_MINIAPP_AUTH_MODE
WECHAT_MINIAPP_MOCK_OPENID
```

要求：

- `WECHAT_MINIAPP_APP_ID` 必须与 `miniapp/project.config.json` 当前 AppID 一致。
- AppSecret 只写入生产服务器受保护的 `.env`，不进入源码、Git 历史、构建命令或日志。
- `.env.example` 与 `deploy/env.production.example` 只记录空值和说明。
- `deploy/docker-compose.prod.yml` 向 Web、Celery 等实际需要加载 Django settings 的后端容器透传配置，但微信身份交换只由 Web 请求路径调用。
- 非 DEBUG 环境缺少 AppID/AppSecret 或启用模拟身份时，Django 配置检查必须失败。
- `WECHAT_MINIAPP_AUTH_MODE` 只允许 `wechat` 或 `mock`；`mock` 仅可在 DEBUG 环境使用，并从 `WECHAT_MINIAPP_MOCK_OPENID` 读取固定本地身份。
- 本地开发可显式启用仅限 DEBUG 的模拟身份提供器；自动化测试优先注入 mock transport/provider，不访问真实微信网络。
- 发布前必须先把当前 AppID 对应的 AppSecret 安全配置到生产环境，否则不得发布依赖自动恢复的新小程序版本。

## 10. 限流与安全

- `wechat-session/` 在调用微信前执行基于可信客户端地址的限流，防止放大上游请求。
- `bind/` 使用更严格的限流，降低四位绑定码被穷举的风险。
- 限流状态使用共享 Redis，不能依赖单进程内存计数。
- Bearer token、OpenID、AppSecret、`session_key`、绑定码明文和完整微信临时 code 均不得出现在异常详情或应用日志中。
- 客户端前端控制只用于体验，所有身份解析、唯一性和换绑规则均由后端执行。

## 11. 测试策略

### 11.1 微信身份提供器

- `code2Session` 成功时仅返回 OpenID。
- 无效 code、微信错误码、频率限制、超时、HTTP 错误、非 JSON 和缺少 OpenID 均映射为安全异常。
- 请求参数正确且密钥、`session_key`、临时 code 不出现在错误文本中。
- 非 DEBUG 配置缺失或模拟模式误用时配置检查失败。

### 11.2 服务与数据库

- OpenID 与 `ProjectPatient` 两侧唯一约束均生效。
- 无本地 token、token 过期和 token 被清除时，可通过已有持久绑定签发新 token。
- 有效旧 token 且两侧都无持久绑定时，静默创建绑定。
- 旧 token 与现有持久绑定冲突时，持久绑定优先且不会被静默覆盖。
- 绑定新账号会替换两侧旧持久绑定并停用相关 session。
- 换绑不会删除 `ProjectPatient`、处方或训练数据。
- 撤销患者端绑定会删除持久微信绑定并停用 session。
- 事务失败不消耗四位绑定码；并发冲突由约束兜底。
- 数据 migration 清空全部历史伪 OpenID，且不创建错误的持久绑定。

### 11.3 API

- `wechat-session/` 覆盖 `authenticated`、`unbound`、旧 token 迁移和安全错误。
- `bind/` 只接受 `code + wx_code`；客户端伪造 `wx_openid` 不影响结果。
- 医生端绑定状态同时准确返回持久微信绑定和活动 token session；token 过期后仍可撤销持久绑定。
- 两个公开身份接口均应用共享限流。
- 响应与错误中不泄露敏感凭据。

### 11.4 小程序

- 启动时先显示检查态。
- 已绑定 OpenID 自动进入首页并正确保存新 token。
- 有效本地 token 可完成无感历史迁移。
- 只有明确 `unbound` 才显示绑定码。
- 微信登录、网络或服务端失败时显示重试态，不显示绑定提示。
- 提交真实绑定码前重新获取新的微信 code。
- 演示绑定码继续进入隔离演示模式。
- 原有 `401/403` 清 token 行为最终会进入新的恢复流程。

### 11.5 Web 管理端

- 持久微信绑定存在而 token 已过期时仍显示“已绑定”并允许撤销。
- 迁移期只有有效旧 session、尚无持久绑定时不错误显示为未绑定。
- 生成绑定码、撤销确认和现有状态字段展示保持兼容。

## 12. 验收标准

- 真实用户完成一次 OpenID 绑定后，清空小程序缓存仍能自动进入原账号。
- token 超过 30 天后可以自动续签，无需重新输入绑定码。
- 同一 OpenID 绑定新账号后，旧账号患者端 token 失效，但旧账号研究数据完整保留。
- 目标账号原来绑定的其他 OpenID 不能再自动登录。
- 指导老师撤销患者端绑定后，原 OpenID 只能看到绑定码入口。
- 持久绑定存在而 token 已过期时，医生端仍显示已绑定并可执行撤销。
- 升级前仍保有有效 token 的用户无感补建真实 OpenID 绑定；升级前已经丢失 token 的用户只需重新绑定一次。
- 微信身份交换不可用时，不把已绑定用户误判为未绑定。
- 后端患者端相关测试、小程序全量测试、小程序 TypeScript 检查和生产构建全部通过。

## 13. 预计影响范围

后端：

- `backend/apps/patient_app/models.py` 与新 migration
- `backend/apps/patient_app/services.py`
- `backend/apps/patient_app/serializers.py`
- `backend/apps/patient_app/views.py`
- `backend/apps/patient_app/urls.py`
- 新增微信身份提供器及其测试
- `backend/apps/studies/views.py` 与绑定状态 API 测试
- `backend/config/settings.py` 与配置测试
- `.env.example`
- `deploy/env.production.example`
- `deploy/docker-compose.prod.yml`

小程序：

- `miniapp/src/pages/bind/index.tsx`
- `miniapp/src/api/client.ts` 或新增专用身份 API 模块
- 相应 Vitest 测试

Web 管理端：

- `frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx`
- `frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx`

Web 端仅调整持久绑定状态判断，不改变页面布局和操作流程；项目级解绑接口合同保持不变。
