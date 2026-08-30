> 状态：review
> 日期：2026-08-30
> 范围：实现真实 OpenID 持久绑定、启动自动恢复、唯一换绑和医生端状态适配
> 关联：`docs/superpowers/specs/2026-08-30-wechat-openid-session-recovery-design.md`
> 实施基线 commit：`4d03db3`

# 微信小程序 OpenID 自动恢复登录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让真实微信用户完成一次绑定后，可在缓存清除、重装、更换设备或 token 过期时凭可信 OpenID 自动恢复原账号，并保证一个 OpenID 与一个 `ProjectPatient` 一对一绑定。

**Architecture:** 后端通过微信 `code2Session` 把一次性 `wx.login code` 换成可信 OpenID，以独立 `PatientAppWechatBinding` 保存持久绑定，以 `PatientAppSession` 保存可过期 token。启动恢复与绑定码换绑都由后端事务和数据库唯一约束兜底；小程序绑定页使用 `checking / unbound / error` 状态机，只在后端明确返回未绑定后展示绑定码。

**Tech Stack:** Django 5.2、Django REST Framework、PostgreSQL、Redis、httpx、pytest-django、Taro 4、React 18、TypeScript、Vitest、Ant Design 5、TanStack Query v5

**Spec:** `docs/superpowers/specs/2026-08-30-wechat-openid-session-recovery-design.md`

## Global Constraints

- 客户端永远不能声明可信 `wx_openid`；只提交 `wx.login()` 的一次性 code，由后端换取 OpenID。
- `PatientAppWechatBinding.wx_openid` 唯一，`project_patient` 一对一。
- 新绑定只替换患者端微信绑定与 token，不调用项目级 `unbind`，不删除 `ProjectPatient`、处方或训练数据。
- token TTL 保持 30 天；持久绑定未撤销时允许自动签发新 token。
- 只有 `wechat-session/` 明确返回 `status: unbound` 时，小程序才展示绑定码。
- 历史 `PatientAppSession.wx_openid` 全部视为一次性 code，migration 必须清空，不能据此创建持久绑定。
- 生产身份模式固定为 `wechat`，AppSecret 只存在服务端环境变量；生产缺少 AppID/AppSecret 或使用 `mock` 必须配置检查失败。
- `WECHAT_MINIAPP_AUTH_MODE=mock` 只允许在 DEBUG 环境使用固定 `WECHAT_MINIAPP_MOCK_OPENID`。
- 身份恢复限流固定为每个可信客户端 IP 每 60 秒 60 次；绑定码限流固定为每个可信客户端 IP 每 900 秒 30 次；两者使用共享 Redis。
- 微信 AppSecret、`session_key`、Bearer token、绑定码明文和完整微信临时 code 不得写日志或出现在错误响应中。
- 保留 `backend/config/settings.py` 中本地 Vite 的 `CSRF_TRUSTED_ORIGINS` 默认值。
- 小程序用户可见文案遵循根目录 `CONTEXT.md` 的中性术语。
- 不修改现有演示模式的数据隔离规则。
- 不主动部署或写入真实生产 AppSecret；实施完成后明确列出生产配置前置条件。

---

## 文件结构

### 后端患者端身份

- Modify: `backend/apps/patient_app/models.py` — 持久微信绑定模型与 session 审计字段。
- Create: `backend/apps/patient_app/migrations/0003_add_wechat_binding.py` — 新模型、字段可空和历史伪 OpenID 清理。
- Create: `backend/apps/patient_app/wechat_identity.py` — 微信 code 交换与安全异常边界。
- Modify: `backend/apps/patient_app/services.py` — 持久绑定、自动恢复、换绑、撤销和 token 签发事务。
- Modify: `backend/apps/patient_app/serializers.py` — `wx_code` 请求校验。
- Modify: `backend/apps/patient_app/views.py` — 启动恢复与真实绑定 API 编排。
- Modify: `backend/apps/patient_app/urls.py` — `wechat-session/` 路由。
- Modify: `backend/apps/patient_app/throttles.py` — 共享 Redis 固定窗口基类与两个身份限流器。

### 后端测试与配置

- Create: `backend/apps/patient_app/tests/test_wechat_binding_migration.py` — 历史伪 OpenID 清理 migration 回归。
- Create: `backend/apps/patient_app/tests/test_wechat_identity.py` — `code2Session` 成功与安全失败测试。
- Create: `backend/apps/patient_app/tests/test_wechat_binding_services.py` — 一对一持久绑定和恢复服务测试。
- Modify: `backend/apps/patient_app/tests/test_binding_services.py` — 既有绑定、撤销和 token 认证兼容断言。
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py` — 新请求合同、恢复状态与错误映射。
- Create: `backend/apps/patient_app/tests/test_patient_app_auth_throttles.py` — 两个身份接口共享 Redis 限流测试。
- Modify: `backend/config/environment.py` — 可单测的微信配置校验函数。
- Modify: `backend/config/settings.py` — 微信身份与限流配置。
- Modify: `backend/tests/test_settings.py` — 配置模板、生产 Compose 与安全模式断言。
- Modify: `.env.example` — 本地 mock 示例，不含真实凭据。
- Modify: `deploy/env.production.example` — 生产微信配置空占位。
- Modify: `deploy/docker-compose.prod.yml` — 后端容器环境透传。

### 医生端状态

- Modify: `backend/apps/studies/views.py` — 同时返回持久绑定与活动 session 状态。
- Modify: `backend/apps/studies/tests/test_project_patient_binding_api.py` — 过期 token 下仍可识别并撤销持久绑定。
- Modify: `frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx` — 使用持久绑定判断状态和撤销能力。
- Modify: `frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx` — 持久绑定 UI 回归。

### 小程序

- Create: `miniapp/src/auth/wechatSession.ts` — 获取新微信 code、恢复会话和真实绑定的专用 API 边界。
- Create: `miniapp/src/auth/wechatSession.test.ts` — code 必填、请求载荷与二次取 code 测试。
- Modify: `miniapp/src/pages/bind/index.tsx` — 启动状态机、重试与新绑定流程。
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx` — 现有页面 harness 中的绑定页与演示模式回归。

### 收口文档

- Modify: `specs/patient-rehab-system/changelog.md` — 追加真实 OpenID 登录恢复落地记录。
- Modify: `docs/superpowers/plans/2026-08-30-wechat-openid-session-recovery.md` — 勾选任务并写入实施提交。

---

### Task 1: 建立持久微信绑定模型并清理历史伪 OpenID

**Files:**
- Modify: `backend/apps/patient_app/models.py:28-46`
- Create: `backend/apps/patient_app/migrations/0003_add_wechat_binding.py`
- Create: `backend/apps/patient_app/tests/test_wechat_binding_migration.py`
- Create: `backend/apps/patient_app/tests/test_wechat_binding_services.py`

**Interfaces:**
- Consumes: 现有 `ProjectPatient`、`PatientAppSession`、`UserStampedModel`。
- Produces: `PatientAppWechatBinding(project_patient, wx_openid)`；`PatientAppSession.wx_openid: str | None`。

- [ ] **Step 1: 写模型唯一性失败测试**

在 `test_wechat_binding_services.py` 添加：

```python
import pytest
from django.db import IntegrityError, transaction

from apps.patient_app.models import PatientAppWechatBinding
from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject


def create_second_project_patient(doctor):
    patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900009999",
        primary_doctor=doctor,
    )
    project = StudyProject.objects.create(name="微信绑定测试项目", created_by=doctor)
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    return ProjectPatient.objects.create(project=project, patient=patient, group=group)


@pytest.mark.django_db
def test_wechat_binding_is_unique_on_both_openid_and_project_patient(
    project_patient,
    doctor,
):
    second_project_patient = create_second_project_patient(doctor)
    PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-001",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        PatientAppWechatBinding.objects.create(
            project_patient=second_project_patient,
            wx_openid="openid-001",
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        PatientAppWechatBinding.objects.create(
            project_patient=project_patient,
            wx_openid="openid-002",
        )
```

- [ ] **Step 2: 运行测试确认因模型缺失而失败**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_wechat_binding_services.py::test_wechat_binding_is_unique_on_both_openid_and_project_patient -q
```

Expected: FAIL，导入错误明确指出 `PatientAppWechatBinding` 尚不存在。

- [ ] **Step 3: 添加模型并生成命名 migration**

在 `models.py` 添加：

```python
class PatientAppWechatBinding(UserStampedModel):
    project_patient = models.OneToOneField(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="patient_app_wechat_binding",
    )
    wx_openid = models.CharField(max_length=128, unique=True)

    class Meta:
        ordering = ["-id"]
```

把 `PatientAppSession.wx_openid` 改为：

```python
wx_openid = models.CharField(max_length=128, null=True, blank=True)
```

Run:

```bash
cd backend
python manage.py makemigrations patient_app --name add_wechat_binding
```

Expected: 生成 `0003_add_wechat_binding.py`，包含新模型和 `wx_openid` 字段变更。

- [ ] **Step 4: 在 migration 中显式清空历史伪 OpenID**

在 `AlterField` 之后加入：

```python
def clear_legacy_session_openids(apps, schema_editor):
    PatientAppSession = apps.get_model("patient_app", "PatientAppSession")
    PatientAppSession.objects.exclude(wx_openid__isnull=True).update(wx_openid=None)


class Migration(migrations.Migration):
    # dependencies 保留 makemigrations 生成值
    operations = [
        # AlterField(wx_openid, null=True, blank=True) 必须在前
        migrations.RunPython(clear_legacy_session_openids, migrations.RunPython.noop),
        # CreateModel(PatientAppWechatBinding) 保留生成内容
    ]
```

不得尝试从历史值创建 `PatientAppWechatBinding`。

- [ ] **Step 5: 写 migration 回归测试并观察通过**

在 `test_wechat_binding_migration.py` 使用 `MigrationExecutor` 从 `patient_app.0002_alter_patientappbindingcode_code_hash` 迁移到 `patient_app.0003_add_wechat_binding`。测试先用历史 apps 创建 `wx_openid="temporary-login-code"` 的 session，再断言：

```python
assert migrated_session.wx_openid is None
assert PatientAppWechatBinding.objects.count() == 0
```

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_wechat_binding_migration.py apps/patient_app/tests/test_wechat_binding_services.py -q
python manage.py makemigrations patient_app --check --dry-run
```

Expected: 测试 PASS；migration 检查输出 `No changes detected`。

- [ ] **Step 6: 提交模型与 migration**

```bash
git add backend/apps/patient_app/models.py backend/apps/patient_app/migrations/0003_add_wechat_binding.py backend/apps/patient_app/tests/test_wechat_binding_migration.py backend/apps/patient_app/tests/test_wechat_binding_services.py
git commit -m "feat(小程序): 建立持久微信账号绑定"
```

---

### Task 2: 实现服务端微信 code2Session 与安全配置

**Files:**
- Create: `backend/apps/patient_app/wechat_identity.py`
- Create: `backend/apps/patient_app/tests/test_wechat_identity.py`
- Modify: `backend/config/environment.py`
- Modify: `backend/config/settings.py:163-177`
- Modify: `backend/tests/test_settings.py:120-170`
- Modify: `.env.example`
- Modify: `deploy/env.production.example`
- Modify: `deploy/docker-compose.prod.yml:3-43`

**Interfaces:**
- Consumes: `httpx>=0.27,<1.0`、Django settings、当前 AppID `wx095c9a6c41b60112` 的服务端凭据。
- Produces: `exchange_login_code(wx_code: str, *, transport: httpx.BaseTransport | None = None) -> str`；`WechatLoginCodeInvalid`；`WechatIdentityUnavailable`。

- [ ] **Step 1: 写微信身份提供器失败测试**

在 `test_wechat_identity.py` 用 `httpx.MockTransport` 覆盖：

```python
@override_settings(
    WECHAT_MINIAPP_AUTH_MODE="wechat",
    WECHAT_MINIAPP_APP_ID="wx-test",
    WECHAT_MINIAPP_APP_SECRET="secret-test",
)
def test_exchange_login_code_returns_only_openid():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"openid": "openid-001", "session_key": "private-session-key"},
            request=request,
        )
    )

    assert exchange_login_code("single-use-code", transport=transport) == "openid-001"
```

另写参数化测试覆盖微信 `40029`、`45011`、`-1`、非 JSON、缺少 OpenID、HTTP 500 和 `httpx.TimeoutException`；断言异常字符串不包含 `secret-test`、`private-session-key` 或 `single-use-code`。

- [ ] **Step 2: 运行提供器测试确认失败**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_wechat_identity.py -q
```

Expected: FAIL，模块 `apps.patient_app.wechat_identity` 尚不存在。

- [ ] **Step 3: 实现身份提供器最小边界**

`wechat_identity.py` 使用以下公开结构：

```python
class WechatLoginCodeInvalid(Exception):
    pass


class WechatIdentityUnavailable(Exception):
    pass


def exchange_login_code(wx_code: str, *, transport=None) -> str:
    if settings.WECHAT_MINIAPP_AUTH_MODE == "mock":
        return settings.WECHAT_MINIAPP_MOCK_OPENID

    timeout = httpx.Timeout(
        connect=settings.WECHAT_MINIAPP_CONNECT_TIMEOUT_SECONDS,
        read=settings.WECHAT_MINIAPP_READ_TIMEOUT_SECONDS,
        write=settings.WECHAT_MINIAPP_READ_TIMEOUT_SECONDS,
        pool=settings.WECHAT_MINIAPP_CONNECT_TIMEOUT_SECONDS,
    )
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.get(
                "https://api.weixin.qq.com/sns/jscode2session",
                params={
                    "appid": settings.WECHAT_MINIAPP_APP_ID,
                    "secret": settings.WECHAT_MINIAPP_APP_SECRET,
                    "js_code": wx_code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise WechatIdentityUnavailable("微信身份服务不可用") from None

    if payload.get("errcode") == 40029:
        raise WechatLoginCodeInvalid("微信登录凭证无效")
    openid = payload.get("openid")
    if payload.get("errcode") not in (None, 0) or not isinstance(openid, str):
        raise WechatIdentityUnavailable("微信身份服务不可用")
    if not openid or len(openid) > 128:
        raise WechatIdentityUnavailable("微信身份服务不可用")
    return openid
```

不得在异常消息中拼接 request URL、响应 body 或原始异常文本。

- [ ] **Step 4: 写配置校验失败测试**

在 `backend/tests/test_settings.py` 对 `config.environment.validate_wechat_miniapp_settings` 添加：

```python
@pytest.mark.parametrize(
    "kwargs",
    [
        {"debug": False, "auth_mode": "mock", "app_id": "wx", "app_secret": "secret", "mock_openid": "local"},
        {"debug": False, "auth_mode": "wechat", "app_id": "", "app_secret": "secret", "mock_openid": ""},
        {"debug": False, "auth_mode": "wechat", "app_id": "wx", "app_secret": "", "mock_openid": ""},
        {"debug": True, "auth_mode": "mock", "app_id": "", "app_secret": "", "mock_openid": ""},
    ],
)
def test_invalid_wechat_identity_settings_fail_closed(kwargs):
    with pytest.raises(ImproperlyConfigured):
        validate_wechat_miniapp_settings(**kwargs)
```

- [ ] **Step 5: 实现配置、模板和 Compose 透传**

在 `settings.py` 定义固定默认值：

```python
WECHAT_MINIAPP_AUTH_MODE = os.getenv(
    "WECHAT_MINIAPP_AUTH_MODE", "mock" if DEBUG else "wechat"
)
WECHAT_MINIAPP_APP_ID = os.getenv("WECHAT_MINIAPP_APP_ID", "")
WECHAT_MINIAPP_APP_SECRET = os.getenv("WECHAT_MINIAPP_APP_SECRET", "")
WECHAT_MINIAPP_MOCK_OPENID = os.getenv("WECHAT_MINIAPP_MOCK_OPENID", "local-openid")
WECHAT_MINIAPP_CONNECT_TIMEOUT_SECONDS = float(
    os.getenv("WECHAT_MINIAPP_CONNECT_TIMEOUT_SECONDS", "5")
)
WECHAT_MINIAPP_READ_TIMEOUT_SECONDS = float(
    os.getenv("WECHAT_MINIAPP_READ_TIMEOUT_SECONDS", "10")
)
PATIENT_APP_WECHAT_SESSION_RATE_LIMIT_REQUESTS = 60
PATIENT_APP_WECHAT_SESSION_RATE_LIMIT_WINDOW_SECONDS = 60
PATIENT_APP_BIND_RATE_LIMIT_REQUESTS = 30
PATIENT_APP_BIND_RATE_LIMIT_WINDOW_SECONDS = 900
PATIENT_APP_AUTH_RATE_LIMIT_REDIS_URL = REDIS_URL
```

`config/environment.py` 添加的校验函数使用确定逻辑：

```python
def validate_wechat_miniapp_settings(
    *,
    debug: bool,
    auth_mode: str,
    app_id: str,
    app_secret: str,
    mock_openid: str,
) -> None:
    if auth_mode not in {"wechat", "mock"}:
        raise ImproperlyConfigured("WECHAT_MINIAPP_AUTH_MODE 必须是 wechat 或 mock")
    if auth_mode == "mock" and (not debug or not mock_openid):
        raise ImproperlyConfigured("微信模拟身份仅允许在 DEBUG 环境使用")
    if not debug and auth_mode != "wechat":
        raise ImproperlyConfigured("生产环境必须使用微信真实身份模式")
    if auth_mode == "wechat" and (not app_id or not app_secret):
        raise ImproperlyConfigured("微信真实身份模式缺少 AppID 或 AppSecret")
```

调用：

```python
validate_wechat_miniapp_settings(
    debug=DEBUG,
    auth_mode=WECHAT_MINIAPP_AUTH_MODE,
    app_id=WECHAT_MINIAPP_APP_ID,
    app_secret=WECHAT_MINIAPP_APP_SECRET,
    mock_openid=WECHAT_MINIAPP_MOCK_OPENID,
)
```

并校验两个 timeout 均大于 0。模板值固定为：本地 `AUTH_MODE=mock`、`MOCK_OPENID=local-openid`；生产 `AUTH_MODE=wechat` 且 AppID/AppSecret 为空占位。Compose 使用 `${WECHAT_MINIAPP_APP_ID}` 与 `${WECHAT_MINIAPP_APP_SECRET}` 无默认值，防止静默空配置。

- [ ] **Step 6: 运行提供器与配置测试**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_wechat_identity.py tests/test_settings.py -q
```

Expected: PASS；任何失败输出均不包含测试密钥或临时 code。

- [ ] **Step 7: 提交微信身份边界与配置**

```bash
git add backend/apps/patient_app/wechat_identity.py backend/apps/patient_app/tests/test_wechat_identity.py backend/config/environment.py backend/config/settings.py backend/tests/test_settings.py .env.example deploy/env.production.example deploy/docker-compose.prod.yml
git commit -m "feat(小程序): 接入服务端微信身份交换"
```

---

### Task 3: 实现一对一换绑、自动恢复和静默迁移服务

**Files:**
- Modify: `backend/apps/patient_app/services.py:1-148`
- Modify: `backend/apps/patient_app/tests/test_wechat_binding_services.py`
- Modify: `backend/apps/patient_app/tests/test_binding_services.py`

**Interfaces:**
- Consumes: `PatientAppWechatBinding`、可信 `wx_openid`、可选明文患者 token。
- Produces: `PatientAppSessionRecovery`；`recover_patient_app_session(*, wx_openid: str, presented_token: str | None) -> PatientAppSessionRecovery`；`PatientAppBindingConflict`；保持 `bind_project_patient_with_code(code: str, wx_openid: str) -> tuple[str, PatientAppSession]` 供可信后端调用。

- [ ] **Step 1: 写恢复与换绑失败测试**

在 `test_wechat_binding_services.py` 添加以下独立用例；每一项都使用函数名中写明的场景，不合并成一个大测试：

- `test_bound_openid_without_token_receives_new_session`：已有持久绑定、无 token，断言返回新 token 和目标 session。
- `test_expired_token_is_replaced_from_persistent_openid_binding`：旧 token 已过期，断言旧 session 失效且新 session TTL 为 30 天。
- `test_valid_matching_token_is_kept_and_legacy_openid_is_backfilled`：有效 token 与绑定指向同一账号，断言 `token is None` 且原 session 补写真正 OpenID。
- `test_valid_legacy_token_claims_unbound_openid`：两侧均无持久绑定，断言创建绑定且保留旧 token。
- `test_persistent_openid_binding_wins_over_conflicting_legacy_token`：OpenID 指向账号 A、token 指向账号 B，断言恢复 A 且不改写绑定。
- `test_legacy_token_cannot_take_project_patient_bound_to_other_openid`：目标账号已有其他 OpenID，断言返回 `unbound`。
- `test_unbound_openid_without_valid_token_returns_unbound`：无绑定、无有效 token，断言 `session is None`、`token is None`。
- `test_binding_new_project_replaces_both_sides_and_deactivates_sessions`：显式绑定替换 OpenID 与目标账号两侧关系，断言旧 session 全部停用。
- `test_revoke_deletes_wechat_binding_and_deactivates_sessions`：撤销后持久绑定不存在，活动 session 数为 0。
- `test_binding_failure_rolls_back_code_consumption_and_relationship_changes`：在新关系创建处注入 `IntegrityError`，断言绑定码 `used_at is None` 且旧绑定保持不变。

首个恢复测试使用以下完整核心断言，其余测试沿用相同 fixture 和结果字段：

```python
result = recover_patient_app_session(
    wx_openid="openid-001",
    presented_token=None,
)
assert result.status == "authenticated"
assert result.token
assert result.session.project_patient == project_patient
```

换绑测试必须在调用前创建两个 `ProjectPatient`、两个 `PatientAppWechatBinding` 和活动 session，并在调用后断言旧绑定已删除、旧 session 均失效、研究对象仍存在。

- [ ] **Step 2: 运行服务测试确认失败**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_wechat_binding_services.py apps/patient_app/tests/test_binding_services.py -q
```

Expected: FAIL，缺少恢复类型和持久绑定行为。

- [ ] **Step 3: 抽取 token 查找与签发 helper**

在 `services.py` 添加私有 helper：

```python
def _active_session_for_token(token: str | None, now) -> PatientAppSession | None:
    if not token:
        return None
    return PatientAppSession.objects.select_related("project_patient__patient").filter(
        token_hash=hash_patient_app_token(token),
        is_active=True,
        expires_at__gt=now,
    ).first()


def _create_patient_app_session(*, project_patient, wx_openid, now):
    token = secrets.token_urlsafe(32)
    session = PatientAppSession.objects.create(
        project_patient=project_patient,
        patient=project_patient.patient,
        wx_openid=wx_openid,
        token_hash=hash_patient_app_token(token),
        expires_at=now + SESSION_TTL,
    )
    return token, session
```

helper 只接收已经验证的 OpenID，不调用微信网络。

- [ ] **Step 4: 实现恢复结果和优先级**

添加：

```python
@dataclass(frozen=True)
class PatientAppSessionRecovery:
    status: Literal["authenticated", "unbound"]
    token: str | None
    session: PatientAppSession | None


class PatientAppBindingConflict(Exception):
    pass
```

`recover_patient_app_session` 严格按 spec §7.1：持久 OpenID 绑定优先；同账号有效 token 返回 `token=None`；缺失/过期 token 签发新 token；只有两侧都无持久绑定时才允许有效旧 token 静默 claim。创建/claim 使用 `transaction.atomic()`、`select_for_update()` 和唯一约束；`IntegrityError` 转成 `PatientAppBindingConflict`。

- [ ] **Step 5: 扩展绑定与撤销事务**

更新 `bind_project_patient_with_code`：在消费绑定码的原事务内锁定目标与被替换关系，删除两侧 `PatientAppWechatBinding`，停用两侧 session，再创建唯一持久绑定和新 session。更新 `revoke_project_patient_binding`：

```python
PatientAppWechatBinding.objects.select_for_update().filter(
    project_patient=locked_project_patient
).delete()
```

不得调用 studies 的项目级解绑服务。

- [ ] **Step 6: 运行患者端服务回归**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_wechat_binding_services.py apps/patient_app/tests/test_binding_services.py -q
```

Expected: PASS；既有绑定码哈希、15 分钟过期和 token 认证测试继续通过。

- [ ] **Step 7: 提交持久绑定服务**

```bash
git add backend/apps/patient_app/services.py backend/apps/patient_app/tests/test_wechat_binding_services.py backend/apps/patient_app/tests/test_binding_services.py
git commit -m "feat(小程序): 支持微信账号恢复与唯一换绑"
```

---

### Task 4: 暴露启动恢复 API 并为公开身份接口限流

**Files:**
- Modify: `backend/apps/patient_app/serializers.py:38-70`
- Modify: `backend/apps/patient_app/views.py:1-215`
- Modify: `backend/apps/patient_app/urls.py:1-32`
- Modify: `backend/apps/patient_app/throttles.py`
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py:1-115`
- Create: `backend/apps/patient_app/tests/test_patient_app_auth_throttles.py`
- Modify: `backend/apps/patient_app/tests/test_demo_motion_video_throttle.py`

**Interfaces:**
- Consumes: `exchange_login_code`、`recover_patient_app_session`、`bind_project_patient_with_code`。
- Produces: `POST /api/patient-app/wechat-session/`；`POST /api/patient-app/bind/` 的 `{code, wx_code}` 合同；`PatientAppWechatSessionRateThrottle`；`PatientAppBindRateThrottle`。

- [ ] **Step 1: 写 API 合同失败测试**

在 `test_patient_app_api.py` 用 monkeypatch 固定身份交换：

```python
monkeypatch.setattr(
    "apps.patient_app.views.exchange_login_code",
    lambda wx_code: "openid-001",
)
```

添加以下明确用例：

- `test_wechat_session_returns_authenticated_and_new_token_for_bound_openid`：创建持久绑定，POST `{"wx_code": "wx-code"}`，断言 `200`、`status == "authenticated"`、返回新 token。
- `test_wechat_session_returns_unbound_without_binding_or_valid_legacy_token`：无绑定，断言 `200` 和精确 JSON `{"status": "unbound"}`。
- `test_wechat_session_ignores_invalid_optional_bearer_and_still_restores_openid`：Header 为 `Bearer invalid-token` 且 OpenID 已绑定，断言仍返回 `authenticated` 而非 `401`。
- `test_wechat_session_migrates_valid_legacy_token`：携带既有有效 token，断言创建持久绑定并返回 `token: null`。
- `test_bind_api_requires_wx_code_and_ignores_forged_wx_openid`：缺少 `wx_code` 得 `400`；同时提交伪造 `wx_openid` 时，落库值仍为 monkeypatch 返回的 `openid-001`。
- `test_invalid_wechat_code_returns_safe_400`：provider 抛 `WechatLoginCodeInvalid`，断言安全固定文案。
- `test_unavailable_wechat_identity_returns_safe_503`：provider 抛 `WechatIdentityUnavailable`，断言响应不含上游详情。
- `test_binding_conflict_returns_safe_409`：service 抛 `PatientAppBindingConflict`，断言安全固定文案。

恢复接口的无效 Bearer 测试必须断言不是 `401`，而是继续按 OpenID 返回 `authenticated` 或 `unbound`。

- [ ] **Step 2: 运行 API 测试确认失败**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_patient_app_api.py -q
```

Expected: FAIL，`wechat-session/` 为 404，旧 bind serializer 仍要求 `wx_openid`。

- [ ] **Step 3: 添加 serializer 与容错旧 token 解析**

定义：

```python
class WechatCodeField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(min_length=1, max_length=128, trim_whitespace=False, **kwargs)


class PatientAppWechatSessionSerializer(serializers.Serializer):
    wx_code = WechatCodeField()


class PatientAppBindSerializer(serializers.Serializer):
    code = BindingCodeField()
    wx_code = WechatCodeField()
```

在 view 内只接受格式正确的 `Bearer <token>` 作为 `presented_token`；错误格式视为 `None`，不能调用常规 `PatientAppTokenAuthentication` 提前抛 `401`。

- [ ] **Step 4: 实现恢复与绑定 view 编排**

`PatientAppWechatSessionView.post`：校验 `wx_code` → 调用 `exchange_login_code` → 调用恢复服务 → 序列化 `authenticated/unbound`。`PatientAppBindView.post`：先在事务外交换 OpenID，再把可信 OpenID 传给现有服务。异常固定映射：

```python
WechatLoginCodeInvalid -> 400 "微信登录凭证无效，请重试"
PatientAppBindingConflict -> 409 "账号绑定发生冲突，请重试"
WechatIdentityUnavailable -> 503 "微信登录服务暂时不可用，请稍后重试"
```

路由添加：

```python
path("wechat-session/", PatientAppWechatSessionView.as_view(), name="patient-app-wechat-session")
```

- [ ] **Step 5: 先写身份限流失败测试**

在 `test_patient_app_auth_throttles.py` 使用与 `test_demo_motion_video_throttle.py` 相同的 `FakeRedis`，断言：

```python
assert first_60_session_requests_are_not_throttled
assert session_request_61.status_code == 429
assert first_30_bind_requests_are_not_throttled
assert bind_request_31.status_code == 429
assert redis_keys_do_not_contain_plain_ip_or_credentials
```

mock view 下游，确保限流测试不访问微信或消费真实绑定码。

同时扩展 `test_patient_app_api.py` 的 autouse fixture，对以下三个类注入同一个测试 Redis，保证 API 测试不会访问本机 Redis：

```python
for throttle_class in (
    DemoMotionVideoRateThrottle,
    PatientAppWechatSessionRateThrottle,
    PatientAppBindRateThrottle,
):
    monkeypatch.setattr(
        throttle_class,
        "redis_client_factory",
        staticmethod(lambda _url, redis=redis: redis),
    )
```

- [ ] **Step 6: 抽取共享 Redis 固定窗口限流基类**

在不改变 `DemoMotionVideoRateThrottle` 行为的前提下抽取：

```python
class PatientAppAuthRateLimitUnavailable(APIException):
    status_code = 503
    default_detail = "登录服务繁忙，请稍后重试"
    default_code = "patient_app_auth_rate_limit_unavailable"


class RedisFixedWindowRateThrottle(BaseThrottle):
    key_namespace: str
    redis_url_setting: str
    requests_setting: str
    window_setting: str
    unavailable_exception_class: type[APIException]


class PatientAppWechatSessionRateThrottle(RedisFixedWindowRateThrottle):
    key_namespace = "patient-app-wechat-session"
    redis_url_setting = "PATIENT_APP_AUTH_RATE_LIMIT_REDIS_URL"
    requests_setting = "PATIENT_APP_WECHAT_SESSION_RATE_LIMIT_REQUESTS"
    window_setting = "PATIENT_APP_WECHAT_SESSION_RATE_LIMIT_WINDOW_SECONDS"
    unavailable_exception_class = PatientAppAuthRateLimitUnavailable


class PatientAppBindRateThrottle(RedisFixedWindowRateThrottle):
    key_namespace = "patient-app-bind"
    redis_url_setting = "PATIENT_APP_AUTH_RATE_LIMIT_REDIS_URL"
    requests_setting = "PATIENT_APP_BIND_RATE_LIMIT_REQUESTS"
    window_setting = "PATIENT_APP_BIND_RATE_LIMIT_WINDOW_SECONDS"
    unavailable_exception_class = PatientAppAuthRateLimitUnavailable
```

两个 view 分别声明对应 `throttle_classes`。Redis 不可用时 fail closed 为安全 `503`，不得暴露 Redis URL。

- [ ] **Step 7: 运行 API、限流与演示视频回归**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_patient_app_api.py apps/patient_app/tests/test_patient_app_auth_throttles.py apps/patient_app/tests/test_demo_motion_video_throttle.py -q
```

Expected: PASS；既有演示视频第 61 次拒绝和安全 503 行为不变。

- [ ] **Step 8: 提交 API 与限流**

```bash
git add backend/apps/patient_app/serializers.py backend/apps/patient_app/views.py backend/apps/patient_app/urls.py backend/apps/patient_app/throttles.py backend/apps/patient_app/tests/test_patient_app_api.py backend/apps/patient_app/tests/test_patient_app_auth_throttles.py backend/apps/patient_app/tests/test_demo_motion_video_throttle.py
git commit -m "feat(小程序): 增加微信启动恢复接口"
```

---

### Task 5: 让医生端按持久绑定展示并撤销

**Files:**
- Modify: `backend/apps/studies/views.py:309-381`
- Modify: `backend/apps/studies/tests/test_project_patient_binding_api.py:58-117`
- Modify: `frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx:13-96`
- Modify: `frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx`

**Interfaces:**
- Consumes: `PatientAppWechatBinding` 和现有活动 session 查询。
- Produces: `binding-status` 新字段 `has_wechat_binding: boolean`、`wechat_bound_at: string | null`；Web 端 `isBound = has_wechat_binding || has_active_session`。

- [ ] **Step 1: 写医生端状态 API 失败测试**

扩展 `test_project_patient_binding_api.py`：创建持久绑定和已过期 session，断言：

```python
assert response.data["has_wechat_binding"] is True
assert response.data["wechat_bound_at"] is not None
assert response.data["has_active_session"] is False
assert response.data["active_session_expires_at"] is None
```

随后调用现有 `revoke-binding/`，断言持久绑定删除、session 停用、`ProjectPatient` 仍存在。

- [ ] **Step 2: 运行后端状态测试确认失败**

Run:

```bash
cd backend
pytest apps/studies/tests/test_project_patient_binding_api.py -q
```

Expected: FAIL，响应缺少 `has_wechat_binding`。

- [ ] **Step 3: 扩展绑定状态 payload**

在 `_binding_status_payload` 查询 `project_patient.patient_app_wechat_binding`，返回：

```python
"has_wechat_binding": wechat_binding is not None,
"wechat_bound_at": wechat_binding.created_at.isoformat() if wechat_binding else None,
```

保留现有 session 字段及其原语义。

- [ ] **Step 4: 写 Web 端持久绑定失败测试**

在 `ProjectPatientBindingCard.test.tsx` 添加：

```tsx
it("token 过期后仍按持久微信绑定显示并允许撤销", async () => {
  mockGet.mockResolvedValue({
    data: {
      has_wechat_binding: true,
      wechat_bound_at: "2026-08-30T10:00:00+08:00",
      has_active_session: false,
      has_active_binding_code: false,
      binding_code_expires_at: null,
      last_bound_at: null,
      active_session_expires_at: null,
    },
  });
  renderCard();
  expect(await screen.findByText("已绑定")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "撤销绑定" })).toBeEnabled();
});
```

另保留“仅有效旧 session、尚无持久绑定”仍显示已绑定的迁移期测试。

- [ ] **Step 5: 更新 Web 状态判断但不改布局**

扩展类型并使用：

```tsx
const isBound = Boolean(status?.has_wechat_binding || status?.has_active_session);
const canRevoke = Boolean(
  status?.has_wechat_binding || status?.has_active_session || status?.has_active_binding_code,
);
```

“最近绑定时间”显示 `wechat_bound_at ?? last_bound_at`；其他布局和按钮流程不变。

- [ ] **Step 6: 运行后端与 Web 定向测试**

Run:

```bash
cd backend
pytest apps/studies/tests/test_project_patient_binding_api.py -q
cd ../frontend
npm run test -- ProjectPatientBindingCard.test.tsx
```

Expected: 两组测试 PASS。

- [ ] **Step 7: 提交医生端状态适配**

```bash
git add backend/apps/studies/views.py backend/apps/studies/tests/test_project_patient_binding_api.py frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx
git commit -m "fix(患者绑定): 按持久微信关系展示状态"
```

---

### Task 6: 实现小程序启动恢复状态机与真实换绑请求

**Files:**
- Create: `miniapp/src/auth/wechatSession.ts`
- Create: `miniapp/src/auth/wechatSession.test.ts`
- Modify: `miniapp/src/pages/bind/index.tsx:1-99`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx:3540-3810`

**Interfaces:**
- Consumes: `Taro.login()`、现有 `request<T>()`、本地 patient token。
- Produces: `recoverWechatSession() -> Promise<WechatSessionResponse>`；`bindWechatAccount(code: string) -> Promise<BindResponse>`；绑定页 `checking | unbound | error` 启动状态。

- [ ] **Step 1: 写专用微信会话 API 失败测试**

在 `wechatSession.test.ts` mock Taro 和 `request`，添加：

```typescript
it('恢复与真实绑定每次都获取新的微信 code', async () => {
  taroMock.login
    .mockResolvedValueOnce({ code: 'startup-code' })
    .mockResolvedValueOnce({ code: 'binding-code-login' })
  requestMock
    .mockResolvedValueOnce({ status: 'unbound' })
    .mockResolvedValueOnce({ token: 'token', project_patient_id: 1, patient: {}, project: {} })

  await recoverWechatSession()
  await bindWechatAccount('1234')

  expect(requestMock).toHaveBeenNthCalledWith(1, '/patient-app/wechat-session/', {
    method: 'POST', data: { wx_code: 'startup-code' }
  })
  expect(requestMock).toHaveBeenNthCalledWith(2, '/patient-app/bind/', {
    method: 'POST', data: { code: '1234', wx_code: 'binding-code-login' }
  })
})
```

另测 `Taro.login()` 未返回 code 时抛出中性、安全错误，且不发 API 请求。

- [ ] **Step 2: 运行专用 API 测试确认失败**

Run:

```bash
cd miniapp
npx vitest run src/auth/wechatSession.test.ts
```

Expected: FAIL，模块尚不存在。

- [ ] **Step 3: 实现专用身份 API 模块**

定义：

```typescript
import Taro from '@tarojs/taro'

import { request } from '../api/client'
import type { BoundIdentity } from '../types/patientApp'

export type WechatSessionResponse =
  | { status: 'unbound' }
  | ({ status: 'authenticated'; token: string | null } & BoundIdentity)

export type BindResponse = BoundIdentity & { token: string }

async function freshWxCode(): Promise<string> {
  const result = await Taro.login()
  if (!result.code) throw new Error('微信登录失败，请重试')
  return result.code
}

export async function recoverWechatSession(): Promise<WechatSessionResponse> {
  const wxCode = await freshWxCode()
  return request<WechatSessionResponse>('/patient-app/wechat-session/', {
    method: 'POST',
    data: { wx_code: wxCode }
  })
}

export async function bindWechatAccount(code: string): Promise<BindResponse> {
  const wxCode = await freshWxCode()
  return request<BindResponse>('/patient-app/bind/', {
    method: 'POST',
    data: { code, wx_code: wxCode }
  })
}
```

从绑定页删除本地 `BindResponse` 类型和现有 `login.code || 'dev-openid'` 回退，改为导入 `bindWechatAccount`、`recoverWechatSession`。

- [ ] **Step 4: 写绑定页状态机失败测试**

在现有 `pages.test.tsx` harness 中添加或改写以下测试：

- `启动检查中不显示绑定码输入`：初始渲染断言含“正在检查登录状态”，`findAll(page.element, (element) => element.type === 'Input')` 长度为 0。
- `只有后端明确 unbound 后才显示绑定码`：恢复请求返回 `{"status":"unbound"}`，触发 show callback 并 rerender 后断言 Input 存在。
- `清缓存后按 OpenID 恢复并保存新 token`：初始 storage 为空，响应带 `restored-token`，断言 storage 与首页跳转。
- `有效旧 token 静默迁移时保留原 token`：storage 预置 `legacy-token`，响应 `token: null`，断言没有覆盖 token。
- `登录检查失败只显示重试且不显示绑定输入`：恢复请求 reject，断言“重新检查”存在、Input 不存在。
- `点击重新检查后可从 error 进入 unbound`：第一次 reject、第二次返回 unbound，断言 `Taro.login` 调用两次。
- `普通绑定启动和提交使用两个不同微信 code`：启动使用 `startup-code`，提交使用 `binding-code-login`，断言两个请求载荷不同。
- `演示码在 unbound 状态仍不请求真实绑定 API`：先完成 unbound 检查，再提交 `8888`，断言只调用启动恢复请求。

每个测试都显式触发 `taroHarness.showCallbacks[0]()`，等待 promise 后 `page.rerender()`，不能依赖初始渲染直接出现 Input。

- [ ] **Step 5: 实现绑定页状态机**

核心状态：

```typescript
type LoginCheckState = 'checking' | 'unbound' | 'error'
const [loginCheckState, setLoginCheckState] = useState<LoginCheckState>('checking')

async function checkExistingBinding() {
  setLoginCheckState('checking')
  setError('')
  try {
    const body = await recoverWechatSession()
    if (body.status === 'unbound') {
      clearPatientAppToken()
      setLoginCheckState('unbound')
      return
    }
    if (body.token) setPatientAppToken(body.token)
    Taro.redirectTo({ url: '/pages/home/index' })
  } catch (err) {
    setError(err instanceof Error ? err.message : '登录检查失败，请重试')
    setLoginCheckState('error')
  }
}
```

`checking` 渲染“正在检查登录状态”；`error` 渲染安全错误和“重新检查”按钮；只有 `unbound` 渲染现有四格输入。真实提交调用 `bindWechatAccount`，演示码仍先走本地 `startDemoSession()`。

- [ ] **Step 6: 运行小程序定向测试与类型检查**

Run:

```bash
cd miniapp
npx vitest run src/auth/wechatSession.test.ts src/pages/shoulder-press/pages.test.tsx
npx tsc --noEmit
```

Expected: PASS，无 TypeScript 错误。

- [ ] **Step 7: 提交小程序登录状态机**

```bash
git add miniapp/src/auth/wechatSession.ts miniapp/src/auth/wechatSession.test.ts miniapp/src/pages/bind/index.tsx miniapp/src/pages/shoulder-press/pages.test.tsx
git commit -m "fix(小程序): 清缓存后按微信身份恢复登录"
```

---

### Task 7: 全链路验证、安全检查与计划收口

**Files:**
- Modify: `specs/patient-rehab-system/changelog.md`
- Modify: `docs/superpowers/plans/2026-08-30-wechat-openid-session-recovery.md`

**Interfaces:**
- Consumes: Tasks 1–6 的完整实现。
- Produces: 可部署代码、完整验证证据、生产配置清单和可追溯执行记录。

- [ ] **Step 1: 运行后端全量验证**

Run:

```bash
cd backend
pytest
python manage.py makemigrations --check --dry-run
ruff check .
```

Expected: pytest 全量 PASS；无缺失 migration；ruff 无错误。

- [ ] **Step 2: 运行小程序全量验证与生产构建**

Run:

```bash
cd miniapp
npm test
npx tsc --noEmit
TARO_APP_CONFIG_ENV=production TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api npm run build:weapp:prod
```

Expected: Vitest 全量 PASS；TypeScript 无错误；微信生产构建退出码 0。

- [ ] **Step 3: 运行 Web 管理端全量验证**

Run:

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Expected: 测试、lint 和构建全部通过；现有 warning 必须单独列出，不能冒充本次新增错误。

- [ ] **Step 4: 执行敏感信息与合同静态检查**

Run:

```bash
rg -n "login\.code \|\| 'dev-openid'|data: \{ code: normalizedCode, wx_openid|WECHAT_MINIAPP_APP_SECRET=.+" backend miniapp .env.example deploy --glob '!**/node_modules/**' --glob '!**/dist/**'
rg -n "wx_openid" miniapp/src --glob '!**/*.test.*'
git diff --check
```

Expected: 第一条不命中旧回退、旧请求合同或非空示例密钥；第二条不命中客户端业务源码；`git diff --check` 通过。测试 fixture 中使用虚构 `openid-*` 允许保留。

- [ ] **Step 5: 核对生产配置前置条件但不写真实密钥**

确认 `WECHAT_MINIAPP_AUTH_MODE` 精确等于 `wechat`，`WECHAT_MINIAPP_APP_ID` 精确等于 `wx095c9a6c41b60112`，并由生产密钥管理系统向 `WECHAT_MINIAPP_APP_SECRET` 注入非空值。核对 AppSecret 时只检查“已设置”，不输出变量内容。

不得读取、打印或提交真实 AppSecret。若生产环境尚未注入，实施可标记“代码完成、发布被外部配置阻塞”，不得宣称线上自动恢复已生效。

- [ ] **Step 6: 追加 changelog 并回填执行记录**

在 `specs/patient-rehab-system/changelog.md` 末尾追加 2026-08-30 条目，包含：真实 OpenID 服务端交换、持久一对一绑定、缓存/token 丢失恢复、旧 token 静默迁移、医生端持久状态。不得修改历史条目。

先运行 `git rev-parse --short HEAD` 取得 Task 6 的实际七位提交号，再在本计划顶部追加一行执行记录，写明 2026-08-30、Codex、Tasks 1–7 已落地、该命令返回的原样提交号，以及后端、小程序、Web 验证均通过。不得写尖括号占位文本。

把实际完成的 `[ ]` 改为 `[x]`，不能提前勾选失败或未运行步骤。

- [ ] **Step 7: 提交收口记录**

```bash
git add specs/patient-rehab-system/changelog.md docs/superpowers/plans/2026-08-30-wechat-openid-session-recovery.md
git commit -m "docs(小程序): 记录微信身份恢复落地结果"
```

- [ ] **Step 8: 使用完成前验证 skill 复核最终状态**

执行 `superpowers:verification-before-completion`，重新读取最后一次验证输出并运行：

```bash
git status --short
git log --oneline -8
```

Expected: 除用户明确要求忽略的 `.风格复制模式.swn` 外无未提交实现改动；最近提交按 Task 1–7 顺序可追溯。不要 push、部署或写入生产密钥，除非用户另行明确授权。
