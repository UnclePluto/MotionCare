# 医生管理与默认密码强制修改 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Web 管理端新增医生管理、医生账号基础资料维护、当前账号改密，以及默认密码登录后的强制改密闭环。

**Architecture:** 沿用 `accounts.User` 作为医生账号模型，新增 `gender` 与 `must_change_password` 字段；医生 CRUD 使用现有 `/api/accounts/users/` 资源接口，当前账号改密使用 ViewSet list action。后端通过共享 DRF 权限门禁硬拦截 `must_change_password=true` 的业务接口，前端通过登录态字段显示不可关闭改密弹窗并提供医生管理/我的账号页面。

**Tech Stack:** Django 5 + DRF + pytest-django；React 18 + TypeScript + Vite + Ant Design 5 + TanStack Query v5 + Vitest。

---

执行记录（2026-05-15, codex）：Task 1 已落地于 commits 84d3b94、e5751e5、4d678c9、cd81293。
执行记录（2026-05-15, codex）：Task 2 已落地于 commits 24ce13b、47f935f。
执行记录（2026-05-15, codex）：Task 3 已落地于 commit b5ecaad。
执行记录（2026-05-15, codex）：Task 4 已落地于 commits 61c896d、d34cfdf、5c87974。

## Scope Check

本计划覆盖一个账号管理功能闭环：医生账号建模 -> 医生列表/新建/编辑 API -> 默认密码强制改密后端门禁 -> 前端菜单、页面与全局弹窗。它跨后端和前端，但功能不可独立拆分：前端强制改密依赖 `/api/me/` 新字段，后端门禁依赖改密接口，医生管理页面依赖账号序列化契约。

本计划不实现独立 `Doctor` 模型，不做账号删除、停用、管理员重置他人密码、完整审计日志或细粒度权限配置。

## File Structure

### 后端

- Modify: `backend/apps/accounts/models.py`
  - 新增 `User.Gender`、`gender`、`must_change_password`。
- Create: `backend/apps/accounts/migrations/0002_user_gender_must_change_password.py`
  - 为既有用户补默认值。
- Modify: `backend/apps/accounts/admin.py`
  - Django admin 显示新字段。
- Modify: `backend/apps/accounts/serializers.py`
  - 医生账号序列化、手机号校验、默认密码创建、当前账号改密序列化。
- Modify: `backend/apps/accounts/views.py`
  - 医生列表只列 `role=doctor`，新建医生默认密码，增加 `me/change-password` action。
- Modify: `backend/apps/accounts/auth_views.py`
  - `/api/me/` 返回 `gender`、`must_change_password`，doctor 权限加入 `user.manage`。
- Modify: `backend/apps/common/permissions.py`
  - 新增默认密码门禁 helper、全局默认权限类，并更新 `IsAdminOrDoctor`。
- Modify: `backend/config/settings.py`
  - 默认权限类切到 `apps.common.permissions.IsAuthenticatedAndPasswordChanged`。
- Test: `backend/apps/accounts/tests/test_user_model.py`
  - 覆盖新字段默认值。
- Create: `backend/apps/accounts/tests/test_doctor_management_api.py`
  - 覆盖医生列表、新建、编辑、手机号校验。
- Create: `backend/apps/accounts/tests/test_password_change_gate.py`
  - 覆盖强制改密门禁和改密接口。

### 前端

- Modify: `frontend/src/auth/AuthContext.tsx`
  - `Me` 类型增加 `gender`、`must_change_password`，新增 `changePassword`。
- Create: `frontend/src/auth/ForcePasswordChangeModal.tsx`
  - 不可关闭的强制改密弹窗。
- Modify: `frontend/src/app/layout/AdminLayout.tsx`
  - 新增医生管理菜单；Header 当前账号入口跳转 `/account`；挂载强制改密弹窗。
- Modify: `frontend/src/app/App.tsx`
  - 新增 `/doctors`、`/doctors/new`、`/doctors/:doctorId/edit`、`/account` 路由。
- Create: `frontend/src/pages/doctors/doctorUtils.ts`
  - 医生性别文案、手机号校验、时间格式化。
- Create: `frontend/src/pages/doctors/doctorUtils.test.ts`
  - 覆盖工具函数。
- Create: `frontend/src/pages/doctors/types.ts`
  - 医生账号类型与表单类型。
- Create: `frontend/src/pages/doctors/DoctorListPage.tsx`
  - 医生管理列表。
- Create: `frontend/src/pages/doctors/DoctorCreatePage.tsx`
  - 添加医生独立页面。
- Create: `frontend/src/pages/doctors/DoctorEditPage.tsx`
  - 编辑医生基础资料页面。
- Create: `frontend/src/pages/account/AccountPage.tsx`
  - 当前账号基础资料编辑与修改密码。
- Test: `frontend/src/auth/ForcePasswordChangeModal.test.tsx`
  - 覆盖不可关闭弹窗和改密成功。
- Test: `frontend/src/pages/doctors/DoctorListPage.test.tsx`
  - 覆盖列表列、脱敏手机号、跳转。
- Test: `frontend/src/pages/doctors/DoctorCreatePage.test.tsx`
  - 覆盖手机号校验、创建成功提示和返回列表。
- Test: `frontend/src/pages/doctors/DoctorEditPage.test.tsx`
  - 覆盖加载、保存和缓存刷新。
- Test: `frontend/src/pages/account/AccountPage.test.tsx`
  - 覆盖基础资料保存、改密成功刷新登录态。
- Modify: `frontend/src/app/App.test.tsx`
  - 更新 `/api/me/` mock 字段和新增入口 smoke 覆盖。

---

### Task 1: Backend User Fields And Doctor CRUD Contract

**Files:**
- Modify: `backend/apps/accounts/models.py`
- Create: `backend/apps/accounts/migrations/0002_user_gender_must_change_password.py`
- Modify: `backend/apps/accounts/admin.py`
- Modify: `backend/apps/accounts/serializers.py`
- Modify: `backend/apps/accounts/views.py`
- Modify: `backend/apps/accounts/auth_views.py`
- Modify: `backend/apps/accounts/tests/test_user_model.py`
- Create: `backend/apps/accounts/tests/test_doctor_management_api.py`

- [x] **Step 1: Extend the failing user model test**

Append to `backend/apps/accounts/tests/test_user_model.py`:

```python
@pytest.mark.django_db
def test_user_defaults_gender_and_password_change_flag():
    user = User.objects.create_user(
        phone="13700000000",
        password="pass123456",
        name="默认医生",
        role=User.Role.DOCTOR,
    )

    assert user.gender == User.Gender.UNKNOWN
    assert user.must_change_password is False
```

- [x] **Step 2: Add failing doctor management API tests**

Create `backend/apps/accounts/tests/test_doctor_management_api.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def auth_client(doctor):
    client = APIClient()
    client.force_authenticate(user=doctor)
    return client


@pytest.mark.django_db
def test_doctor_list_only_returns_doctor_accounts(auth_client):
    doctor = User.objects.create_user(
        phone="13700000001",
        password="pass123456",
        name="列表医生",
        role=User.Role.DOCTOR,
    )
    User.objects.create_user(
        phone="13700000002",
        password="pass123456",
        name="管理员",
        role=User.Role.ADMIN,
    )

    response = auth_client.get("/api/accounts/users/")

    assert response.status_code == 200, response.content
    rows = response.json()
    names = {row["name"] for row in rows}
    assert "列表医生" in names
    assert "管理员" not in names
    row = next(item for item in rows if item["id"] == doctor.id)
    assert row["gender"] == User.Gender.UNKNOWN
    assert row["role"] == User.Role.DOCTOR
    assert row["must_change_password"] is False
    assert row["date_joined"]


@pytest.mark.django_db
def test_create_doctor_uses_default_password_and_requires_change(auth_client):
    response = auth_client.post(
        "/api/accounts/users/",
        {
            "name": "新医生",
            "gender": User.Gender.FEMALE,
            "phone": "13700000003",
            "role": User.Role.SUPER_ADMIN,
            "must_change_password": False,
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    created = User.objects.get(phone="13700000003")
    assert created.name == "新医生"
    assert created.gender == User.Gender.FEMALE
    assert created.role == User.Role.DOCTOR
    assert created.must_change_password is True
    assert created.check_password("888888")
    assert response.json()["must_change_password"] is True


@pytest.mark.django_db
def test_create_doctor_rejects_invalid_phone(auth_client):
    response = auth_client.post(
        "/api/accounts/users/",
        {"name": "错误医生", "gender": User.Gender.MALE, "phone": "12345"},
        format="json",
    )

    assert response.status_code == 400
    assert "phone" in response.json()


@pytest.mark.django_db
def test_create_doctor_rejects_duplicate_phone(auth_client):
    User.objects.create_user(
        phone="13700000004",
        password="pass123456",
        name="已存在医生",
        role=User.Role.DOCTOR,
    )

    response = auth_client.post(
        "/api/accounts/users/",
        {"name": "重复医生", "gender": User.Gender.MALE, "phone": "13700000004"},
        format="json",
    )

    assert response.status_code == 400
    assert "phone" in response.json()


@pytest.mark.django_db
def test_update_doctor_basic_profile_does_not_change_password_or_role(auth_client):
    target = User.objects.create_user(
        phone="13700000005",
        password="pass123456",
        name="待编辑医生",
        role=User.Role.DOCTOR,
    )

    response = auth_client.patch(
        f"/api/accounts/users/{target.id}/",
        {
            "name": "已编辑医生",
            "gender": User.Gender.MALE,
            "phone": "13700000006",
            "role": User.Role.SUPER_ADMIN,
            "password": "hacked-password",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    target.refresh_from_db()
    assert target.name == "已编辑医生"
    assert target.gender == User.Gender.MALE
    assert target.phone == "13700000006"
    assert target.username == "13700000006"
    assert target.role == User.Role.DOCTOR
    assert target.check_password("pass123456")
```

- [x] **Step 3: Run the backend account tests and verify they fail**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/accounts/tests/test_user_model.py apps/accounts/tests/test_doctor_management_api.py -q
```

Expected: FAIL because `User.Gender`, `gender`, `must_change_password`, tightened serializer behavior, and doctor list filtering do not exist.

- [x] **Step 4: Add user fields to the model**

Modify `backend/apps/accounts/models.py`:

```python
class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "超级管理员"
        ADMIN = "admin", "管理员"
        DOCTOR = "doctor", "医生"

    class Gender(models.TextChoices):
        MALE = "male", "男"
        FEMALE = "female", "女"
        UNKNOWN = "unknown", "未知"

    phone = models.CharField("手机号", max_length=20, unique=True)
    name = models.CharField("姓名", max_length=80)
    gender = models.CharField("性别", max_length=16, choices=Gender.choices, default=Gender.UNKNOWN)
    role = models.CharField("角色", max_length=32, choices=Role.choices, default=Role.DOCTOR)
    must_change_password = models.BooleanField("是否必须修改密码", default=False)

    objects = MotionCareUserManager()
    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["name"]

    def save(self, *args, **kwargs):
        if self.phone:
            self.username = self.phone
        super().save(*args, **kwargs)
```

- [x] **Step 5: Create the migration**

Create `backend/apps/accounts/migrations/0002_user_gender_must_change_password.py`:

```python
# Generated by Codex on 2026-05-15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="gender",
            field=models.CharField(
                choices=[("male", "男"), ("female", "女"), ("unknown", "未知")],
                default="unknown",
                max_length=16,
                verbose_name="性别",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="must_change_password",
            field=models.BooleanField(default=False, verbose_name="是否必须修改密码"),
        ),
    ]
```

- [x] **Step 6: Update Django admin fields**

Modify `backend/apps/accounts/admin.py`:

```python
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class MotionCareUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("MotionCare", {"fields": ("phone", "name", "gender", "role", "must_change_password")}),
    )
    list_display = ("phone", "name", "gender", "role", "must_change_password", "is_active", "is_staff")
    search_fields = ("phone", "name")
```

- [x] **Step 7: Replace the account serializer**

Replace `backend/apps/accounts/serializers.py` with:

```python
import re

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User

DEFAULT_DOCTOR_PASSWORD = "888888"
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


class UserSerializer(serializers.ModelSerializer):
    date_joined = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "name",
            "gender",
            "role",
            "date_joined",
            "must_change_password",
            "is_active",
        ]
        read_only_fields = ["id", "role", "date_joined", "must_change_password", "is_active"]

    def validate_phone(self, value: str) -> str:
        phone = value.strip()
        if not PHONE_RE.match(phone):
            raise serializers.ValidationError("请输入 11 位有效手机号")
        qs = User.objects.filter(phone=phone)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("该手机号已存在")
        return phone

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if not name:
            raise serializers.ValidationError("请输入姓名")
        return name

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(
            phone=validated_data["phone"],
            password=DEFAULT_DOCTOR_PASSWORD,
            name=validated_data["name"],
            gender=validated_data.get("gender", User.Gender.UNKNOWN),
            role=User.Role.DOCTOR,
            must_change_password=True,
        )

    def update(self, instance: User, validated_data: dict) -> User:
        for field in ("name", "gender", "phone"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict) -> dict:
        user = self.context["request"].user
        old_password = attrs["old_password"]
        new_password = attrs["new_password"]
        confirm_password = attrs["confirm_password"]

        if not user.check_password(old_password):
            raise serializers.ValidationError({"old_password": "原密码错误"})
        if new_password != confirm_password:
            raise serializers.ValidationError({"confirm_password": "两次输入的新密码不一致"})
        if new_password == DEFAULT_DOCTOR_PASSWORD:
            raise serializers.ValidationError({"new_password": "新密码不能使用默认密码"})
        validate_password(new_password, user=user)
        return attrs
```

- [x] **Step 8: Update account viewset behavior**

Modify `backend/apps/accounts/views.py`:

```python
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import User
from .serializers import ChangePasswordSerializer, UserSerializer


class UserViewSet(ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        qs = User.objects.order_by("-date_joined", "-id")
        if self.action == "list":
            return qs.filter(role=User.Role.DOCTOR)
        return qs

    @action(detail=False, methods=["post"], url_path="me/change-password")
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.must_change_password = False
        request.user.save(update_fields=["password", "must_change_password"])
        return Response({"detail": "密码已修改"})
```

- [x] **Step 9: Update `/api/me/` and doctor permissions**

Modify `backend/apps/accounts/auth_views.py`:

```python
    User.Role.DOCTOR: [
        "patient.read",
        "patient.write",
        "project.read",
        "project.write",
        "randomization.confirm",
        "visit.write",
        "prescription.write",
        "prescription.terminate",
        "training.write",
        "health.write",
        "crf.read",
        "crf.export",
        "user.manage",
    ],
```

In `MeView.get`, return the new fields:

```python
                "gender": user.gender,
                "must_change_password": user.must_change_password,
```

- [x] **Step 10: Run the backend account tests and verify they pass**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/accounts/tests/test_user_model.py apps/accounts/tests/test_doctor_management_api.py apps/accounts/tests/test_auth_flow.py -q
```

Expected: PASS.

- [x] **Step 11: Commit Task 1**

Run:

```bash
git add backend/apps/accounts/models.py backend/apps/accounts/migrations/0002_user_gender_must_change_password.py backend/apps/accounts/admin.py backend/apps/accounts/serializers.py backend/apps/accounts/views.py backend/apps/accounts/auth_views.py backend/apps/accounts/tests/test_user_model.py backend/apps/accounts/tests/test_doctor_management_api.py
git commit -m "feat(accounts): 新增医生账号基础管理"
```

Expected: commit succeeds.

---

### Task 2: Backend Forced Password Change Gate

**Files:**
- Modify: `backend/apps/common/permissions.py`
- Modify: `backend/config/settings.py`
- Create: `backend/apps/accounts/tests/test_password_change_gate.py`

- [x] **Step 1: Add failing backend gate tests**

Create `backend/apps/accounts/tests/test_password_change_gate.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def forced_user(db):
    return User.objects.create_user(
        phone="13700001000",
        password="888888",
        name="默认密码医生",
        role=User.Role.DOCTOR,
        must_change_password=True,
    )


@pytest.fixture
def forced_client(forced_user):
    client = APIClient()
    client.force_authenticate(user=forced_user)
    return client


@pytest.mark.django_db
def test_forced_password_change_blocks_business_api(forced_client):
    response = forced_client.get("/api/patients/")

    assert response.status_code == 403
    assert response.json()["detail"] == "请先修改默认密码"


@pytest.mark.django_db
def test_forced_password_change_allows_me_endpoint(forced_client):
    response = forced_client.get("/api/me/")

    assert response.status_code == 200
    assert response.json()["must_change_password"] is True


@pytest.mark.django_db
def test_forced_password_change_rejects_default_password(forced_client):
    response = forced_client.post(
        "/api/accounts/users/me/change-password/",
        {
            "old_password": "888888",
            "new_password": "888888",
            "confirm_password": "888888",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "new_password" in response.json()


@pytest.mark.django_db
def test_forced_password_change_accepts_new_password(forced_client, forced_user):
    response = forced_client.post(
        "/api/accounts/users/me/change-password/",
        {
            "old_password": "888888",
            "new_password": "newpass123456",
            "confirm_password": "newpass123456",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    forced_user.refresh_from_db()
    assert forced_user.must_change_password is False
    assert forced_user.check_password("newpass123456")


@pytest.mark.django_db
def test_change_password_rejects_wrong_old_password(forced_client):
    response = forced_client.post(
        "/api/accounts/users/me/change-password/",
        {
            "old_password": "wrong-password",
            "new_password": "newpass123456",
            "confirm_password": "newpass123456",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "old_password" in response.json()


@pytest.mark.django_db
def test_global_default_permission_blocks_force_authenticated_default_password_user(forced_user):
    client = APIClient()
    client.force_authenticate(user=forced_user)

    response = client.get("/api/patient-app/me/")

    assert response.status_code == 403
    assert response.json()["detail"] == "请先修改默认密码"
```

- [x] **Step 2: Run the gate tests and verify they fail**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/accounts/tests/test_password_change_gate.py -q
```

Expected: FAIL because password-change gate is not enforced yet.

- [x] **Step 3: Add shared permission helpers**

Replace `backend/apps/common/permissions.py` with:

```python
from rest_framework.permissions import BasePermission


PASSWORD_CHANGE_ALLOWED_PATHS = {
    "/api/me/",
    "/api/auth/logout/",
    "/api/accounts/users/me/change-password/",
}


def is_password_change_allowed_path(path: str) -> bool:
    normalized = path if path.endswith("/") else f"{path}/"
    return normalized in PASSWORD_CHANGE_ALLOWED_PATHS


def passes_password_change_gate(request) -> bool:
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "must_change_password", False) and not is_password_change_allowed_path(request.path):
        return False
    return True


class IsAuthenticatedAndPasswordChanged(BasePermission):
    message = "请先修改默认密码"

    def has_permission(self, request, view):
        return passes_password_change_gate(request)


class IsAdminOrDoctor(BasePermission):
    message = "请先修改默认密码"

    def has_permission(self, request, view):
        return bool(
            passes_password_change_gate(request)
            and request.user.role in {"super_admin", "admin", "doctor"}
        )
```

- [x] **Step 4: Switch the global DRF default permission**

Modify `backend/config/settings.py`:

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["apps.common.permissions.IsAuthenticatedAndPasswordChanged"],
}
```

- [x] **Step 5: Run the gate and auth tests**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/accounts/tests/test_password_change_gate.py apps/accounts/tests/test_auth_flow.py -q
```

Expected: PASS.

- [x] **Step 6: Run a focused backend regression set**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/accounts/tests apps/patients/tests/test_patient_baseline_api.py apps/studies/tests/test_project_patient_binding_api.py -q
```

Expected: PASS. If a test creates `role="patient"` and expects a 403 from `IsAdminOrDoctor`, keep that behavior: the new gate must not grant access to non-admin/non-doctor roles.

- [x] **Step 7: Commit Task 2**

Run:

```bash
git add backend/apps/common/permissions.py backend/config/settings.py backend/apps/accounts/tests/test_password_change_gate.py
git commit -m "fix(accounts): 强制默认密码账号先改密"
```

Expected: commit succeeds.

---

### Task 3: Frontend Auth State And Forced Password Modal

**Files:**
- Modify: `frontend/src/auth/AuthContext.tsx`
- Create: `frontend/src/auth/ForcePasswordChangeModal.tsx`
- Test: `frontend/src/auth/ForcePasswordChangeModal.test.tsx`

- [x] **Step 1: Add failing modal tests**

Create `frontend/src/auth/ForcePasswordChangeModal.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ForcePasswordChangeModal } from "./ForcePasswordChangeModal";

const { mockPost } = vi.hoisted(() => ({
  mockPost: vi.fn(),
}));

vi.mock("../api/client", () => ({
  apiClient: {
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

function renderModal(options?: { onChanged?: () => void; onLogout?: () => void }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onChanged = options?.onChanged ?? vi.fn();
  const onLogout = options?.onLogout ?? vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <ForcePasswordChangeModal open onChanged={onChanged} onLogout={onLogout} />
    </QueryClientProvider>,
  );
  return { onChanged, onLogout };
}

describe("ForcePasswordChangeModal", () => {
  it("renders as a blocking dialog without close controls", () => {
    renderModal();

    expect(screen.getByText("请先修改默认密码")).toBeInTheDocument();
    expect(screen.queryByLabelText("Close")).not.toBeInTheDocument();
    expect(screen.queryByText("稍后再说")).not.toBeInTheDocument();
  });

  it("submits password change and notifies caller", async () => {
    mockPost.mockResolvedValueOnce({ data: { detail: "密码已修改" } });
    const { onChanged } = renderModal();

    fireEvent.change(screen.getByLabelText("原密码"), { target: { value: "888888" } });
    fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "newpass123456" } });
    fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "newpass123456" } });
    fireEvent.click(screen.getByRole("button", { name: "修改密码" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/accounts/users/me/change-password/", {
        old_password: "888888",
        new_password: "newpass123456",
        confirm_password: "newpass123456",
      });
      expect(onChanged).toHaveBeenCalled();
    });
  });

  it("allows logout from the blocking dialog", () => {
    const { onLogout } = renderModal();

    fireEvent.click(screen.getByRole("button", { name: "退出登录" }));

    expect(onLogout).toHaveBeenCalled();
  });
});
```

- [x] **Step 2: Run the modal test and verify it fails**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npx vitest run src/auth/ForcePasswordChangeModal.test.tsx
```

Expected: FAIL because `ForcePasswordChangeModal` does not exist.

- [x] **Step 3: Extend `Me` and add `changePassword` to AuthContext**

Modify `frontend/src/auth/AuthContext.tsx`:

```tsx
export type Me = {
  id: number;
  phone: string;
  name: string;
  gender: "male" | "female" | "unknown";
  role: string;
  roles: string[];
  permissions: string[];
  must_change_password: boolean;
};

type AuthContextValue = {
  me: Me | null | undefined;
  loading: boolean;
  error: unknown | null;
  refetchSession: () => Promise<unknown>;
  login: (phone: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (values: {
    old_password: string;
    new_password: string;
    confirm_password: string;
  }) => Promise<void>;
};
```

Inside `AuthProvider`, add:

```tsx
  const changePassword = useCallback(
    async (values: { old_password: string; new_password: string; confirm_password: string }) => {
      await apiClient.post("/accounts/users/me/change-password/", values);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    [queryClient],
  );
```

Add `changePassword` to `value` and the `useMemo` dependency list.

- [x] **Step 4: Create the blocking password modal**

Create `frontend/src/auth/ForcePasswordChangeModal.tsx`:

```tsx
import { Button, Form, Input, Modal, Space, Typography, message } from "antd";
import { isAxiosError } from "axios";
import { useState } from "react";

import { apiClient } from "../api/client";

type PasswordFormValues = {
  old_password: string;
  new_password: string;
  confirm_password: string;
};

function backendDetail(err: unknown): string | null {
  if (!isAxiosError(err)) return null;
  const data = err.response?.data;
  if (!data || typeof data !== "object") return null;
  if ("detail" in data && typeof (data as { detail?: unknown }).detail === "string") {
    return (data as { detail: string }).detail;
  }
  const parts = Object.entries(data as Record<string, unknown>).map(([key, value]) => {
    if (Array.isArray(value)) return `${key}: ${value.map(String).join(", ")}`;
    if (typeof value === "string") return `${key}: ${value}`;
    return `${key}: ${JSON.stringify(value)}`;
  });
  return parts.length ? parts.join("；") : null;
}

export function ForcePasswordChangeModal({
  open,
  onChanged,
  onLogout,
}: {
  open: boolean;
  onChanged: () => void;
  onLogout: () => void;
}) {
  const [form] = Form.useForm<PasswordFormValues>();
  const [submitting, setSubmitting] = useState(false);

  const onFinish = async (values: PasswordFormValues) => {
    setSubmitting(true);
    try {
      await apiClient.post("/accounts/users/me/change-password/", values);
      message.success("密码已修改");
      form.resetFields();
      onChanged();
    } catch (err) {
      message.error(backendDetail(err) ?? "修改密码失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="请先修改默认密码"
      open={open}
      footer={null}
      closable={false}
      maskClosable={false}
      keyboard={false}
      destroyOnClose
    >
      <Typography.Paragraph type="secondary">
        当前账号仍在使用系统默认密码。修改密码后才可以继续使用系统。
      </Typography.Paragraph>
      <Form<PasswordFormValues> form={form} layout="vertical" onFinish={onFinish}>
        <Form.Item label="原密码" name="old_password" rules={[{ required: true, message: "请输入原密码" }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item
          label="新密码"
          name="new_password"
          rules={[{ required: true, message: "请输入新密码" }]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          label="确认新密码"
          name="confirm_password"
          dependencies={["new_password"]}
          rules={[
            { required: true, message: "请再次输入新密码" },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue("new_password") === value) return Promise.resolve();
                return Promise.reject(new Error("两次输入的新密码不一致"));
              },
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={submitting}>
              修改密码
            </Button>
            <Button onClick={onLogout}>退出登录</Button>
          </Space>
        </Form.Item>
      </Form>
    </Modal>
  );
}
```

- [x] **Step 5: Run the modal test and verify it passes**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npx vitest run src/auth/ForcePasswordChangeModal.test.tsx
```

Expected: PASS.

- [x] **Step 6: Commit Task 3**

Run:

```bash
git add frontend/src/auth/AuthContext.tsx frontend/src/auth/ForcePasswordChangeModal.tsx frontend/src/auth/ForcePasswordChangeModal.test.tsx
git commit -m "feat(frontend): 新增默认密码强制改密弹窗"
```

Expected: commit succeeds.

---

### Task 4: Frontend Doctor Management And Account Pages

**Files:**
- Modify: `frontend/src/app/layout/AdminLayout.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/App.test.tsx`
- Create: `frontend/src/pages/doctors/types.ts`
- Create: `frontend/src/pages/doctors/doctorUtils.ts`
- Create: `frontend/src/pages/doctors/doctorUtils.test.ts`
- Create: `frontend/src/pages/doctors/DoctorListPage.tsx`
- Create: `frontend/src/pages/doctors/DoctorListPage.test.tsx`
- Create: `frontend/src/pages/doctors/DoctorCreatePage.tsx`
- Create: `frontend/src/pages/doctors/DoctorCreatePage.test.tsx`
- Create: `frontend/src/pages/doctors/DoctorEditPage.tsx`
- Create: `frontend/src/pages/doctors/DoctorEditPage.test.tsx`
- Create: `frontend/src/pages/account/AccountPage.tsx`
- Create: `frontend/src/pages/account/AccountPage.test.tsx`

- [x] **Step 1: Add doctor utility tests**

Create `frontend/src/pages/doctors/doctorUtils.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { formatDoctorDateTime, isValidMainlandPhone } from "./doctorUtils";

describe("doctorUtils", () => {
  it("validates mainland mobile phone numbers", () => {
    expect(isValidMainlandPhone("13812345678")).toBe(true);
    expect(isValidMainlandPhone("12812345678")).toBe(false);
    expect(isValidMainlandPhone("1381234567")).toBe(false);
  });

  it("formats date time for list display", () => {
    expect(formatDoctorDateTime("2026-05-15T10:20:00+08:00")).toBe("2026-05-15 10:20");
    expect(formatDoctorDateTime("")).toBe("—");
    expect(formatDoctorDateTime(null)).toBe("—");
  });
});
```

- [x] **Step 2: Implement doctor utility files**

Create `frontend/src/pages/doctors/types.ts`:

```ts
export type DoctorGender = "male" | "female" | "unknown";

export type Doctor = {
  id: number;
  phone: string;
  name: string;
  gender: DoctorGender;
  role: string;
  date_joined: string;
  must_change_password: boolean;
  is_active: boolean;
};

export type DoctorFormValues = {
  name: string;
  gender: DoctorGender;
  phone: string;
};
```

Create `frontend/src/pages/doctors/doctorUtils.ts`:

```ts
import dayjs from "dayjs";

import type { DoctorGender } from "./types";

export const doctorGenderLabel: Record<DoctorGender, string> = {
  male: "男",
  female: "女",
  unknown: "未知",
};

export function isValidMainlandPhone(value: string): boolean {
  return /^1[3-9]\d{9}$/.test(value.trim());
}

export function formatDoctorDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = dayjs(value);
  return d.isValid() ? d.format("YYYY-MM-DD HH:mm") : "—";
}
```

- [x] **Step 3: Run utility tests**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npx vitest run src/pages/doctors/doctorUtils.test.ts
```

Expected: PASS.

- [x] **Step 4: Add failing page tests**

Create `frontend/src/pages/doctors/DoctorListPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { DoctorListPage } from "./DoctorListPage";

const { mockGet, mockNavigate } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockNavigate: vi.fn(),
}));

vi.mock("../../api/client", () => ({ apiClient: { get: (...args: unknown[]) => mockGet(...args) } }));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DoctorListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DoctorListPage", () => {
  it("renders doctors with masked phone and navigates to create/edit", async () => {
    mockGet.mockResolvedValueOnce({
      data: [
        {
          id: 1,
          name: "王医生",
          phone: "13812345678",
          gender: "male",
          role: "doctor",
          date_joined: "2026-05-15T10:20:00+08:00",
          must_change_password: false,
          is_active: true,
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("王医生")).toBeInTheDocument();
    expect(screen.getByText("138****5678")).toBeInTheDocument();
    expect(screen.getByText("2026-05-15 10:20")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "添加医生" }));
    expect(mockNavigate).toHaveBeenCalledWith("/doctors/new");
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/doctors/1/edit"));
  });
});
```

Create `frontend/src/pages/doctors/DoctorCreatePage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { DoctorCreatePage } from "./DoctorCreatePage";

const { mockPost, mockNavigate } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockNavigate: vi.fn(),
}));

vi.mock("../../api/client", () => ({ apiClient: { post: (...args: unknown[]) => mockPost(...args) } }));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DoctorCreatePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DoctorCreatePage", () => {
  it("validates phone before submit", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: "新医生" } });
    fireEvent.change(screen.getByLabelText("手机号"), { target: { value: "12345" } });
    fireEvent.click(screen.getByRole("button", { name: "创建" }));

    expect(await screen.findByText("请输入 11 位有效手机号")).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("creates doctor and returns to list", async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 2 } });
    renderPage();

    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: "新医生" } });
    fireEvent.change(screen.getByLabelText("手机号"), { target: { value: "13812345678" } });
    fireEvent.click(screen.getByRole("button", { name: "创建" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/accounts/users/", {
        name: "新医生",
        gender: "unknown",
        phone: "13812345678",
      });
      expect(mockNavigate).toHaveBeenCalledWith("/doctors");
    });
  });
});
```

Create `frontend/src/pages/doctors/DoctorEditPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { DoctorEditPage } from "./DoctorEditPage";

const { mockGet, mockPatch, mockNavigate } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPatch: vi.fn(),
  mockNavigate: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
  },
}));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate, useParams: () => ({ doctorId: "3" }) };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DoctorEditPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DoctorEditPage", () => {
  it("loads and saves doctor profile", async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        id: 3,
        name: "旧医生",
        phone: "13812345678",
        gender: "female",
        role: "doctor",
        date_joined: "2026-05-15T10:20:00+08:00",
        must_change_password: false,
        is_active: true,
      },
    });
    mockPatch.mockResolvedValueOnce({ data: {} });

    renderPage();

    expect(await screen.findByDisplayValue("旧医生")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: "新医生" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith("/accounts/users/3/", {
        name: "新医生",
        gender: "female",
        phone: "13812345678",
      });
      expect(mockNavigate).toHaveBeenCalledWith("/doctors");
    });
  });
});
```

Create `frontend/src/pages/account/AccountPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AccountPage } from "./AccountPage";

const { mockPatch, mockPost } = vi.hoisted(() => ({
  mockPatch: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    patch: (...args: unknown[]) => mockPatch(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));
vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({
    me: {
      id: 9,
      name: "当前医生",
      phone: "13812345678",
      gender: "male",
      role: "doctor",
      roles: ["doctor"],
      permissions: ["user.manage"],
      must_change_password: false,
    },
    refetchSession: vi.fn(),
  }),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AccountPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AccountPage", () => {
  it("updates current profile", async () => {
    mockPatch.mockResolvedValueOnce({ data: {} });
    renderPage();

    fireEvent.change(screen.getByLabelText("姓名"), { target: { value: "新姓名" } });
    fireEvent.click(screen.getByRole("button", { name: "保存资料" }));

    await waitFor(() => {
      expect(mockPatch).toHaveBeenCalledWith("/accounts/users/9/", {
        name: "新姓名",
        gender: "male",
        phone: "13812345678",
      });
    });
  });

  it("changes current password", async () => {
    mockPost.mockResolvedValueOnce({ data: { detail: "密码已修改" } });
    renderPage();

    fireEvent.change(screen.getByLabelText("原密码"), { target: { value: "oldpass123456" } });
    fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "newpass123456" } });
    fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "newpass123456" } });
    fireEvent.click(screen.getByRole("button", { name: "修改密码" }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/accounts/users/me/change-password/", {
        old_password: "oldpass123456",
        new_password: "newpass123456",
        confirm_password: "newpass123456",
      });
    });
  });
});
```

- [x] **Step 5: Run page tests and verify they fail**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npx vitest run src/pages/doctors/DoctorListPage.test.tsx src/pages/doctors/DoctorCreatePage.test.tsx src/pages/doctors/DoctorEditPage.test.tsx src/pages/account/AccountPage.test.tsx
```

Expected: FAIL because page components do not exist.

- [x] **Step 6: Create doctor list page**

Create `frontend/src/pages/doctors/DoctorListPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Space, Table } from "antd";
import { useNavigate } from "react-router-dom";

import { apiClient } from "../../api/client";
import { maskPhoneForList } from "../patients/phoneMask";
import { formatDoctorDateTime } from "./doctorUtils";
import type { Doctor } from "./types";

export function DoctorListPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["doctors"],
    queryFn: async () => {
      const r = await apiClient.get<Doctor[]>("/accounts/users/");
      return r.data;
    },
  });

  return (
    <Card title="医生管理" extra={<Button type="primary" onClick={() => navigate("/doctors/new")}>添加医生</Button>}>
      <Table<Doctor>
        rowKey="id"
        loading={isLoading}
        dataSource={data ?? []}
        columns={[
          { title: "医生姓名", dataIndex: "name" },
          { title: "手机号", dataIndex: "phone", render: (v: string) => maskPhoneForList(v ?? "") },
          { title: "创建时间", dataIndex: "date_joined", render: (v: string) => formatDoctorDateTime(v) },
          {
            title: "操作",
            key: "actions",
            render: (_: unknown, row) => (
              <Space>
                <Button type="link" style={{ padding: 0 }} onClick={() => navigate(`/doctors/${row.id}/edit`)}>
                  编辑
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
```

- [x] **Step 7: Create doctor create page**

Create `frontend/src/pages/doctors/DoctorCreatePage.tsx`:

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, Radio, Space, message } from "antd";
import { isAxiosError } from "axios";
import { useNavigate } from "react-router-dom";

import { apiClient } from "../../api/client";
import { isValidMainlandPhone } from "./doctorUtils";
import type { DoctorFormValues } from "./types";

function backendDetail(err: unknown): string | null {
  if (!isAxiosError(err)) return null;
  const data = err.response?.data;
  if (!data || typeof data !== "object") return null;
  const parts = Object.entries(data as Record<string, unknown>).map(([key, value]) => {
    if (Array.isArray(value)) return `${key}: ${value.map(String).join(", ")}`;
    if (typeof value === "string") return `${key}: ${value}`;
    return `${key}: ${JSON.stringify(value)}`;
  });
  return parts.length ? parts.join("；") : null;
}

export function DoctorCreatePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [form] = Form.useForm<DoctorFormValues>();

  const createMutation = useMutation({
    mutationFn: async (values: DoctorFormValues) => {
      await apiClient.post("/accounts/users/", {
        name: values.name.trim(),
        gender: values.gender,
        phone: values.phone.trim(),
      });
    },
    onSuccess: async () => {
      message.success("创建成功。默认密码为 888888，建议登录后立刻修改。");
      form.resetFields();
      await qc.invalidateQueries({ queryKey: ["doctors"] });
      navigate("/doctors");
    },
    onError: (err) => message.error(backendDetail(err) ?? "创建失败"),
  });

  return (
    <Card title="添加医生" extra={<Button onClick={() => navigate("/doctors")}>返回列表</Button>}>
      <Form<DoctorFormValues>
        form={form}
        layout="vertical"
        initialValues={{ gender: "unknown" }}
        onFinish={(v) => createMutation.mutate(v)}
        style={{ maxWidth: 560 }}
      >
        <Form.Item label="姓名" name="name" rules={[{ required: true, message: "请输入姓名" }]}>
          <Input />
        </Form.Item>
        <Form.Item label="性别" name="gender" rules={[{ required: true }]}>
          <Radio.Group
            options={[
              { value: "male", label: "男" },
              { value: "female", label: "女" },
              { value: "unknown", label: "未知" },
            ]}
          />
        </Form.Item>
        <Form.Item
          label="手机号"
          name="phone"
          rules={[
            { required: true, message: "请输入手机号" },
            {
              validator(_, value) {
                if (!value || isValidMainlandPhone(value)) return Promise.resolve();
                return Promise.reject(new Error("请输入 11 位有效手机号"));
              },
            },
          ]}
        >
          <Input />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
              创建
            </Button>
            <Button onClick={() => navigate("/doctors")}>取消</Button>
          </Space>
        </Form.Item>
      </Form>
    </Card>
  );
}
```

- [x] **Step 8: Create doctor edit page**

Create `frontend/src/pages/doctors/DoctorEditPage.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Radio, Space, message } from "antd";
import { isAxiosError } from "axios";
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "../../api/client";
import { isValidMainlandPhone } from "./doctorUtils";
import type { Doctor, DoctorFormValues } from "./types";

function backendDetail(err: unknown): string | null {
  if (!isAxiosError(err)) return null;
  const data = err.response?.data;
  if (!data || typeof data !== "object") return null;
  if ("detail" in data && typeof (data as { detail?: unknown }).detail === "string") return (data as { detail: string }).detail;
  return Object.entries(data as Record<string, unknown>)
    .map(([key, value]) => (Array.isArray(value) ? `${key}: ${value.map(String).join(", ")}` : `${key}: ${String(value)}`))
    .join("；");
}

export function DoctorEditPage() {
  const { doctorId } = useParams();
  const id = Number(doctorId);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [form] = Form.useForm<DoctorFormValues>();

  const { data: doctor, isLoading, isError, error } = useQuery({
    queryKey: ["doctor", doctorId ?? ""],
    queryFn: async () => {
      const r = await apiClient.get<Doctor>(`/accounts/users/${id}/`);
      return r.data;
    },
    enabled: Number.isSafeInteger(id) && id > 0,
  });

  useEffect(() => {
    if (!doctor) return;
    form.setFieldsValue({ name: doctor.name, gender: doctor.gender, phone: doctor.phone });
  }, [doctor, form]);

  const saveMutation = useMutation({
    mutationFn: async (values: DoctorFormValues) => {
      await apiClient.patch(`/accounts/users/${id}/`, {
        name: values.name.trim(),
        gender: values.gender,
        phone: values.phone.trim(),
      });
    },
    onSuccess: async () => {
      message.success("医生资料已保存");
      await qc.invalidateQueries({ queryKey: ["doctors"] });
      await qc.invalidateQueries({ queryKey: ["doctor", String(id)] });
      navigate("/doctors");
    },
    onError: (err) => message.error(backendDetail(err) || "保存失败"),
  });

  if (!Number.isSafeInteger(id) || id <= 0) return <Alert type="error" message="无效的医生 ID" />;
  if (isError) return <Alert type="error" message={backendDetail(error) || "医生不存在或无权限访问"} />;

  return (
    <Card loading={isLoading} title={doctor ? `编辑：${doctor.name}` : "编辑医生"} extra={<Button onClick={() => navigate("/doctors")}>返回列表</Button>}>
      {doctor && (
        <Form<DoctorFormValues> form={form} layout="vertical" onFinish={(v) => saveMutation.mutate(v)} style={{ maxWidth: 560 }}>
          <Form.Item label="姓名" name="name" rules={[{ required: true, message: "请输入姓名" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="性别" name="gender" rules={[{ required: true }]}>
            <Radio.Group options={[{ value: "male", label: "男" }, { value: "female", label: "女" }, { value: "unknown", label: "未知" }]} />
          </Form.Item>
          <Form.Item
            label="手机号"
            name="phone"
            rules={[
              { required: true, message: "请输入手机号" },
              {
                validator(_, value) {
                  if (!value || isValidMainlandPhone(value)) return Promise.resolve();
                  return Promise.reject(new Error("请输入 11 位有效手机号"));
                },
              },
            ]}
          >
            <Input />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
                保存
              </Button>
              <Button onClick={() => navigate("/doctors")}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      )}
    </Card>
  );
}
```

- [x] **Step 9: Create account page**

Create `frontend/src/pages/account/AccountPage.tsx`:

```tsx
import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Card, Divider, Form, Input, Radio, Space, message } from "antd";
import { isAxiosError } from "axios";
import { useEffect } from "react";

import { apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { isValidMainlandPhone } from "../doctors/doctorUtils";
import type { DoctorFormValues } from "../doctors/types";

type PasswordValues = {
  old_password: string;
  new_password: string;
  confirm_password: string;
};

function backendDetail(err: unknown): string | null {
  if (!isAxiosError(err)) return null;
  const data = err.response?.data;
  if (!data || typeof data !== "object") return null;
  return Object.entries(data as Record<string, unknown>)
    .map(([key, value]) => (Array.isArray(value) ? `${key}: ${value.map(String).join(", ")}` : `${key}: ${String(value)}`))
    .join("；");
}

export function AccountPage() {
  const { me, refetchSession } = useAuth();
  const [profileForm] = Form.useForm<DoctorFormValues>();
  const [passwordForm] = Form.useForm<PasswordValues>();

  useEffect(() => {
    if (!me) return;
    profileForm.setFieldsValue({ name: me.name, gender: me.gender, phone: me.phone });
  }, [me, profileForm]);

  const profileMutation = useMutation({
    mutationFn: async (values: DoctorFormValues) => {
      if (!me) return;
      await apiClient.patch(`/accounts/users/${me.id}/`, {
        name: values.name.trim(),
        gender: values.gender,
        phone: values.phone.trim(),
      });
    },
    onSuccess: async () => {
      message.success("账号资料已保存");
      await refetchSession();
    },
    onError: (err) => message.error(backendDetail(err) || "保存失败"),
  });

  const passwordMutation = useMutation({
    mutationFn: async (values: PasswordValues) => {
      await apiClient.post("/accounts/users/me/change-password/", values);
    },
    onSuccess: async () => {
      message.success("密码已修改");
      passwordForm.resetFields();
      await refetchSession();
    },
    onError: (err) => message.error(backendDetail(err) || "修改密码失败"),
  });

  if (!me) return <Alert type="error" message="无法读取当前账号" />;

  return (
    <Card title="我的账号">
      <Form<DoctorFormValues> form={profileForm} layout="vertical" onFinish={(v) => profileMutation.mutate(v)} style={{ maxWidth: 560 }}>
        <Form.Item label="姓名" name="name" rules={[{ required: true, message: "请输入姓名" }]}>
          <Input />
        </Form.Item>
        <Form.Item label="性别" name="gender" rules={[{ required: true }]}>
          <Radio.Group options={[{ value: "male", label: "男" }, { value: "female", label: "女" }, { value: "unknown", label: "未知" }]} />
        </Form.Item>
        <Form.Item
          label="手机号"
          name="phone"
          rules={[
            { required: true, message: "请输入手机号" },
            {
              validator(_, value) {
                if (!value || isValidMainlandPhone(value)) return Promise.resolve();
                return Promise.reject(new Error("请输入 11 位有效手机号"));
              },
            },
          ]}
        >
          <Input />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={profileMutation.isPending}>
            保存资料
          </Button>
        </Form.Item>
      </Form>

      <Divider orientation="left">修改密码</Divider>
      <Form<PasswordValues> form={passwordForm} layout="vertical" onFinish={(v) => passwordMutation.mutate(v)} style={{ maxWidth: 560 }}>
        <Form.Item label="原密码" name="old_password" rules={[{ required: true, message: "请输入原密码" }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item label="新密码" name="new_password" rules={[{ required: true, message: "请输入新密码" }]}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          label="确认新密码"
          name="confirm_password"
          dependencies={["new_password"]}
          rules={[
            { required: true, message: "请再次输入新密码" },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue("new_password") === value) return Promise.resolve();
                return Promise.reject(new Error("两次输入的新密码不一致"));
              },
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={passwordMutation.isPending}>
              修改密码
            </Button>
            <Button onClick={() => passwordForm.resetFields()}>清空</Button>
          </Space>
        </Form.Item>
      </Form>
    </Card>
  );
}
```

- [x] **Step 10: Wire layout and routes**

Modify `frontend/src/app/layout/AdminLayout.tsx`:

```tsx
import { Button, Layout, Menu, Space, Typography } from "antd";
import {
  FileTextOutlined,
  FormOutlined,
  HeartOutlined,
  MedicineBoxOutlined,
  ProjectOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { ForcePasswordChangeModal } from "../../auth/ForcePasswordChangeModal";
import { useAuth } from "../../auth/AuthContext";
import { maskPhoneForList } from "../../pages/patients/phoneMask";
```

Inside `AdminLayout`, derive selected key:

```tsx
  const location = useLocation();
  const selectedKey = `/${location.pathname.split("/").filter(Boolean)[0] ?? "patients"}`;
```

Set `selectedKeys={[selectedKey]}` on `Menu`, add the doctor item:

```tsx
{ key: "/doctors", icon: <UserOutlined />, label: "医生管理" },
```

Replace the Header account text with a link-style button:

```tsx
            <Button type="link" onClick={() => navigate("/account")}>
              {me?.name}（{maskPhoneForList(me?.phone ?? "")}）
            </Button>
```

Mount the forced modal after `<Outlet />`:

```tsx
          <Outlet />
          <ForcePasswordChangeModal
            open={me?.must_change_password === true}
            onChanged={() => void refetchSession()}
            onLogout={() => void logout()}
          />
```

This requires destructuring `refetchSession` from `useAuth()`.

Modify `frontend/src/app/App.tsx` imports:

```tsx
import { AccountPage } from "../pages/account/AccountPage";
import { DoctorCreatePage } from "../pages/doctors/DoctorCreatePage";
import { DoctorEditPage } from "../pages/doctors/DoctorEditPage";
import { DoctorListPage } from "../pages/doctors/DoctorListPage";
```

Add routes under `AdminLayout`:

```tsx
              <Route path="/doctors" element={<DoctorListPage />} />
              <Route path="/doctors/new" element={<DoctorCreatePage />} />
              <Route path="/doctors/:doctorId/edit" element={<DoctorEditPage />} />
              <Route path="/account" element={<AccountPage />} />
```

- [x] **Step 11: Update App test mock fields**

In `frontend/src/app/App.test.tsx`, every `/me/` mock user must include:

```ts
gender: "male",
must_change_password: false,
permissions: ["patient.read", "user.manage"],
```

Add a smoke expectation to the existing authenticated app test:

```tsx
expect(await screen.findByText("医生管理")).toBeInTheDocument();
```

- [x] **Step 12: Run focused frontend page tests**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npx vitest run src/pages/doctors/doctorUtils.test.ts src/pages/doctors/DoctorListPage.test.tsx src/pages/doctors/DoctorCreatePage.test.tsx src/pages/doctors/DoctorEditPage.test.tsx src/pages/account/AccountPage.test.tsx src/auth/ForcePasswordChangeModal.test.tsx src/app/App.test.tsx
```

Expected: PASS.

- [x] **Step 13: Commit Task 4**

Run:

```bash
git add frontend/src/auth/AuthContext.tsx frontend/src/auth/ForcePasswordChangeModal.tsx frontend/src/auth/ForcePasswordChangeModal.test.tsx frontend/src/app/layout/AdminLayout.tsx frontend/src/app/App.tsx frontend/src/app/App.test.tsx frontend/src/pages/doctors frontend/src/pages/account
git commit -m "feat(frontend): 新增医生管理和我的账号页面"
```

Expected: commit succeeds.

---

### Task 5: Full Verification And Regression Sweep

**Files:**
- No planned source edits.
- Update only files required by failures found during verification.

- [ ] **Step 1: Run all backend tests**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest
```

Expected: PASS.

- [ ] **Step 2: Run all frontend tests**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run test
```

Expected: PASS.

- [ ] **Step 3: Run frontend lint**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run lint
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run build
```

Expected: PASS.

- [ ] **Step 5: Run migration check**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
python manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`.

- [ ] **Step 6: Manually smoke the local UI**

Start services if they are not already running:

```bash
docker compose up -d postgres redis
cd /Users/nick/my_dev/workout/MotionCare/backend
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

In another terminal:

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run dev
```

Open `http://localhost:5173` and verify:

1. 登录 `13800000000 / pass123456`。
2. 左侧菜单出现“医生管理”。
3. 进入“医生管理”，列表能显示演示医生或新建医生。
4. 新建医生成功提示默认密码。
5. 退出后使用新医生手机号与 `888888` 登录。
6. 登录后出现不可关闭改密弹窗。
7. 修改为非 `888888` 密码后弹窗消失。
8. 右上角账号入口进入“我的账号”，可保存基础资料。

- [ ] **Step 7: Commit verification fixes if needed**

If verification required source changes, commit them:

```bash
git add <changed-files>
git commit -m "fix(accounts): 修正医生管理验证问题"
```

Expected: commit succeeds only when there were verification fixes. If no files changed, skip this step.

## Self-Review Checklist

- Spec coverage:
  - 医生管理菜单、列表、新建、编辑：Task 4。
  - `User.gender`、`must_change_password`、默认密码：Task 1。
  - `/api/me/` 新字段和 doctor `user.manage`：Task 1。
  - 当前账号改密：Task 2 后端，Task 3/4 前端。
  - 强制改密不可跳过与后端硬拦截：Task 2/3。
  - 手机号校验、重复提示、默认密码不可作为新密码：Task 1/2/4。
  - 完整验证命令：Task 5。
- 占位词扫描：已检查常见占位符与未展开步骤；未发现需要补充的执行内容。
- Type consistency:
  - 后端字段使用 `gender`、`must_change_password`、`date_joined`。
  - 前端 `Me`、`Doctor`、表单类型均使用同名字段。
  - 改密接口统一为 `/api/accounts/users/me/change-password/`；前端 axios baseURL 为 `/api`，因此前端调用 `/accounts/users/me/change-password/`。
