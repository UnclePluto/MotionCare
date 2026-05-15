# 微信小程序患者日常工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增微信小程序患者端一期：患者通过绑定码绑定单个项目患者身份，在小程序里查看当前处方、本周训练进度、进入单动作训练、查看动作历史并填报今日健康数据。

**Architecture:** 后端新增 `apps.patient_app` 作为患者端身份、绑定码、token 鉴权和聚合 API 边界；小程序接口只从 token 推导 `ProjectPatient`，不信任前端传入的患者或项目 ID。医生后台继续使用现有 session + CSRF，并在 `ProjectPatient` 维度新增绑定码生成、状态查看和撤销动作；小程序作为根目录 `miniapp/` 下的 Taro + React + TypeScript 独立工程。

**Tech Stack:** Django 5 + DRF + pytest-django；React 18 + Ant Design 5 + TanStack Query v5；Taro + React + TypeScript（初始化和 weapp 构建命令参考 Taro 官方文档：https://docs.taro.zone/en/docs/GETTING-STARTED/）。

---

## File Structure

### Backend

- Create: `backend/apps/patient_app/__init__.py`
- Create: `backend/apps/patient_app/apps.py`
- Create: `backend/apps/patient_app/models.py`
- Create: `backend/apps/patient_app/services.py`
- Create: `backend/apps/patient_app/authentication.py`
- Create: `backend/apps/patient_app/serializers.py`
- Create: `backend/apps/patient_app/views.py`
- Create: `backend/apps/patient_app/urls.py`
- Create: `backend/apps/patient_app/tests/test_binding_services.py`
- Create: `backend/apps/patient_app/tests/test_patient_app_api.py`
- Modify: `backend/config/settings.py`
- Modify: `backend/config/urls.py`
- Modify: `backend/apps/prescriptions/models.py`
- Modify: `backend/apps/prescriptions/serializers.py`
- Modify: `backend/apps/prescriptions/tests/test_prescription_versioning.py`
- Modify: `backend/apps/studies/views.py`
- Modify: `backend/apps/studies/tests/test_project_patient_binding_api.py`

### Doctor Web Frontend

- Create: `frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx`
- Create: `frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx`
- Modify: `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx`

### Miniapp

- Create: `miniapp/` using Taro CLI.
- Create or modify after scaffold:
  - `miniapp/src/app.config.ts`
  - `miniapp/src/app.tsx`
  - `miniapp/src/app.scss`
  - `miniapp/src/api/client.ts`
  - `miniapp/src/auth/token.ts`
  - `miniapp/src/pages/bind/index.tsx`
  - `miniapp/src/pages/home/index.tsx`
  - `miniapp/src/pages/prescription/index.tsx`
  - `miniapp/src/pages/training/index.tsx`
  - `miniapp/src/pages/action-history/index.tsx`
  - `miniapp/src/pages/daily-health/index.tsx`

---

### Task 1: Add Weekly Target Count To Prescription Actions

执行记录（2026-05-14, codex）：Task 1 已实现但未提交；当前代码基于最新处方模型使用 `weekly_frequency`、`action_instruction_snapshot` 等字段，迁移编号为 `0009_prescriptionaction_weekly_target_count.py`。执行中额外补齐 activate-now 写入链路、历史 `weekly_frequency` 回填、`weekly_target_count > 0` 约束和医生端处方抽屉 payload，验证命令通过：`pytest apps/prescriptions/tests/test_activate_now_api.py apps/prescriptions/tests/test_prescription_versioning.py -q`（28 passed）、`npm run test -- src/pages/prescriptions/PrescriptionPanel.test.tsx`（9 passed）。

**Files:**
- Modify: `backend/apps/prescriptions/models.py`
- Modify: `backend/apps/prescriptions/serializers.py`
- Modify: `backend/apps/prescriptions/tests/test_prescription_versioning.py`
- Create: `backend/apps/prescriptions/migrations/0003_prescriptionaction_weekly_target_count.py`

- [x] **Step 1: Write failing model and serializer tests**

Add these tests to `backend/apps/prescriptions/tests/test_prescription_versioning.py`:

```python
def test_action_snapshot_records_weekly_target_count(active_prescription):
    action = ActionLibraryItem.objects.create(
        name="坐站转移训练",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="平衡训练",
        execution_description="从椅子坐下后站起",
        key_points="保持躯干稳定",
    )

    snapshot = active_prescription.add_action_snapshot(
        action,
        frequency="每周 2 次",
        duration_minutes=15,
        sets=3,
        weekly_target_count=2,
    )

    assert snapshot.weekly_target_count == 2


def test_prescription_action_serializer_exposes_weekly_target_count(prescription_action):
    from apps.prescriptions.serializers import PrescriptionActionSerializer

    prescription_action.weekly_target_count = 3
    prescription_action.save(update_fields=["weekly_target_count", "updated_at"])

    data = PrescriptionActionSerializer(prescription_action).data

    assert data["weekly_target_count"] == 3
```

- [x] **Step 2: Run the focused prescription tests and confirm failure**

Run:

```bash
cd backend && pytest apps/prescriptions/tests/test_prescription_versioning.py -q
```

Expected: tests fail because `weekly_target_count` does not exist and `add_action_snapshot()` does not accept it.

- [x] **Step 3: Add the model field and snapshot argument**

Modify `backend/apps/prescriptions/models.py`:

```python
    def add_action_snapshot(
        self,
        action: ActionLibraryItem,
        *,
        frequency: str = "",
        duration_minutes: int | None = None,
        sets: int | None = None,
        weekly_target_count: int = 1,
        difficulty: str = "",
        notes: str = "",
        sort_order: int = 0,
    ):
        return PrescriptionAction.objects.create(
            prescription=self,
            action_library_item=action,
            action_name_snapshot=action.name,
            training_type_snapshot=action.training_type,
            internal_type_snapshot=action.internal_type,
            action_type_snapshot=action.action_type,
            execution_description_snapshot=action.execution_description,
            frequency=frequency,
            duration_minutes=duration_minutes,
            sets=sets,
            weekly_target_count=weekly_target_count,
            difficulty=difficulty,
            notes=notes,
            sort_order=sort_order,
        )
```

Add this field to `PrescriptionAction` after `sets`:

```python
    weekly_target_count = models.PositiveIntegerField("每周目标次数", default=1)
```

- [x] **Step 4: Expose the field in the serializer**

Modify `backend/apps/prescriptions/serializers.py` and add `"weekly_target_count"` after `"sets"` in `PrescriptionActionSerializer.Meta.fields`.

- [x] **Step 5: Generate and inspect the migration**

Run:

```bash
cd backend && python manage.py makemigrations prescriptions
```

Expected: Django creates `apps/prescriptions/migrations/0003_prescriptionaction_weekly_target_count.py` adding a positive integer field with default `1`.

- [x] **Step 6: Run prescription tests**

Run:

```bash
cd backend && pytest apps/prescriptions/tests/test_prescription_versioning.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: 提交处方目标字段**

暂未执行：用户尚未要求 commit。

```bash
git add backend/apps/prescriptions/models.py backend/apps/prescriptions/serializers.py backend/apps/prescriptions/tests/test_prescription_versioning.py backend/apps/prescriptions/migrations/0003_prescriptionaction_weekly_target_count.py
git commit -m "feat(prescriptions): 新增处方动作每周目标次数"
```

### Task 2: Add Patient App Models, Token Authentication, And Binding Services

执行记录（2026-05-14, codex）：Task 2 已实现但未提交；实际实现增加绑定码唯一索引竞争重试、`ProjectPatient` 父行锁序列化 create/bind/revoke、明文 code/token 仅响应或请求中出现、患者端 bearer token 鉴权和 15 条服务/认证测试。验证命令通过：`pytest apps/patient_app/tests/test_binding_services.py -q`（15 passed）、`python manage.py makemigrations patient_app --check --dry-run`（No changes detected）。

**Files:**
- Create: `backend/apps/patient_app/__init__.py`
- Create: `backend/apps/patient_app/apps.py`
- Create: `backend/apps/patient_app/models.py`
- Create: `backend/apps/patient_app/services.py`
- Create: `backend/apps/patient_app/authentication.py`
- Create: `backend/apps/patient_app/tests/test_binding_services.py`
- Modify: `backend/config/settings.py`

- [x] **Step 1: Register the new Django app**

Create `backend/apps/patient_app/apps.py`:

```python
from django.apps import AppConfig


class PatientAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.patient_app"
```

Create empty `backend/apps/patient_app/__init__.py`.

Modify `backend/config/settings.py` and add `"apps.patient_app"` after `"apps.health"` in `INSTALLED_APPS`.

- [x] **Step 2: Write failing service tests**

Create `backend/apps/patient_app/tests/test_binding_services.py`:

```python
import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.patient_app.models import PatientAppBindingCode, PatientAppSession
from apps.patient_app.services import bind_project_patient_with_code, create_binding_code


@pytest.mark.django_db
def test_create_binding_code_stores_hash_not_plaintext(project_patient, doctor):
    plain_code, binding = create_binding_code(project_patient=project_patient, created_by=doctor)

    assert len(plain_code) == 8
    assert binding.project_patient == project_patient
    assert binding.code_hash != plain_code
    assert binding.used_at is None
    assert binding.revoked_at is None


@pytest.mark.django_db
def test_bind_project_patient_with_code_creates_session(project_patient, doctor):
    plain_code, binding = create_binding_code(project_patient=project_patient, created_by=doctor)

    token, session = bind_project_patient_with_code(code=plain_code, wx_openid="openid-a")

    binding.refresh_from_db()
    assert token
    assert binding.used_at is not None
    assert session.project_patient == project_patient
    assert session.patient == project_patient.patient
    assert session.wx_openid == "openid-a"
    assert session.is_active is True


@pytest.mark.django_db
def test_binding_code_cannot_be_reused(project_patient, doctor):
    plain_code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    bind_project_patient_with_code(code=plain_code, wx_openid="openid-a")

    with pytest.raises(ValidationError, match="绑定码已使用"):
        bind_project_patient_with_code(code=plain_code, wx_openid="openid-a")


@pytest.mark.django_db
def test_expired_binding_code_is_rejected(project_patient, doctor):
    plain_code, binding = create_binding_code(project_patient=project_patient, created_by=doctor)
    binding.expires_at = timezone.now() - timezone.timedelta(minutes=1)
    binding.save(update_fields=["expires_at", "updated_at"])

    with pytest.raises(ValidationError, match="绑定码已过期"):
        bind_project_patient_with_code(code=plain_code, wx_openid="openid-a")


@pytest.mark.django_db
def test_revoked_binding_code_is_rejected(project_patient, doctor):
    plain_code, binding = create_binding_code(project_patient=project_patient, created_by=doctor)
    binding.revoked_at = timezone.now()
    binding.save(update_fields=["revoked_at", "updated_at"])

    with pytest.raises(ValidationError, match="绑定码已撤销"):
        bind_project_patient_with_code(code=plain_code, wx_openid="openid-a")


@pytest.mark.django_db
def test_create_binding_code_revokes_old_unused_code(project_patient, doctor):
    _, first = create_binding_code(project_patient=project_patient, created_by=doctor)
    _, second = create_binding_code(project_patient=project_patient, created_by=doctor)

    first.refresh_from_db()
    assert first.revoked_at is not None
    assert second.revoked_at is None
```

- [x] **Step 3: Run service tests and confirm failure**

Run:

```bash
cd backend && pytest apps/patient_app/tests/test_binding_services.py -q
```

Expected: import errors because `patient_app` models and services do not exist yet.

- [x] **Step 4: Add patient app models**

Create `backend/apps/patient_app/models.py`:

```python
from django.db import models

from apps.common.models import UserStampedModel


class PatientAppBindingCode(UserStampedModel):
    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="patient_app_binding_codes",
    )
    code_hash = models.CharField("绑定码哈希", max_length=128, unique=True)
    expires_at = models.DateTimeField("过期时间")
    used_at = models.DateTimeField("使用时间", null=True, blank=True)
    revoked_at = models.DateTimeField("撤销时间", null=True, blank=True)

    class Meta:
        ordering = ["-id"]


class PatientAppSession(UserStampedModel):
    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="patient_app_sessions",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="patient_app_sessions",
    )
    wx_openid = models.CharField("微信 openid", max_length=128)
    token_hash = models.CharField("患者端 token 哈希", max_length=128, unique=True)
    expires_at = models.DateTimeField("过期时间")
    last_seen_at = models.DateTimeField("最后访问时间", null=True, blank=True)
    is_active = models.BooleanField("是否有效", default=True)

    class Meta:
        ordering = ["-id"]
```

- [x] **Step 5: Add binding and token services**

Create `backend/apps/patient_app/services.py`:

```python
import secrets

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.studies.models import ProjectPatient

from .models import PatientAppBindingCode, PatientAppSession

BINDING_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
BINDING_CODE_LENGTH = 8
BINDING_CODE_TTL_MINUTES = 30
SESSION_TTL_DAYS = 30


def _hash_binding_code(code: str) -> str:
    return salted_hmac("patient-app-binding-code", code.strip().upper()).hexdigest()


def hash_patient_app_token(token: str) -> str:
    return salted_hmac("patient-app-token", token).hexdigest()


def _generate_binding_code() -> str:
    return "".join(secrets.choice(BINDING_CODE_ALPHABET) for _ in range(BINDING_CODE_LENGTH))


def create_binding_code(*, project_patient: ProjectPatient, created_by) -> tuple[str, PatientAppBindingCode]:
    now = timezone.now()
    with transaction.atomic():
        PatientAppBindingCode.objects.select_for_update().filter(
            project_patient=project_patient,
            used_at__isnull=True,
            revoked_at__isnull=True,
        ).update(revoked_at=now, updated_at=now)

        for _ in range(5):
            plain_code = _generate_binding_code()
            code_hash = _hash_binding_code(plain_code)
            if not PatientAppBindingCode.objects.filter(code_hash=code_hash).exists():
                binding = PatientAppBindingCode.objects.create(
                    project_patient=project_patient,
                    code_hash=code_hash,
                    expires_at=now + timezone.timedelta(minutes=BINDING_CODE_TTL_MINUTES),
                    created_by=created_by,
                )
                return plain_code, binding

    raise ValidationError("绑定码生成失败，请重试")


def _find_binding_by_plain_code(code: str) -> PatientAppBindingCode:
    code_hash = _hash_binding_code(code)
    for binding in PatientAppBindingCode.objects.select_related(
        "project_patient",
        "project_patient__patient",
    ).filter(code_hash=code_hash):
        if constant_time_compare(binding.code_hash, code_hash):
            return binding
    raise ValidationError("绑定码无效")


@transaction.atomic
def bind_project_patient_with_code(*, code: str, wx_openid: str) -> tuple[str, PatientAppSession]:
    now = timezone.now()
    binding = PatientAppBindingCode.objects.select_for_update().select_related(
        "project_patient",
        "project_patient__patient",
    ).get(pk=_find_binding_by_plain_code(code).pk)

    if binding.revoked_at is not None:
        raise ValidationError("绑定码已撤销")
    if binding.used_at is not None:
        raise ValidationError("绑定码已使用")
    if binding.expires_at <= now:
        raise ValidationError("绑定码已过期")

    binding.used_at = now
    binding.save(update_fields=["used_at", "updated_at"])

    PatientAppSession.objects.select_for_update().filter(
        project_patient=binding.project_patient,
        is_active=True,
    ).update(is_active=False, updated_at=now)

    token = secrets.token_urlsafe(32)
    session = PatientAppSession.objects.create(
        project_patient=binding.project_patient,
        patient=binding.project_patient.patient,
        wx_openid=wx_openid,
        token_hash=hash_patient_app_token(token),
        expires_at=now + timezone.timedelta(days=SESSION_TTL_DAYS),
        last_seen_at=now,
        is_active=True,
    )
    return token, session


def revoke_project_patient_binding(*, project_patient: ProjectPatient) -> None:
    now = timezone.now()
    PatientAppBindingCode.objects.filter(
        project_patient=project_patient,
        used_at__isnull=True,
        revoked_at__isnull=True,
    ).update(revoked_at=now, updated_at=now)
    PatientAppSession.objects.filter(project_patient=project_patient, is_active=True).update(
        is_active=False,
        updated_at=now,
    )
```

- [x] **Step 6: Add token authentication**

Create `backend/apps/patient_app/authentication.py`:

```python
from dataclasses import dataclass

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import PatientAppSession
from .services import hash_patient_app_token


@dataclass
class PatientAppPrincipal:
    session: PatientAppSession

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def project_patient(self):
        return self.session.project_patient

    @property
    def patient(self):
        return self.session.patient


class PatientAppTokenAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth:
            return None
        if len(auth) != 2 or auth[0].lower() != self.keyword:
            raise AuthenticationFailed("患者端认证格式错误")

        token = auth[1].decode("utf-8")
        token_hash = hash_patient_app_token(token)
        session = (
            PatientAppSession.objects.select_related(
                "project_patient",
                "project_patient__project",
                "project_patient__patient",
                "patient",
            )
            .filter(token_hash=token_hash, is_active=True, expires_at__gt=timezone.now())
            .first()
        )
        if session is None:
            raise AuthenticationFailed("患者端登录已失效")

        session.last_seen_at = timezone.now()
        session.save(update_fields=["last_seen_at", "updated_at"])
        return PatientAppPrincipal(session=session), session
```

- [x] **Step 7: Generate and inspect patient app migration**

Run:

```bash
cd backend && python manage.py makemigrations patient_app
```

Expected: Django creates `apps/patient_app/migrations/0001_initial.py` for `PatientAppBindingCode` and `PatientAppSession`.

- [x] **Step 8: Run service tests**

Run:

```bash
cd backend && pytest apps/patient_app/tests/test_binding_services.py -q
```

Expected: all selected tests pass.

- [ ] **Step 9: 提交患者端绑定基础设施**

暂未执行：用户尚未要求 commit。

```bash
git add backend/config/settings.py backend/apps/patient_app
git commit -m "feat(patient-app): 新增患者端绑定与令牌模型"
```

### Task 3: Add Doctor-Side Binding Management APIs

执行记录（2026-05-14, codex）：Task 3 已实现但未提交；在 `ProjectPatientViewSet` 新增 `binding-code`、`binding-status`、`revoke-binding` 动作，完结项目允许查看状态但禁止生成/撤销，接口测试覆盖 5 条。验证命令通过：`pytest apps/studies/tests/test_project_patient_binding_api.py -q`（5 passed），并与 Task 2/解绑/完结相关测试合跑通过：27 passed。

**Files:**
- Modify: `backend/apps/studies/views.py`
- Create: `backend/apps/studies/tests/test_project_patient_binding_api.py`

- [x] **Step 1: Write failing API tests**

Create `backend/apps/studies/tests/test_project_patient_binding_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.patient_app.models import PatientAppBindingCode, PatientAppSession
from apps.patient_app.services import bind_project_patient_with_code


def login(client: APIClient, doctor):
    client.force_authenticate(user=doctor)


@pytest.mark.django_db
def test_doctor_can_create_project_patient_binding_code(project_patient, doctor):
    client = APIClient()
    login(client, doctor)

    resp = client.post(f"/api/studies/project-patients/{project_patient.id}/binding-code/")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["code"]) == 8
    assert body["expires_at"]
    assert PatientAppBindingCode.objects.filter(project_patient=project_patient).count() == 1


@pytest.mark.django_db
def test_binding_status_reports_active_session(project_patient, doctor):
    client = APIClient()
    login(client, doctor)
    create_resp = client.post(f"/api/studies/project-patients/{project_patient.id}/binding-code/")
    token, _ = bind_project_patient_with_code(
        code=create_resp.json()["code"],
        wx_openid="openid-a",
    )
    assert token

    resp = client.get(f"/api/studies/project-patients/{project_patient.id}/binding-status/")

    assert resp.status_code == 200
    body = resp.json()
    assert body["has_active_session"] is True
    assert body["has_valid_unused_code"] is False
    assert body["last_bound_at"]


@pytest.mark.django_db
def test_revoke_binding_disables_session(project_patient, doctor):
    client = APIClient()
    login(client, doctor)
    create_resp = client.post(f"/api/studies/project-patients/{project_patient.id}/binding-code/")
    bind_project_patient_with_code(code=create_resp.json()["code"], wx_openid="openid-a")

    resp = client.post(f"/api/studies/project-patients/{project_patient.id}/revoke-binding/")

    assert resp.status_code == 200
    assert PatientAppSession.objects.filter(project_patient=project_patient, is_active=True).count() == 0
```

- [x] **Step 2: Run API tests and confirm failure**

Run:

```bash
cd backend && pytest apps/studies/tests/test_project_patient_binding_api.py -q
```

Expected: tests fail with 404 because actions do not exist yet.

- [x] **Step 3: Add actions to ProjectPatientViewSet**

Modify imports in `backend/apps/studies/views.py`:

```python
from django.utils import timezone
from apps.patient_app.models import PatientAppBindingCode, PatientAppSession
from apps.patient_app.services import create_binding_code, revoke_project_patient_binding
```

Add these actions inside `ProjectPatientViewSet`:

```python
    @action(detail=True, methods=["post"], url_path="binding-code")
    @transaction.atomic
    def binding_code(self, request, pk=None):
        pp = self.get_object()
        plain_code, binding = create_binding_code(project_patient=pp, created_by=request.user)
        return Response(
            {
                "code": plain_code,
                "expires_at": binding.expires_at.isoformat(),
            }
        )

    @action(detail=True, methods=["get"], url_path="binding-status")
    def binding_status(self, request, pk=None):
        pp = self.get_object()
        now = timezone.now()
        active_session = (
            PatientAppSession.objects.filter(project_patient=pp, is_active=True, expires_at__gt=now)
            .order_by("-id")
            .first()
        )
        valid_code = PatientAppBindingCode.objects.filter(
            project_patient=pp,
            used_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=now,
        ).exists()
        return Response(
            {
                "has_active_session": active_session is not None,
                "has_valid_unused_code": valid_code,
                "last_bound_at": active_session.created_at.isoformat() if active_session else None,
            }
        )

    @action(detail=True, methods=["post"], url_path="revoke-binding")
    @transaction.atomic
    def revoke_binding(self, request, pk=None):
        pp = self.get_object()
        revoke_project_patient_binding(project_patient=pp)
        return Response({"detail": "已撤销患者端绑定"})
```

- [x] **Step 4: Run binding API tests**

Run:

```bash
cd backend && pytest apps/studies/tests/test_project_patient_binding_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: 提交医生端绑定管理接口**

暂未执行：用户尚未要求 commit。

```bash
git add backend/apps/studies/views.py backend/apps/studies/tests/test_project_patient_binding_api.py
git commit -m "feat(studies): 新增项目患者小程序绑定接口"
```

### Task 4: Add Patient App Prescription, Progress, Training, History, And Health APIs

执行记录（2026-05-14, codex）：Task 4 已实现但未提交；新增 `/api/patient-app/` 绑定、身份、首页、当前处方、本周动作进度、训练提交、动作历史、今日健康数据 upsert 接口。实际序列化字段按当前处方模型使用 `weekly_frequency`、`action_instruction_snapshot`、`duration_minutes`，并由 token 推导唯一 `ProjectPatient`。验证命令通过：`pytest apps/patient_app/tests/test_patient_app_api.py -q`（6 passed），相关后端合跑 `pytest apps/patient_app apps/studies/tests/test_project_patient_binding_api.py apps/training/tests/test_training_current_prescription.py apps/health/tests/test_daily_health_unique.py -q`（33 passed）。

**Files:**
- Create: `backend/apps/patient_app/serializers.py`
- Create: `backend/apps/patient_app/views.py`
- Create: `backend/apps/patient_app/urls.py`
- Create: `backend/apps/patient_app/tests/test_patient_app_api.py`
- Modify: `backend/config/urls.py`

- [x] **Step 1: Write failing patient app API tests**

Create `backend/apps/patient_app/tests/test_patient_app_api.py`:

```python
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.health.models import DailyHealthRecord
from apps.patient_app.services import bind_project_patient_with_code, create_binding_code
from apps.training.models import TrainingRecord


def auth_client(project_patient, doctor):
    code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    token, _ = bind_project_patient_with_code(code=code, wx_openid="openid-a")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
def test_bind_api_returns_token(project_patient, doctor):
    code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    client = APIClient()

    resp = client.post("/api/patient-app/bind/", {"code": code, "wx_openid": "openid-a"}, format="json")

    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["patient"]["name"] == project_patient.patient.name
    assert body["project"]["name"] == project_patient.project.name


@pytest.mark.django_db
def test_patient_app_me_uses_token(project_patient, doctor):
    client = auth_client(project_patient, doctor)

    resp = client.get("/api/patient-app/me/")

    assert resp.status_code == 200
    assert resp.json()["project_patient_id"] == project_patient.id


@pytest.mark.django_db
def test_current_prescription_includes_weekly_progress(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    prescription_action.weekly_target_count = 2
    prescription_action.save(update_fields=["weekly_target_count", "updated_at"])
    TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=12,
    )
    client = auth_client(project_patient, doctor)

    resp = client.get("/api/patient-app/current-prescription/")

    assert resp.status_code == 200
    action = resp.json()["actions"][0]
    assert action["weekly_target_count"] == 2
    assert action["weekly_completed_count"] == 1
    assert action["recent_record"]["status"] == "completed"


@pytest.mark.django_db
def test_training_record_api_allows_multiple_records_same_day(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    client = auth_client(project_patient, doctor)
    payload = {
        "prescription_action": prescription_action.id,
        "training_date": str(timezone.localdate()),
        "status": "completed",
        "actual_duration_minutes": 10,
        "note": "完成",
    }

    first = client.post("/api/patient-app/training-records/", payload, format="json")
    second = client.post("/api/patient-app/training-records/", payload, format="json")

    assert first.status_code == 201
    assert second.status_code == 201
    assert TrainingRecord.objects.filter(project_patient=project_patient).count() == 2


@pytest.mark.django_db
def test_action_history_only_returns_current_action_records(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
    )
    client = auth_client(project_patient, doctor)

    resp = client.get(f"/api/patient-app/actions/{prescription_action.id}/history/")

    assert resp.status_code == 200
    body = resp.json()
    assert body["last_7_days_completed_count"] == 1
    assert len(body["records"]) == 1


@pytest.mark.django_db
def test_daily_health_today_upserts_patient_record(project_patient, doctor):
    client = auth_client(project_patient, doctor)

    first = client.put("/api/patient-app/daily-health/today/", {"steps": 1000}, format="json")
    second = client.put("/api/patient-app/daily-health/today/", {"steps": 2000}, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert DailyHealthRecord.objects.filter(patient=project_patient.patient).count() == 1
    assert DailyHealthRecord.objects.get(patient=project_patient.patient).steps == 2000
```

- [x] **Step 2: Run patient app API tests and confirm failure**

Run:

```bash
cd backend && pytest apps/patient_app/tests/test_patient_app_api.py -q
```

Expected: tests fail because `/api/patient-app/` routes do not exist yet.

- [x] **Step 3: Add serializers**

Create `backend/apps/patient_app/serializers.py`:

```python
from rest_framework import serializers

from apps.health.models import DailyHealthRecord
from apps.training.models import TrainingRecord


class PatientAppBindSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)
    wx_openid = serializers.CharField(max_length=128)


class PatientAppTrainingRecordCreateSerializer(serializers.Serializer):
    prescription_action = serializers.IntegerField(min_value=1)
    training_date = serializers.DateField()
    status = serializers.ChoiceField(choices=TrainingRecord.Status.choices)
    actual_duration_minutes = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    score = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, allow_null=True)
    form_data = serializers.JSONField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)


class PatientAppDailyHealthSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyHealthRecord
        fields = [
            "id",
            "record_date",
            "steps",
            "exercise_minutes",
            "average_heart_rate",
            "max_heart_rate",
            "min_heart_rate",
            "sleep_hours",
            "note",
        ]
        read_only_fields = ["id", "record_date"]
```

- [x] **Step 4: Add patient app views**

Create `backend/apps/patient_app/views.py`. Keep helper functions in the same file for this first pass; move them to a service module only when they grow:

```python
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.health.models import DailyHealthRecord
from apps.prescriptions.models import Prescription, PrescriptionAction
from apps.training.models import TrainingRecord
from apps.training.services import create_training_record

from .authentication import PatientAppTokenAuthentication
from .serializers import (
    PatientAppBindSerializer,
    PatientAppDailyHealthSerializer,
    PatientAppTrainingRecordCreateSerializer,
)
from .services import bind_project_patient_with_code


def current_week_bounds(today=None):
    today = today or timezone.localdate()
    start = today - timezone.timedelta(days=today.weekday())
    end = start + timezone.timedelta(days=6)
    return start, end


def serialize_me(project_patient):
    return {
        "project_patient_id": project_patient.id,
        "patient": {"id": project_patient.patient_id, "name": project_patient.patient.name},
        "project": {"id": project_patient.project_id, "name": project_patient.project.name},
    }


def current_prescription_for(project_patient):
    return (
        Prescription.objects.filter(project_patient=project_patient, status=Prescription.Status.ACTIVE)
        .prefetch_related("actions")
        .order_by("-effective_at", "-id")
        .first()
    )


def serialize_prescription(project_patient):
    prescription = current_prescription_for(project_patient)
    if prescription is None:
        return None

    actions = list(prescription.actions.all().order_by("sort_order", "id"))
    action_ids = [a.id for a in actions]
    week_start, week_end = current_week_bounds()

    completed_counts = {
        row["prescription_action_id"]: row["count"]
        for row in TrainingRecord.objects.filter(
            project_patient=project_patient,
            prescription_action_id__in=action_ids,
            training_date__gte=week_start,
            training_date__lte=week_end,
            status=TrainingRecord.Status.COMPLETED,
        )
        .values("prescription_action_id")
        .annotate(count=Count("id"))
    }
    recent_records = {}
    for record in TrainingRecord.objects.filter(
        project_patient=project_patient,
        prescription_action_id__in=action_ids,
    ).order_by("prescription_action_id", "-training_date", "-id"):
        recent_records.setdefault(record.prescription_action_id, record)

    serialized_actions = []
    for action in actions:
        recent = recent_records.get(action.id)
        serialized_actions.append(
            {
                "id": action.id,
                "action_name": action.action_name_snapshot,
                "action_type": action.action_type_snapshot,
                "execution_description": action.execution_description_snapshot,
                "frequency": action.frequency,
                "duration_minutes": action.duration_minutes,
                "sets": action.sets,
                "weekly_target_count": action.weekly_target_count,
                "weekly_completed_count": completed_counts.get(action.id, 0),
                "recent_record": (
                    {
                        "id": recent.id,
                        "training_date": recent.training_date.isoformat(),
                        "status": recent.status,
                        "actual_duration_minutes": recent.actual_duration_minutes,
                    }
                    if recent
                    else None
                ),
            }
        )

    return {
        "id": prescription.id,
        "version": prescription.version,
        "effective_at": prescription.effective_at.isoformat() if prescription.effective_at else None,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "actions": serialized_actions,
    }


class PatientAppBindView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PatientAppBindSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token, session = bind_project_patient_with_code(**serializer.validated_data)
        except DjangoValidationError as exc:
            detail = exc.messages[0] if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"token": token, **serialize_me(session.project_patient)})


class PatientAppBaseView(APIView):
    authentication_classes = [PatientAppTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def project_patient(self):
        return self.request.user.project_patient


class PatientAppMeView(PatientAppBaseView):
    def get(self, request):
        return Response(serialize_me(self.project_patient()))


class PatientAppHomeView(PatientAppBaseView):
    def get(self, request):
        pp = self.project_patient()
        prescription = serialize_prescription(pp)
        today = timezone.localdate()
        has_daily_health = DailyHealthRecord.objects.filter(patient=pp.patient, record_date=today).exists()
        return Response(
            {
                **serialize_me(pp),
                "today": today.isoformat(),
                "has_daily_health_today": has_daily_health,
                "current_prescription": prescription,
            }
        )


class PatientAppCurrentPrescriptionView(PatientAppBaseView):
    def get(self, request):
        return Response(serialize_prescription(self.project_patient()))


class PatientAppTrainingRecordView(PatientAppBaseView):
    def post(self, request):
        serializer = PatientAppTrainingRecordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            action = PrescriptionAction.objects.get(pk=data.pop("prescription_action"))
            record = create_training_record(
                project_patient=self.project_patient(),
                prescription_action=action,
                **data,
            )
        except (PrescriptionAction.DoesNotExist, DjangoValidationError) as exc:
            detail = exc.messages[0] if hasattr(exc, "messages") else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": record.id}, status=status.HTTP_201_CREATED)


class PatientAppActionHistoryView(PatientAppBaseView):
    def get(self, request, prescription_action_id):
        pp = self.project_patient()
        active = current_prescription_for(pp)
        if active is None or not active.actions.filter(pk=prescription_action_id).exists():
            return Response({"detail": "动作不存在或不属于当前处方"}, status=status.HTTP_404_NOT_FOUND)

        today = timezone.localdate()
        last_7_start = today - timezone.timedelta(days=6)
        last_30_start = today - timezone.timedelta(days=29)
        records = TrainingRecord.objects.filter(
            project_patient=pp,
            prescription_action_id=prescription_action_id,
        ).order_by("-training_date", "-id")
        return Response(
            {
                "last_7_days_completed_count": records.filter(
                    training_date__gte=last_7_start,
                    status=TrainingRecord.Status.COMPLETED,
                ).count(),
                "last_30_days_completed_count": records.filter(
                    training_date__gte=last_30_start,
                    status=TrainingRecord.Status.COMPLETED,
                ).count(),
                "records": [
                    {
                        "id": r.id,
                        "training_date": r.training_date.isoformat(),
                        "status": r.status,
                        "actual_duration_minutes": r.actual_duration_minutes,
                        "note": r.note,
                    }
                    for r in records[:30]
                ],
            }
        )


class PatientAppDailyHealthTodayView(PatientAppBaseView):
    def get(self, request):
        pp = self.project_patient()
        record = DailyHealthRecord.objects.filter(
            patient=pp.patient,
            record_date=timezone.localdate(),
        ).first()
        return Response(PatientAppDailyHealthSerializer(record).data if record else None)

    def put(self, request):
        pp = self.project_patient()
        record, _ = DailyHealthRecord.objects.get_or_create(
            patient=pp.patient,
            record_date=timezone.localdate(),
        )
        serializer = PatientAppDailyHealthSerializer(record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
```

- [x] **Step 5: Add routes**

Create `backend/apps/patient_app/urls.py`:

```python
from django.urls import path

from .views import (
    PatientAppActionHistoryView,
    PatientAppBindView,
    PatientAppCurrentPrescriptionView,
    PatientAppDailyHealthTodayView,
    PatientAppHomeView,
    PatientAppMeView,
    PatientAppTrainingRecordView,
)

urlpatterns = [
    path("bind/", PatientAppBindView.as_view(), name="patient-app-bind"),
    path("me/", PatientAppMeView.as_view(), name="patient-app-me"),
    path("home/", PatientAppHomeView.as_view(), name="patient-app-home"),
    path(
        "current-prescription/",
        PatientAppCurrentPrescriptionView.as_view(),
        name="patient-app-current-prescription",
    ),
    path(
        "training-records/",
        PatientAppTrainingRecordView.as_view(),
        name="patient-app-training-records",
    ),
    path(
        "actions/<int:prescription_action_id>/history/",
        PatientAppActionHistoryView.as_view(),
        name="patient-app-action-history",
    ),
    path(
        "daily-health/today/",
        PatientAppDailyHealthTodayView.as_view(),
        name="patient-app-daily-health-today",
    ),
]
```

Modify `backend/config/urls.py`:

```python
    path("api/patient-app/", include("apps.patient_app.urls")),
```

- [x] **Step 6: Run patient app API tests**

Run:

```bash
cd backend && pytest apps/patient_app/tests/test_patient_app_api.py -q
```

Expected: all selected tests pass.

- [x] **Step 7: Run related backend tests**

Run:

```bash
cd backend && pytest apps/patient_app apps/studies/tests/test_project_patient_binding_api.py apps/training/tests/test_training_current_prescription.py apps/health/tests/test_daily_health_unique.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: 提交患者端 API**

暂未执行：用户尚未要求 commit。

```bash
git add backend/config/urls.py backend/apps/patient_app
git commit -m "feat(patient-app): 新增患者端处方训练与健康接口"
```

### Task 5: Add Doctor Web Binding Card

执行记录（2026-05-14, codex）：Task 5 已实现但未提交；新增研究录入页小程序绑定管理区，支持查看绑定状态、生成一次性绑定码、撤销绑定，并按后端实际字段使用 `has_active_binding_code`。验证命令通过：`npm run test -- src/pages/research-entry/ProjectPatientBindingCard.test.tsx src/pages/research-entry/ProjectPatientResearchEntryPage.test.tsx src/app/App.test.tsx`（18 passed，保留既有 React Router/AntD/jsdom warning）。

**Files:**
- Create: `frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx`
- Create: `frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx`
- Modify: `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx`

- [x] **Step 1: Write failing component test**

Create `frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import { ProjectPatientBindingCard } from "./ProjectPatientBindingCard";

vi.mock("../../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProjectPatientBindingCard projectPatientId={12} />
    </QueryClientProvider>,
  );
}

describe("ProjectPatientBindingCard", () => {
  it("shows binding status and generated code", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { has_active_session: false, has_valid_unused_code: false, last_bound_at: null },
    });
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { code: "ABCD2345", expires_at: "2026-05-14T12:30:00+08:00" },
    });

    renderCard();
    await screen.findByText("未绑定");
    await userEvent.click(screen.getByRole("button", { name: "生成绑定码" }));

    expect(await screen.findByText("ABCD2345")).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledWith("/studies/project-patients/12/binding-code/");
  });
});
```

- [x] **Step 2: Run the focused frontend test and confirm failure**

Run:

```bash
cd frontend && npm run test -- src/pages/research-entry/ProjectPatientBindingCard.test.tsx
```

Expected: test fails because the component does not exist.

- [x] **Step 3: Add binding card component**

Create `frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Space, Tag, Typography } from "antd";

import { apiClient } from "../../api/client";

type BindingStatus = {
  has_active_session: boolean;
  has_valid_unused_code: boolean;
  last_bound_at: string | null;
};

type BindingCodeResponse = {
  code: string;
  expires_at: string;
};

export function ProjectPatientBindingCard({ projectPatientId }: { projectPatientId: number }) {
  const qc = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ["project-patient-binding-status", projectPatientId],
    queryFn: async () => {
      const r = await apiClient.get<BindingStatus>(
        `/studies/project-patients/${projectPatientId}/binding-status/`,
      );
      return r.data;
    },
  });
  const createCode = useMutation({
    mutationFn: async () => {
      const r = await apiClient.post<BindingCodeResponse>(
        `/studies/project-patients/${projectPatientId}/binding-code/`,
      );
      return r.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project-patient-binding-status", projectPatientId] }),
  });
  const revoke = useMutation({
    mutationFn: async () => {
      await apiClient.post(`/studies/project-patients/${projectPatientId}/revoke-binding/`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project-patient-binding-status", projectPatientId] }),
  });

  const status = statusQuery.data;

  return (
    <Card
      title="小程序绑定"
      loading={statusQuery.isLoading}
      extra={
        <Space>
          <Button onClick={() => createCode.mutate()} loading={createCode.isPending}>
            生成绑定码
          </Button>
          <Button danger onClick={() => revoke.mutate()} loading={revoke.isPending}>
            撤销绑定
          </Button>
        </Space>
      }
    >
      <Descriptions size="small" bordered column={3}>
        <Descriptions.Item label="绑定状态">
          {status?.has_active_session ? <Tag color="green">已绑定</Tag> : <Tag>未绑定</Tag>}
        </Descriptions.Item>
        <Descriptions.Item label="有效绑定码">
          {status?.has_valid_unused_code ? <Tag color="blue">存在</Tag> : <Tag>无</Tag>}
        </Descriptions.Item>
        <Descriptions.Item label="最近绑定时间">{status?.last_bound_at ?? "—"}</Descriptions.Item>
      </Descriptions>
      {createCode.data && (
        <Alert
          style={{ marginTop: 16 }}
          type="success"
          showIcon
          message={
            <Space direction="vertical">
              <span>绑定码只显示一次，请提供给患者。</span>
              <Typography.Text copyable strong>
                {createCode.data.code}
              </Typography.Text>
              <span>过期时间：{createCode.data.expires_at}</span>
            </Space>
          }
        />
      )}
    </Card>
  );
}
```

- [x] **Step 4: Mount card in research entry page**

Modify `frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx`:

```tsx
import { ProjectPatientBindingCard } from "./ProjectPatientBindingCard";
```

Add the card immediately after the `Descriptions` block and before `Tabs`:

```tsx
          <ProjectPatientBindingCard projectPatientId={data.id} />
```

- [x] **Step 5: Run frontend tests**

Run:

```bash
cd frontend && npm run test -- src/pages/research-entry/ProjectPatientBindingCard.test.tsx src/pages/research-entry/ProjectPatientResearchEntryPage.test.tsx src/app/App.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 6: 提交医生端绑定卡片**

暂未执行：用户尚未要求 commit。

```bash
git add frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx frontend/src/pages/research-entry/ProjectPatientResearchEntryPage.tsx
git commit -m "feat(frontend): 新增项目患者小程序绑定卡片"
```

### Task 6: Scaffold Taro Miniapp Project

执行记录（2026-05-14, codex）：Task 6 已实现但未提交；使用 Taro v4.2.0 初始化 `miniapp/`（React + TypeScript + Sass + npm + Webpack5 + CLI 内置默认模板），删除脚手架自动生成的嵌套 `miniapp/.git`，`miniapp/dist/` 已由脚手架 `.gitignore` 忽略。验证命令通过：`npm run build:weapp`。依赖安装报告 51 个 npm audit vulnerabilities，未执行自动修复以避免破坏脚手架锁定版本。

**Files:**
- Create: `miniapp/`
- Modify: `.gitignore` if Taro scaffold creates build artifacts not ignored

- [x] **Step 1: Scaffold the Taro project**

Run from repository root:

```bash
npx @tarojs/cli init miniapp
```

When prompted, select:

```text
框架: React
语言: TypeScript
CSS 预处理器: Sass
包管理器: npm
模板: 默认模板
```

Expected: `miniapp/package.json`, `miniapp/src/app.tsx`, and Taro config files are created.

- [x] **Step 2: Install dependencies if the scaffold did not finish install**

Run:

```bash
cd miniapp && npm install
```

Expected: `miniapp/package-lock.json` exists and dependencies install successfully.

- [x] **Step 3: Verify weapp build**

Run:

```bash
cd miniapp && npm run build:weapp
```

Expected: build succeeds and emits mini program files into `miniapp/dist/`.

- [x] **Step 4: Ensure generated build output is ignored**

If `miniapp/dist/` is not ignored by generated `.gitignore`, add:

```gitignore
miniapp/dist/
```

- [ ] **Step 5: 提交小程序工程脚手架**

暂未执行：用户尚未要求 commit。

```bash
git add miniapp .gitignore
git commit -m "chore(miniapp): 初始化 Taro 小程序工程"
```

### Task 7: Add Miniapp API Client And Auth Flow

执行记录（2026-05-14, codex）：Task 7 已实现但未提交；配置小程序页面路由，新增患者端 token 存储、Taro request API client、绑定页和首页工作台。实际实现同时移除脚手架默认 `pages/index`，首页包含当前处方、本周训练和健康填报入口。验证命令通过：`npm run build:weapp`、`npx tsc --noEmit --skipLibCheck`。

**Files:**
- Modify: `miniapp/src/app.config.ts`
- Modify: `miniapp/src/app.tsx`
- Create: `miniapp/src/api/client.ts`
- Create: `miniapp/src/auth/token.ts`
- Create: `miniapp/src/pages/bind/index.tsx`
- Create: `miniapp/src/pages/home/index.tsx`

- [x] **Step 1: Configure pages**

Modify `miniapp/src/app.config.ts`:

```ts
export default defineAppConfig({
  pages: [
    "pages/bind/index",
    "pages/home/index",
    "pages/prescription/index",
    "pages/training/index",
    "pages/action-history/index",
    "pages/daily-health/index",
  ],
  window: {
    backgroundTextStyle: "light",
    navigationBarBackgroundColor: "#ffffff",
    navigationBarTitleText: "MotionCare",
    navigationBarTextStyle: "black",
  },
});
```

- [x] **Step 2: Add token storage helper**

Create `miniapp/src/auth/token.ts`:

```ts
import Taro from "@tarojs/taro";

const TOKEN_KEY = "motioncare_patient_app_token";

export function getPatientAppToken(): string | undefined {
  return Taro.getStorageSync<string>(TOKEN_KEY) || undefined;
}

export function setPatientAppToken(token: string) {
  Taro.setStorageSync(TOKEN_KEY, token);
}

export function clearPatientAppToken() {
  Taro.removeStorageSync(TOKEN_KEY);
}
```

- [x] **Step 3: Add API client**

Create `miniapp/src/api/client.ts`:

```ts
import Taro from "@tarojs/taro";

import { clearPatientAppToken, getPatientAppToken } from "../auth/token";

const API_BASE_URL = process.env.TARO_APP_API_BASE_URL || "http://127.0.0.1:8000/api";

type Method = "GET" | "POST" | "PUT";

export async function request<T>(path: string, options: { method?: Method; data?: unknown } = {}): Promise<T> {
  const token = getPatientAppToken();
  const response = await Taro.request<T>({
    url: `${API_BASE_URL}${path}`,
    method: options.method ?? "GET",
    data: options.data,
    header: {
      "content-type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  if (response.statusCode === 401 || response.statusCode === 403) {
    clearPatientAppToken();
    Taro.redirectTo({ url: "/pages/bind/index" });
    throw new Error("登录已失效");
  }
  if (response.statusCode < 200 || response.statusCode >= 300) {
    const data = response.data as { detail?: string; message?: string };
    throw new Error(data?.detail || data?.message || "请求失败");
  }
  return response.data;
}
```

- [x] **Step 4: Add bind page**

Create `miniapp/src/pages/bind/index.tsx`:

```tsx
import { Button, Input, View, Text } from "@tarojs/components";
import Taro from "@tarojs/taro";
import { useState } from "react";

import { request } from "../../api/client";
import { setPatientAppToken } from "../../auth/token";

type BindResponse = {
  token: string;
  patient: { name: string };
  project: { name: string };
};

export default function BindPage() {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    setError("");
    try {
      const login = await Taro.login();
      const wxOpenid = login.code || "dev-openid";
      const body = await request<BindResponse>("/patient-app/bind/", {
        method: "POST",
        data: { code, wx_openid: wxOpenid },
      });
      setPatientAppToken(body.token);
      Taro.redirectTo({ url: "/pages/home/index" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "绑定失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <View className="page bind-page">
      <Text className="title">绑定 MotionCare</Text>
      <Input value={code} placeholder="请输入医生提供的绑定码" onInput={(e) => setCode(e.detail.value)} />
      {error ? <Text className="error">{error}</Text> : null}
      <Button loading={loading} disabled={!code.trim()} onClick={submit}>
        绑定
      </Button>
    </View>
  );
}
```

- [x] **Step 5: Add basic home page**

Create `miniapp/src/pages/home/index.tsx`:

```tsx
import { Button, View, Text } from "@tarojs/components";
import Taro, { useDidShow } from "@tarojs/taro";
import { useState } from "react";

import { request } from "../../api/client";

type HomeData = {
  patient: { name: string };
  project: { name: string };
  has_daily_health_today: boolean;
  current_prescription: null | {
    actions: Array<{ id: number; action_name: string; weekly_completed_count: number; weekly_target_count: number }>;
  };
};

export default function HomePage() {
  const [data, setData] = useState<HomeData | null>(null);
  const [error, setError] = useState("");

  useDidShow(() => {
    request<HomeData>("/patient-app/home/")
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  });

  return (
    <View className="page home-page">
      <Text className="title">今日工作台</Text>
      {error ? <Text className="error">{error}</Text> : null}
      {data ? (
        <View>
          <Text>{data.patient.name} · {data.project.name}</Text>
          <Text>今日健康数据：{data.has_daily_health_today ? "已填写" : "待填写"}</Text>
          <Text>处方动作：{data.current_prescription?.actions.length ?? 0} 项</Text>
          <Button onClick={() => Taro.navigateTo({ url: "/pages/prescription/index" })}>查看处方</Button>
          <Button onClick={() => Taro.navigateTo({ url: "/pages/daily-health/index" })}>填写健康数据</Button>
        </View>
      ) : (
        <Text>加载中</Text>
      )}
    </View>
  );
}
```

- [x] **Step 6: Verify miniapp build**

Run:

```bash
cd miniapp && npm run build:weapp
```

Expected: build succeeds.

- [ ] **Step 7: 提交小程序绑定与首页**

暂未执行：用户尚未要求 commit。

```bash
git add miniapp/src
git commit -m "feat(miniapp): 新增绑定与首页工作台"
```

### Task 8: Add Miniapp Prescription, Training, History, And Daily Health Pages

执行记录（2026-05-14, codex）：Task 8 已实现但未提交；新增当前处方、本周进度、训练提交、动作历史和今日健康数据页面，并抽出共享类型与本地日期工具。验证命令通过：`npm run build:weapp`、`npx tsc --noEmit --skipLibCheck`。直接 `npx tsc --noEmit` 会因 Taro 4.2.0 脚手架依赖声明文件报错，故使用 `--skipLibCheck` 校验本项目 TS。

**Files:**
- Create: `miniapp/src/pages/prescription/index.tsx`
- Create: `miniapp/src/pages/training/index.tsx`
- Create: `miniapp/src/pages/action-history/index.tsx`
- Create: `miniapp/src/pages/daily-health/index.tsx`

- [x] **Step 1: Add prescription page**

Create `miniapp/src/pages/prescription/index.tsx`:

```tsx
import { Button, View, Text } from "@tarojs/components";
import Taro, { useDidShow } from "@tarojs/taro";
import { useState } from "react";

import { request } from "../../api/client";

type Prescription = null | {
  version: number;
  week_start: string;
  week_end: string;
  actions: Array<{
    id: number;
    action_name: string;
    action_type: string;
    weekly_target_count: number;
    weekly_completed_count: number;
    recent_record: null | { training_date: string; status: string };
  }>;
};

export default function PrescriptionPage() {
  const [data, setData] = useState<Prescription>(null);

  useDidShow(() => {
    request<Prescription>("/patient-app/current-prescription/").then(setData);
  });

  if (!data) return <View className="page"><Text>暂无生效处方</Text></View>;

  return (
    <View className="page prescription-page">
      <Text className="title">当前处方 v{data.version}</Text>
      <Text>本周：{data.week_start} 至 {data.week_end}</Text>
      {data.actions.map((action) => (
        <View key={action.id} className="action-card">
          <Text>{action.action_name}</Text>
          <Text>{action.weekly_completed_count}/{action.weekly_target_count} 次</Text>
          <Text>最近：{action.recent_record?.training_date ?? "暂无记录"}</Text>
          <Button onClick={() => Taro.navigateTo({ url: `/pages/training/index?actionId=${action.id}` })}>
            开始训练
          </Button>
          <Button onClick={() => Taro.navigateTo({ url: `/pages/action-history/index?actionId=${action.id}` })}>
            历史
          </Button>
        </View>
      ))}
    </View>
  );
}
```

- [x] **Step 2: Add training page**

Create `miniapp/src/pages/training/index.tsx`:

```tsx
import { Button, Input, Picker, View, Text } from "@tarojs/components";
import Taro, { useRouter } from "@tarojs/taro";
import { useState } from "react";

import { request } from "../../api/client";

const STATUS_OPTIONS = [
  { label: "已完成", value: "completed" },
  { label: "部分完成", value: "partial" },
  { label: "未完成", value: "missed" },
];

export default function TrainingPage() {
  const router = useRouter();
  const actionId = Number(router.params.actionId);
  const [statusIndex, setStatusIndex] = useState(0);
  const [duration, setDuration] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    const today = new Date().toISOString().slice(0, 10);
    await request("/patient-app/training-records/", {
      method: "POST",
      data: {
        prescription_action: actionId,
        training_date: today,
        status: STATUS_OPTIONS[statusIndex].value,
        actual_duration_minutes: duration ? Number(duration) : null,
        note,
      },
    });
    setLoading(false);
    Taro.navigateBack();
  }

  return (
    <View className="page training-page">
      <Text className="title">训练记录</Text>
      <Picker
        mode="selector"
        range={STATUS_OPTIONS.map((item) => item.label)}
        value={statusIndex}
        onChange={(e) => setStatusIndex(Number(e.detail.value))}
      >
        <Text>完成状态：{STATUS_OPTIONS[statusIndex].label}</Text>
      </Picker>
      <Input type="number" value={duration} placeholder="实际时长（分钟）" onInput={(e) => setDuration(e.detail.value)} />
      <Input value={note} placeholder="备注" onInput={(e) => setNote(e.detail.value)} />
      <Button loading={loading} onClick={submit}>提交</Button>
    </View>
  );
}
```

- [x] **Step 3: Add action history page**

Create `miniapp/src/pages/action-history/index.tsx`:

```tsx
import { View, Text } from "@tarojs/components";
import { useDidShow, useRouter } from "@tarojs/taro";
import { useState } from "react";

import { request } from "../../api/client";

type History = {
  last_7_days_completed_count: number;
  last_30_days_completed_count: number;
  records: Array<{ id: number; training_date: string; status: string; actual_duration_minutes: number | null; note: string }>;
};

export default function ActionHistoryPage() {
  const router = useRouter();
  const actionId = Number(router.params.actionId);
  const [data, setData] = useState<History | null>(null);

  useDidShow(() => {
    request<History>(`/patient-app/actions/${actionId}/history/`).then(setData);
  });

  return (
    <View className="page action-history-page">
      <Text className="title">训练历史</Text>
      {data ? (
        <View>
          <Text>近 7 天完成：{data.last_7_days_completed_count} 次</Text>
          <Text>近 30 天完成：{data.last_30_days_completed_count} 次</Text>
          {data.records.map((record) => (
            <View key={record.id} className="history-row">
              <Text>{record.training_date} · {record.status}</Text>
              <Text>{record.actual_duration_minutes ?? "-"} 分钟</Text>
            </View>
          ))}
        </View>
      ) : (
        <Text>加载中</Text>
      )}
    </View>
  );
}
```

- [x] **Step 4: Add daily health page**

Create `miniapp/src/pages/daily-health/index.tsx`:

```tsx
import { Button, Input, View, Text } from "@tarojs/components";
import Taro, { useDidShow } from "@tarojs/taro";
import { useState } from "react";

import { request } from "../../api/client";

type DailyHealth = {
  steps: number | null;
  exercise_minutes: number | null;
  sleep_hours: string | null;
  note: string;
};

export default function DailyHealthPage() {
  const [steps, setSteps] = useState("");
  const [exerciseMinutes, setExerciseMinutes] = useState("");
  const [sleepHours, setSleepHours] = useState("");
  const [note, setNote] = useState("");

  useDidShow(() => {
    request<DailyHealth | null>("/patient-app/daily-health/today/").then((data) => {
      if (!data) return;
      setSteps(data.steps ? String(data.steps) : "");
      setExerciseMinutes(data.exercise_minutes ? String(data.exercise_minutes) : "");
      setSleepHours(data.sleep_hours ?? "");
      setNote(data.note ?? "");
    });
  });

  async function submit() {
    await request("/patient-app/daily-health/today/", {
      method: "PUT",
      data: {
        steps: steps ? Number(steps) : null,
        exercise_minutes: exerciseMinutes ? Number(exerciseMinutes) : null,
        sleep_hours: sleepHours || null,
        note,
      },
    });
    Taro.navigateBack();
  }

  return (
    <View className="page daily-health-page">
      <Text className="title">今日健康数据</Text>
      <Input type="number" value={steps} placeholder="步数" onInput={(e) => setSteps(e.detail.value)} />
      <Input type="number" value={exerciseMinutes} placeholder="运动时长（分钟）" onInput={(e) => setExerciseMinutes(e.detail.value)} />
      <Input type="digit" value={sleepHours} placeholder="睡眠时长（小时）" onInput={(e) => setSleepHours(e.detail.value)} />
      <Input value={note} placeholder="备注" onInput={(e) => setNote(e.detail.value)} />
      <Button onClick={submit}>保存</Button>
    </View>
  );
}
```

- [x] **Step 5: Add minimal shared styles**

Modify `miniapp/src/app.scss`:

```scss
.page {
  min-height: 100vh;
  padding: 24px;
  box-sizing: border-box;
  background: #f6f8fb;
}

.title {
  display: block;
  margin-bottom: 20px;
  font-size: 22px;
  font-weight: 600;
  color: #162033;
}

.error {
  display: block;
  margin: 12px 0;
  color: #c2410c;
}

.action-card,
.history-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 16px 0;
  padding: 16px;
  border-radius: 8px;
  background: #fff;
}
```

- [x] **Step 6: Verify miniapp build**

Run:

```bash
cd miniapp && npm run build:weapp
```

Expected: build succeeds.

- [ ] **Step 7: 提交小程序处方训练闭环页面**

暂未执行：用户尚未要求 commit。

```bash
git add miniapp/src
git commit -m "feat(miniapp): 新增处方训练历史与健康填报"
```

### Task 9: Full Verification And Documentation Index

执行记录（2026-05-14, codex）：Task 9 已执行但未提交；superpowers 索引已包含本 plan，最终验证通过：`pytest`（backend，187 passed；首次在隔离 worktree 缺少被忽略的 CRF docx 模板导致 1 fail，复制本地模板后通过）、`python manage.py makemigrations --check --dry-run`（No changes detected）、`npm run test`（frontend，105 passed）、`npm run lint`（0 errors，4 existing fast-refresh warnings）、`npm run build`（success，保留 Vite chunk-size warning）、`npm run build:weapp`（success）、`npx tsc --noEmit --skipLibCheck`（success）。`miniapp/dist/`、`miniapp/node_modules/`、`frontend/dist/` 与本地 `docs/other` CRF 模板均被 gitignore 忽略。

**Files:**
- Modify: `docs/superpowers/README.md`
- Modify: `docs/superpowers/plans/2026-05-14-wechat-miniapp-patient-daily-workbench.md`

- [x] **Step 1: Add this plan to the superpowers index**

Modify `docs/superpowers/README.md` under the plans table:

```markdown
| `plans/2026-05-14-wechat-miniapp-patient-daily-workbench.md` | 微信小程序患者日常工作台 | approved | `specs/2026-05-14-wechat-miniapp-patient-daily-workbench-design.md` |
```

- [x] **Step 2: Run backend verification**

Run:

```bash
cd backend && pytest
```

Expected: all backend tests pass.

- [x] **Step 3: Run frontend verification**

Run:

```bash
cd frontend && npm run test
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: all frontend tests, lint, and build pass.

- [x] **Step 4: Run miniapp verification**

Run:

```bash
cd miniapp && npm run build:weapp
```

Expected: Taro weapp build passes and writes output to `miniapp/dist/`.

- [x] **Step 5: Run git status review**

Run:

```bash
git status --short
```

Expected: only intended tracked files are modified; generated build output under `miniapp/dist/` is not staged.

- [ ] **Step 6: 提交计划索引和最终收口**

暂未执行：用户尚未要求 commit。

```bash
git add docs/superpowers/README.md docs/superpowers/plans/2026-05-14-wechat-miniapp-patient-daily-workbench.md
git commit -m "docs(plan): 新增微信小程序患者工作台实施计划"
```

## Self-Review Notes

- Spec coverage: binding code, single `ProjectPatient` identity, patient token boundary, current prescription, weekly progress, same-day multiple training records, action history limited to current action, global patient daily health, doctor-side binding management, and Taro miniapp pages are covered by Tasks 1-8.
- Type consistency: plan uses `weekly_target_count`, `PatientAppBindingCode`, `PatientAppSession`, `/api/patient-app/`, and `prescription_action` consistently across backend and miniapp tasks.
- Execution order: backend model and API tasks come before frontend and miniapp tasks so UI work can call stable endpoints.
