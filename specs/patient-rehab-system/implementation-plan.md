# Web Admin MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first-version hospital Web admin system for patient records, research projects, grouping, visits, prescriptions, manual training records, daily health data, and CRF preview/export.

**Architecture:** Use a Django + Django REST Framework backend as the system of record, PostgreSQL for relational and JSONB data, and a React + TypeScript + Ant Design frontend as a separate SPA. Keep future AI motion recognition out of the first backend process; implement it as a separate FastAPI service called by task or HTTP integration when that phase starts.

**Tech Stack:** Python 3.12, Django 5, Django REST Framework, PostgreSQL 16, Redis, Celery, React 18, TypeScript, Vite, Ant Design, Vitest, Playwright, python-docx, LibreOffice for PDF conversion, Docker Compose.

---

## Scope

This plan implements the PRD 0.2 in `specs/patient-rehab-system/prd.md`.

Included:

- Web admin only.
- Django API and React admin UI.
- Global patient list.
- Research projects and project groups.
- Batch random grouping with confirmation lock.
- T0/T1/T2 visit records.
- Versioned prescriptions with action snapshots.
- Manual training record entry against current active prescription.
- Manual daily health data entry.
- CRF preview, missing-field list, DOCX export, PDF export.

Excluded:

- WeChat mini program.
- Real device OpenAPI sync.
- TCP device protocol.
- Real games.
- Video upload.
- AI action recognition.
- Electronic signatures.
- Full clinical audit lock workflow.

## File Structure

Create these top-level files and folders:

```text
docker-compose.yml
.env.example
backend/
  pyproject.toml
  manage.py
  config/
    __init__.py
    settings.py
    urls.py
    celery.py
    wsgi.py
    asgi.py
  apps/
    accounts/
    common/
    patients/
    studies/
    visits/
    prescriptions/
    training/
    health/
    crf/
  tests/
frontend/
  package.json
  index.html
  vite.config.ts
  tsconfig.json
  src/
    main.tsx
    app/
    api/
    pages/
    components/
```

Backend app responsibilities:

- `accounts`: custom user model, roles, authentication.
- `common`: shared model mixins, enums, pagination, permissions.
- `patients`: global patient records.
- `studies`: projects, groups, project-patient relation, grouping batches.
- `visits`: visit plan and T0/T1/T2 visit records.
- `prescriptions`: action library, prescriptions, prescription versions, action snapshots.
- `training`: manual training records based on active prescriptions.
- `health`: manual daily health records.
- `crf`: CRF aggregation, preview, missing-field detection, DOCX/PDF export records.

Frontend page responsibilities:

- `pages/patients`: patient list and patient detail.
- `pages/projects`: project list, project detail, groups, grouping batches, project patient detail.
- `pages/visits`: visit form pages.
- `pages/prescriptions`: prescription editor and prescription history.
- `pages/training`: manual training entry and list.
- `pages/health`: daily health entry and list.
- `pages/crf`: CRF preview and export.

## Implementation Tasks

### Task 1: Repository Scaffolding and Local Runtime

**Files:**

- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `backend/pyproject.toml`
- Create: `backend/manage.py`
- Create: `backend/config/settings.py`
- Create: `backend/config/urls.py`
- Create: `backend/config/celery.py`
- Create: `backend/config/wsgi.py`
- Create: `backend/config/asgi.py`
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`

- [ ] **Step 1: Add Docker Compose services**

Create `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: motioncare
      POSTGRES_USER: motioncare
      POSTGRES_PASSWORD: motioncare
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

volumes:
  postgres_data:
```

- [ ] **Step 2: Add environment example**

Create `.env.example`:

```dotenv
DJANGO_SECRET_KEY=replace-with-local-secret
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://motioncare:motioncare@localhost:5432/motioncare
REDIS_URL=redis://localhost:6379/0
CRF_TEMPLATE_PATH=docs/认知衰弱数字疗法研究_CRF表_修订稿.docx
CRF_EXPORT_DIR=media/crf_exports
```

- [ ] **Step 3: Add backend dependency file**

Create `backend/pyproject.toml`:

```toml
[project]
name = "motioncare-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "Django>=5.0,<6.0",
  "djangorestframework>=3.15,<4.0",
  "django-cors-headers>=4.3,<5.0",
  "dj-database-url>=2.2,<3.0",
  "psycopg[binary]>=3.1,<4.0",
  "celery>=5.4,<6.0",
  "redis>=5.0,<6.0",
  "python-docx>=1.1,<2.0",
  "python-dotenv>=1.0,<2.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0,<9.0",
  "pytest-django>=4.8,<5.0",
  "factory-boy>=3.3,<4.0",
  "ruff>=0.5,<1.0",
]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
python_files = ["test_*.py", "*_test.py"]
testpaths = ["apps", "tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 4: Create Django project shell**

Create `backend/manage.py`:

```python
#!/usr/bin/env python
import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

Create `backend/config/settings.py`:

```python
from pathlib import Path
import os

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(ROOT_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "local-dev-secret")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "apps.accounts",
    "apps.common",
    "apps.patients",
    "apps.studies",
    "apps.visits",
    "apps.prescriptions",
    "apps.training",
    "apps.health",
    "apps.crf",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]},
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL", "postgres://motioncare:motioncare@localhost:5432/motioncare"),
        conn_max_age=600,
    )
}

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "media/"
MEDIA_ROOT = ROOT_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CRF_TEMPLATE_PATH = ROOT_DIR / os.getenv(
    "CRF_TEMPLATE_PATH",
    "docs/认知衰弱数字疗法研究_CRF表_修订稿.docx",
)
CRF_EXPORT_DIR = ROOT_DIR / os.getenv("CRF_EXPORT_DIR", "media/crf_exports")
```

Create `backend/config/urls.py`:

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/patients/", include("apps.patients.urls")),
    path("api/studies/", include("apps.studies.urls")),
    path("api/visits/", include("apps.visits.urls")),
    path("api/prescriptions/", include("apps.prescriptions.urls")),
    path("api/training/", include("apps.training.urls")),
    path("api/health/", include("apps.health.urls")),
    path("api/crf/", include("apps.crf.urls")),
]
```

Create `backend/config/celery.py`:

```python
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("motioncare")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

Create `backend/config/wsgi.py`:

```python
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()
```

Create `backend/config/asgi.py`:

```python
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()
```

- [ ] **Step 5: Add frontend scaffold**

Create `frontend/package.json`:

```json
{
  "name": "motioncare-admin",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc && vite build",
    "test": "vitest run",
    "lint": "eslint src --ext ts,tsx"
  },
  "dependencies": {
    "@ant-design/icons": "^5.4.0",
    "@tanstack/react-query": "^5.51.0",
    "antd": "^5.19.0",
    "axios": "^1.7.0",
    "dayjs": "^1.11.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.25.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/react": "^16.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.5.0",
    "vite": "^5.3.0",
    "vitest": "^2.0.0"
  }
}
```

Create `frontend/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
```

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"],
  "references": []
}
```

Create `frontend/index.html`:

```html
<div id="root"></div>
<script type="module" src="/src/main.tsx"></script>
```

Create `frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";

function App() {
  return <div>MotionCare 管理后台</div>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 6: Run scaffold checks**

Run:

```bash
docker compose up -d postgres redis
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python manage.py check
cd ../frontend
npm install
npm run build
```

Expected:

- PostgreSQL and Redis containers are healthy.
- `python manage.py check` prints `System check identified no issues`.
- `npm run build` exits with status 0.

- [ ] **Step 7: Commit scaffold**

```bash
git add docker-compose.yml .env.example backend frontend
git commit -m "chore: scaffold web admin stack"
```

### Task 2: Accounts, Roles, and Shared Model Utilities

**Files:**

- Create: `backend/apps/accounts/apps.py`
- Create: `backend/apps/accounts/models.py`
- Create: `backend/apps/accounts/admin.py`
- Create: `backend/apps/accounts/serializers.py`
- Create: `backend/apps/accounts/views.py`
- Create: `backend/apps/accounts/urls.py`
- Create: `backend/apps/common/models.py`
- Create: `backend/apps/common/permissions.py`
- Test: `backend/apps/accounts/tests/test_user_model.py`

- [ ] **Step 1: Add common model mixins**

Create `backend/apps/common/models.py`:

```python
from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserStampedModel(TimeStampedModel):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_updated",
    )

    class Meta:
        abstract = True
```

Create `backend/apps/common/permissions.py`:

```python
from rest_framework.permissions import BasePermission


class IsAdminOrDoctor(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in {"super_admin", "admin", "doctor"}
        )
```

- [ ] **Step 2: Write user model tests**

Create `backend/apps/accounts/tests/test_user_model.py`:

```python
import pytest

from apps.accounts.models import User


@pytest.mark.django_db
def test_user_uses_phone_as_unique_login_identifier():
    user = User.objects.create_user(
        phone="13800000000",
        password="pass123456",
        name="张医生",
        role=User.Role.DOCTOR,
    )

    assert user.username == "13800000000"
    assert user.phone == "13800000000"
    assert user.name == "张医生"
    assert user.role == User.Role.DOCTOR
    assert user.check_password("pass123456")


@pytest.mark.django_db
def test_create_superuser_sets_super_admin_role():
    user = User.objects.create_superuser(
        phone="13900000000",
        password="pass123456",
        name="超级管理员",
    )

    assert user.is_staff
    assert user.is_superuser
    assert user.role == User.Role.SUPER_ADMIN
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
cd backend
. .venv/bin/activate
pytest apps/accounts/tests/test_user_model.py -v
```

Expected:

- FAIL because `apps.accounts.models.User` is not implemented.

- [ ] **Step 4: Implement custom user**

Create `backend/apps/accounts/apps.py`:

```python
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
```

Create `backend/apps/accounts/models.py`:

```python
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class MotionCareUserManager(UserManager):
    def create_user(self, phone: str, password: str | None = None, **extra_fields):
        if not phone:
            raise ValueError("手机号不能为空")
        extra_fields.setdefault("username", phone)
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.SUPER_ADMIN)
        return self.create_user(phone=phone, password=password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "超级管理员"
        ADMIN = "admin", "管理员"
        DOCTOR = "doctor", "医生"

    phone = models.CharField("手机号", max_length=20, unique=True)
    name = models.CharField("姓名", max_length=80)
    role = models.CharField("角色", max_length=32, choices=Role.choices, default=Role.DOCTOR)

    objects = MotionCareUserManager()
    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["name"]

    def save(self, *args, **kwargs):
        if self.phone and not self.username:
            self.username = self.phone
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name}（{self.phone}）"
```

Create `backend/apps/accounts/admin.py`:

```python
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class MotionCareUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("MotionCare", {"fields": ("phone", "name", "role")}),
    )
    list_display = ("phone", "name", "role", "is_active", "is_staff")
    search_fields = ("phone", "name")
```

- [ ] **Step 5: Add basic account API**

Create `backend/apps/accounts/serializers.py`:

```python
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "phone", "name", "role", "is_active"]
        read_only_fields = ["id"]
```

Create `backend/apps/accounts/views.py`:

```python
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import User
from .serializers import UserSerializer


class UserViewSet(ModelViewSet):
    queryset = User.objects.order_by("id")
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrDoctor]
```

Create `backend/apps/accounts/urls.py`:

```python
from rest_framework.routers import DefaultRouter

from .views import UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
urlpatterns = router.urls
```

- [ ] **Step 6: Run tests and migrations**

Run:

```bash
cd backend
. .venv/bin/activate
python manage.py makemigrations accounts
python manage.py migrate
pytest apps/accounts/tests/test_user_model.py -v
```

Expected:

- Migration file is created.
- Tests pass.

- [ ] **Step 7: Commit accounts foundation**

```bash
git add backend/apps/accounts backend/apps/common backend/config/settings.py backend/config/urls.py
git commit -m "feat: add accounts and shared model utilities"
```

### Task 3: Patient, Project, Grouping, and Visit Data Model

**Files:**

- Create: `backend/apps/patients/models.py`
- Create: `backend/apps/studies/models.py`
- Create: `backend/apps/visits/models.py`
- Create: `backend/apps/studies/services/grouping.py`
- Test: `backend/apps/studies/tests/test_grouping.py`
- Test: `backend/apps/visits/tests/test_visit_generation.py`

- [ ] **Step 1: Write grouping tests**

Create `backend/apps/studies/tests/test_grouping.py`:

```python
import pytest

from apps.studies.services.grouping import assign_groups


def test_assign_groups_respects_equal_ratio_for_four_patients():
    groups = [
        {"id": 1, "ratio": 1},
        {"id": 2, "ratio": 1},
    ]
    patient_ids = [101, 102, 103, 104]

    assignments = assign_groups(patient_ids=patient_ids, groups=groups, seed=7)

    counts = {1: 0, 2: 0}
    for group_id in assignments.values():
        counts[group_id] += 1
    assert counts == {1: 2, 2: 2}


def test_assign_groups_handles_two_to_one_ratio_for_six_patients():
    groups = [
        {"id": 1, "ratio": 2},
        {"id": 2, "ratio": 1},
    ]
    patient_ids = [101, 102, 103, 104, 105, 106]

    assignments = assign_groups(patient_ids=patient_ids, groups=groups, seed=9)

    counts = {1: 0, 2: 0}
    for group_id in assignments.values():
        counts[group_id] += 1
    assert counts == {1: 4, 2: 2}
```

- [ ] **Step 2: Run failing grouping tests**

Run:

```bash
cd backend
. .venv/bin/activate
pytest apps/studies/tests/test_grouping.py -v
```

Expected:

- FAIL because `assign_groups` is not implemented.

- [ ] **Step 3: Implement deterministic grouping service**

Create `backend/apps/studies/services/grouping.py`:

```python
import random
from collections.abc import Sequence


def assign_groups(
    *,
    patient_ids: Sequence[int],
    groups: Sequence[dict[str, int]],
    seed: int | None = None,
) -> dict[int, int]:
    if not groups:
        raise ValueError("项目没有分组，不能随机分组")
    if any(group["ratio"] <= 0 for group in groups):
        raise ValueError("分组比例必须大于 0")

    shuffled_patients = list(patient_ids)
    random.Random(seed).shuffle(shuffled_patients)

    total_ratio = sum(group["ratio"] for group in groups)
    total_patients = len(shuffled_patients)
    target_counts: dict[int, int] = {}
    remaining = total_patients

    for index, group in enumerate(groups):
        group_id = group["id"]
        if index == len(groups) - 1:
            count = remaining
        else:
            count = round(total_patients * group["ratio"] / total_ratio)
            count = min(count, remaining)
        target_counts[group_id] = count
        remaining -= count

    assignments: dict[int, int] = {}
    cursor = 0
    for group_id, count in target_counts.items():
        for patient_id in shuffled_patients[cursor : cursor + count]:
            assignments[patient_id] = group_id
        cursor += count
    return assignments
```

- [ ] **Step 4: Implement core models**

Create `backend/apps/patients/models.py`:

```python
from django.db import models

from apps.common.models import UserStampedModel


class Patient(UserStampedModel):
    class Gender(models.TextChoices):
        MALE = "male", "男"
        FEMALE = "female", "女"
        UNKNOWN = "unknown", "未知"

    name = models.CharField("姓名", max_length=80)
    gender = models.CharField("性别", max_length=16, choices=Gender.choices)
    birth_date = models.DateField("出生日期", null=True, blank=True)
    age = models.PositiveIntegerField("年龄", null=True, blank=True)
    phone = models.CharField("手机号", max_length=20, unique=True)
    primary_doctor = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="patients",
    )
    symptom_note = models.TextField("症状或备注", blank=True)
    is_active = models.BooleanField("是否启用", default=True)

    def __str__(self) -> str:
        return f"{self.name}（{self.phone}）"
```

Create `backend/apps/studies/models.py`:

```python
from django.conf import settings
from django.db import models

from apps.common.models import UserStampedModel


class StudyProject(UserStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        ACTIVE = "active", "进行中"
        ARCHIVED = "archived", "已归档"

    name = models.CharField("项目名称", max_length=160)
    description = models.TextField("项目描述", blank=True)
    crf_template_version = models.CharField("CRF模板版本", max_length=40, default="1.1")
    visit_plan = models.JSONField("访视计划", default=list)
    status = models.CharField("项目状态", max_length=20, choices=Status.choices, default=Status.DRAFT)

    def __str__(self) -> str:
        return self.name


class StudyGroup(UserStampedModel):
    project = models.ForeignKey(StudyProject, on_delete=models.CASCADE, related_name="groups")
    name = models.CharField("分组名称", max_length=100)
    description = models.TextField("分组说明", blank=True)
    target_ratio = models.PositiveIntegerField("目标比例", default=1)
    sort_order = models.PositiveIntegerField("排序", default=0)
    is_active = models.BooleanField("是否启用", default=True)

    class Meta:
        unique_together = [("project", "name")]
        ordering = ["project_id", "sort_order", "id"]


class GroupingBatch(UserStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待确认"
        CONFIRMED = "confirmed", "已确认"

    project = models.ForeignKey(StudyProject, on_delete=models.CASCADE, related_name="grouping_batches")
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.PENDING)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_grouping_batches",
    )
    confirmed_at = models.DateTimeField("确认时间", null=True, blank=True)


class ProjectPatient(UserStampedModel):
    class GroupingStatus(models.TextChoices):
        PENDING = "pending", "待确认"
        CONFIRMED = "confirmed", "已确认"

    project = models.ForeignKey(StudyProject, on_delete=models.CASCADE, related_name="project_patients")
    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="project_links")
    group = models.ForeignKey(StudyGroup, null=True, blank=True, on_delete=models.PROTECT)
    grouping_batch = models.ForeignKey(
        GroupingBatch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="project_patients",
    )
    enrolled_at = models.DateTimeField("入组时间", auto_now_add=True)
    grouping_status = models.CharField(
        "分组状态",
        max_length=20,
        choices=GroupingStatus.choices,
        default=GroupingStatus.PENDING,
    )

    class Meta:
        unique_together = [("project", "patient")]
```

Create `backend/apps/visits/models.py`:

```python
from django.db import models

from apps.common.models import UserStampedModel


class VisitRecord(UserStampedModel):
    class VisitType(models.TextChoices):
        T0 = "T0", "T0 筛选/入组"
        T1 = "T1", "T1 干预12周"
        T2 = "T2", "T2 干预后36周随访"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        COMPLETED = "completed", "已完成"

    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="visits",
    )
    visit_type = models.CharField("访视类型", max_length=8, choices=VisitType.choices)
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.DRAFT)
    visit_date = models.DateField("访视日期", null=True, blank=True)
    form_data = models.JSONField("访视表单数据", default=dict)

    class Meta:
        unique_together = [("project_patient", "visit_type")]
```

- [ ] **Step 5: Add visit generation test and service**

Create `backend/apps/visits/tests/test_visit_generation.py`:

```python
import pytest

from apps.visits.models import VisitRecord
from apps.visits.services import ensure_default_visits


@pytest.mark.django_db
def test_ensure_default_visits_creates_t0_t1_t2(project_patient):
    ensure_default_visits(project_patient)

    assert list(
        VisitRecord.objects.filter(project_patient=project_patient)
        .order_by("visit_type")
        .values_list("visit_type", flat=True)
    ) == ["T0", "T1", "T2"]
```

Create `backend/apps/visits/services.py`:

```python
from apps.visits.models import VisitRecord


DEFAULT_VISIT_TYPES = ["T0", "T1", "T2"]


def ensure_default_visits(project_patient) -> None:
    for visit_type in DEFAULT_VISIT_TYPES:
        VisitRecord.objects.get_or_create(
            project_patient=project_patient,
            visit_type=visit_type,
            defaults={"form_data": {}},
        )
```

Also create test factories in `backend/apps/studies/tests/conftest.py`:

```python
import pytest

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject


@pytest.fixture
def doctor(db):
    return User.objects.create_user(
        phone="13800001111",
        password="pass123456",
        name="测试医生",
        role=User.Role.DOCTOR,
    )


@pytest.fixture
def patient(db, doctor):
    return Patient.objects.create(
        name="患者甲",
        gender=Patient.Gender.MALE,
        age=70,
        phone="13900001111",
        primary_doctor=doctor,
    )


@pytest.fixture
def project(db, doctor):
    return StudyProject.objects.create(name="认知衰弱研究", created_by=doctor)


@pytest.fixture
def group(db, project):
    return StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)


@pytest.fixture
def project_patient(db, project, patient, group):
    return ProjectPatient.objects.create(project=project, patient=patient, group=group)
```

- [ ] **Step 6: Run model tests**

Run:

```bash
cd backend
. .venv/bin/activate
python manage.py makemigrations patients studies visits
python manage.py migrate
pytest apps/studies/tests/test_grouping.py apps/visits/tests/test_visit_generation.py -v
```

Expected:

- Grouping tests pass.
- Visit generation test passes.

- [ ] **Step 7: Commit patient/project/visit models**

```bash
git add backend/apps/patients backend/apps/studies backend/apps/visits
git commit -m "feat: add patient project grouping and visit models"
```

### Task 4: Prescription, Action Snapshot, Training, and Health Models

**Files:**

- Create: `backend/apps/prescriptions/models.py`
- Create: `backend/apps/prescriptions/services.py`
- Create: `backend/apps/training/models.py`
- Create: `backend/apps/health/models.py`
- Test: `backend/apps/prescriptions/tests/test_prescription_versioning.py`
- Test: `backend/apps/training/tests/test_training_current_prescription.py`
- Test: `backend/apps/health/tests/test_daily_health_unique.py`

- [ ] **Step 1: Write prescription versioning test**

Create `backend/apps/prescriptions/tests/test_prescription_versioning.py`:

```python
import pytest
from django.utils import timezone

from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.prescriptions.services import activate_prescription


@pytest.mark.django_db
def test_activating_new_prescription_archives_existing_active(project_patient, doctor):
    first = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    second = Prescription.objects.create(
        project_patient=project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.DRAFT,
    )

    activate_prescription(second)

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == Prescription.Status.ARCHIVED
    assert second.status == Prescription.Status.ACTIVE


@pytest.mark.django_db
def test_prescription_action_keeps_snapshot(project_patient, doctor):
    action = ActionLibraryItem.objects.create(
        name="坐立训练",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="平衡训练",
        execution_description="从椅子坐下后站起",
        key_points="保持躯干稳定",
    )

    prescription = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
    )
    snapshot = prescription.add_action_snapshot(action, duration_minutes=10, sets=2)

    action.name = "已修改动作名"
    action.save()

    snapshot.refresh_from_db()
    assert snapshot.action_library_item == action
    assert snapshot.action_name_snapshot == "坐立训练"
```

- [ ] **Step 2: Implement prescription models and service**

Create `backend/apps/prescriptions/models.py`:

```python
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import UserStampedModel


class ActionLibraryItem(UserStampedModel):
    class InternalType(models.TextChoices):
        VIDEO = "video", "视频类"
        GAME = "game", "游戏互动类"
        MOTION = "motion", "运动类"

    name = models.CharField("动作名称", max_length=120)
    training_type = models.CharField("训练类型", max_length=80)
    internal_type = models.CharField("内部类型", max_length=20, choices=InternalType.choices)
    action_type = models.CharField("动作类型", max_length=80)
    execution_description = models.TextField("执行描述", blank=True)
    key_points = models.TextField("动作要点", blank=True)
    suggested_frequency = models.CharField("建议频次", max_length=80, blank=True)
    suggested_duration_minutes = models.PositiveIntegerField("建议时长", null=True, blank=True)
    suggested_sets = models.PositiveIntegerField("建议组数", null=True, blank=True)
    default_difficulty = models.CharField("默认难度", max_length=40, blank=True)
    is_active = models.BooleanField("是否启用", default=True)


class Prescription(UserStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        ACTIVE = "active", "生效中"
        PENDING = "pending", "待生效"
        ARCHIVED = "archived", "已归档"
        TERMINATED = "terminated", "已终止"

    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="prescriptions",
    )
    version = models.PositiveIntegerField("版本号")
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="opened_prescriptions",
    )
    opened_at = models.DateTimeField("开设时间", auto_now_add=True)
    effective_at = models.DateTimeField("生效时间", null=True, blank=True)
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.DRAFT)
    note = models.TextField("备注", blank=True)

    class Meta:
        unique_together = [("project_patient", "version")]

    def add_action_snapshot(
        self,
        action: ActionLibraryItem,
        *,
        frequency: str = "",
        duration_minutes: int | None = None,
        sets: int | None = None,
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
            difficulty=difficulty,
            notes=notes,
            sort_order=sort_order,
        )


class PrescriptionAction(UserStampedModel):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="actions")
    action_library_item = models.ForeignKey(ActionLibraryItem, on_delete=models.PROTECT)
    action_name_snapshot = models.CharField("动作名称快照", max_length=120)
    training_type_snapshot = models.CharField("训练类型快照", max_length=80)
    internal_type_snapshot = models.CharField("内部类型快照", max_length=20)
    action_type_snapshot = models.CharField("动作类型快照", max_length=80)
    execution_description_snapshot = models.TextField("执行描述快照", blank=True)
    frequency = models.CharField("频次", max_length=80, blank=True)
    duration_minutes = models.PositiveIntegerField("时长", null=True, blank=True)
    sets = models.PositiveIntegerField("组数", null=True, blank=True)
    difficulty = models.CharField("难度", max_length=40, blank=True)
    notes = models.TextField("注意事项", blank=True)
    sort_order = models.PositiveIntegerField("排序", default=0)
```

Create `backend/apps/prescriptions/services.py`:

```python
from django.db import transaction
from django.utils import timezone

from .models import Prescription


@transaction.atomic
def activate_prescription(prescription: Prescription, effective_at=None) -> Prescription:
    now = timezone.now()
    effective_at = effective_at or now
    Prescription.objects.filter(
        project_patient=prescription.project_patient,
        status=Prescription.Status.ACTIVE,
    ).exclude(id=prescription.id).update(status=Prescription.Status.ARCHIVED)

    prescription.effective_at = effective_at
    prescription.status = (
        Prescription.Status.ACTIVE if effective_at <= now else Prescription.Status.PENDING
    )
    prescription.save(update_fields=["effective_at", "status", "updated_at"])
    return prescription
```

- [ ] **Step 3: Implement training and health models**

Create `backend/apps/training/models.py`:

```python
from django.db import models

from apps.common.models import UserStampedModel


class TrainingRecord(UserStampedModel):
    class Status(models.TextChoices):
        COMPLETED = "completed", "已完成"
        PARTIAL = "partial", "部分完成"
        MISSED = "missed", "未完成"

    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="training_records",
    )
    prescription = models.ForeignKey("prescriptions.Prescription", on_delete=models.PROTECT)
    prescription_action = models.ForeignKey("prescriptions.PrescriptionAction", on_delete=models.PROTECT)
    training_date = models.DateField("训练日期")
    status = models.CharField("完成状态", max_length=20, choices=Status.choices)
    actual_duration_minutes = models.PositiveIntegerField("实际时长", null=True, blank=True)
    score = models.DecimalField("得分", max_digits=6, decimal_places=2, null=True, blank=True)
    form_data = models.JSONField("分类表单数据", default=dict)
    note = models.TextField("备注", blank=True)
```

Create `backend/apps/health/models.py`:

```python
from django.db import models

from apps.common.models import UserStampedModel


class DailyHealthRecord(UserStampedModel):
    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="daily_health")
    record_date = models.DateField("日期")
    steps = models.PositiveIntegerField("步数", null=True, blank=True)
    exercise_minutes = models.PositiveIntegerField("运动时长", null=True, blank=True)
    average_heart_rate = models.PositiveIntegerField("平均心率", null=True, blank=True)
    max_heart_rate = models.PositiveIntegerField("最高心率", null=True, blank=True)
    min_heart_rate = models.PositiveIntegerField("最低心率", null=True, blank=True)
    sleep_hours = models.DecimalField("睡眠时长", max_digits=4, decimal_places=1, null=True, blank=True)
    note = models.TextField("备注", blank=True)

    class Meta:
        unique_together = [("patient", "record_date")]
```

- [ ] **Step 4: Add training and health tests**

Create `backend/apps/training/tests/test_training_current_prescription.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.prescriptions.models import Prescription
from apps.training.services import create_training_record


@pytest.mark.django_db
def test_training_requires_active_prescription(project_patient):
    with pytest.raises(ValidationError, match="当前无生效处方"):
        create_training_record(project_patient=project_patient, training_date="2026-05-06")


@pytest.mark.django_db
def test_training_uses_current_active_prescription(active_prescription, prescription_action):
    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date="2026-05-06",
        prescription_action=prescription_action,
        status="completed",
        actual_duration_minutes=20,
    )

    assert record.prescription == active_prescription
    assert record.prescription_action == prescription_action
    assert record.status == "completed"
```

Create `backend/apps/training/services.py`:

```python
from django.core.exceptions import ValidationError

from apps.prescriptions.models import Prescription

from .models import TrainingRecord


def create_training_record(*, project_patient, training_date, prescription_action=None, **fields):
    active = (
        Prescription.objects.filter(
            project_patient=project_patient,
            status=Prescription.Status.ACTIVE,
        )
        .order_by("-effective_at", "-id")
        .first()
    )
    if not active:
        raise ValidationError("当前无生效处方，不能录入训练")
    if prescription_action is None:
        raise ValidationError("必须选择当前处方动作")
    if prescription_action.prescription_id != active.id:
        raise ValidationError("只能录入当前生效处方下的动作")
    return TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active,
        prescription_action=prescription_action,
        training_date=training_date,
        **fields,
    )
```

Create `backend/apps/health/tests/test_daily_health_unique.py`:

```python
import pytest
from django.db import IntegrityError

from apps.health.models import DailyHealthRecord


@pytest.mark.django_db
def test_daily_health_unique_per_patient_and_date(patient):
    DailyHealthRecord.objects.create(patient=patient, record_date="2026-05-06", steps=1000)

    with pytest.raises(IntegrityError):
        DailyHealthRecord.objects.create(patient=patient, record_date="2026-05-06", steps=2000)
```

- [ ] **Step 5: Run model tests**

Run:

```bash
cd backend
. .venv/bin/activate
python manage.py makemigrations prescriptions training health
python manage.py migrate
pytest apps/prescriptions/tests/test_prescription_versioning.py apps/training/tests/test_training_current_prescription.py apps/health/tests/test_daily_health_unique.py -v
```

Expected:

- Prescription versioning tests pass.
- Training current-prescription tests pass.
- Daily health uniqueness test passes.

- [ ] **Step 6: Commit prescription/training/health models**

```bash
git add backend/apps/prescriptions backend/apps/training backend/apps/health
git commit -m "feat: add prescription training and health models"
```

### Task 5: REST API ViewSets

**Files:**

- Create: serializers, views, urls for `patients`, `studies`, `visits`, `prescriptions`, `training`, `health`, `crf`
- Test: `backend/tests/test_api_smoke.py`

- [ ] **Step 1: Add API smoke tests**

Create `backend/tests/test_api_smoke.py`:

```python
import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_patient_list_requires_authentication():
    client = APIClient()
    response = client.get("/api/patients/")
    assert response.status_code in {401, 403}


@pytest.mark.django_db
def test_authenticated_doctor_can_create_patient(doctor):
    client = APIClient()
    client.force_authenticate(user=doctor)

    response = client.post(
        "/api/patients/",
        {
            "name": "患者乙",
            "gender": "female",
            "age": 68,
            "phone": "13900002222",
            "primary_doctor": doctor.id,
            "symptom_note": "记忆力下降",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["name"] == "患者乙"
```

- [ ] **Step 2: Implement patient API first**

Create `backend/apps/patients/serializers.py`:

```python
from rest_framework import serializers

from .models import Patient


class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = [
            "id",
            "name",
            "gender",
            "birth_date",
            "age",
            "phone",
            "primary_doctor",
            "symptom_note",
            "is_active",
        ]
        read_only_fields = ["id"]
```

Create `backend/apps/patients/views.py`:

```python
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import Patient
from .serializers import PatientSerializer


class PatientViewSet(ModelViewSet):
    queryset = Patient.objects.select_related("primary_doctor").order_by("-id")
    serializer_class = PatientSerializer
    permission_classes = [IsAdminOrDoctor]
    search_fields = ["name", "phone"]
```

Create `backend/apps/patients/urls.py`:

```python
from rest_framework.routers import DefaultRouter

from .views import PatientViewSet

router = DefaultRouter()
router.register("", PatientViewSet, basename="patient")
urlpatterns = router.urls
```

- [ ] **Step 3: Implement remaining ViewSets**

For each app, create serializers exposing all first-version fields and register standard DRF `ModelViewSet` routes:

```text
backend/apps/studies/serializers.py
backend/apps/studies/views.py
backend/apps/studies/urls.py
backend/apps/visits/serializers.py
backend/apps/visits/views.py
backend/apps/visits/urls.py
backend/apps/prescriptions/serializers.py
backend/apps/prescriptions/views.py
backend/apps/prescriptions/urls.py
backend/apps/training/serializers.py
backend/apps/training/views.py
backend/apps/training/urls.py
backend/apps/health/serializers.py
backend/apps/health/views.py
backend/apps/health/urls.py
```

Use these endpoint groups:

```text
/api/studies/projects/
/api/studies/groups/
/api/studies/project-patients/
/api/studies/grouping-batches/
/api/visits/
/api/prescriptions/actions/
/api/prescriptions/
/api/prescriptions/prescription-actions/
/api/training/
/api/health/
```

Business actions to implement as DRF custom actions in `studies/views.py`:

- `POST /api/studies/projects/{id}/create_grouping_batch/`
  - Request body: `{"patient_ids": [1, 2, 3]}`
  - Behavior: validate that the project has active groups, create a `GroupingBatch`, create `ProjectPatient` records in pending status, assign draft groups with `assign_groups`, and call `ensure_default_visits` for each project patient.
  - Response body: `{"batch_id": 1, "status": "pending", "assignments": [{"project_patient_id": 1, "group_id": 1}]}`
- `POST /api/studies/grouping-batches/{id}/confirm/`
  - Request body: `{"assignments": [{"project_patient_id": 1, "group_id": 2}]}`
  - Behavior: validate that the batch is pending, apply the submitted group choices, mark all batch project patients as confirmed, set the batch status to confirmed, and reject edits to confirmed project-patient group values.
  - Response body: `{"batch_id": 1, "status": "confirmed"}`

Business actions to implement as DRF custom actions in `prescriptions/views.py`:

- `POST /api/prescriptions/{id}/activate/`
  - Request body: `{"effective_at": "2026-05-06T09:00:00+08:00"}`
  - Behavior: call `activate_prescription`, archive the previous active prescription for the same project patient, and return the updated prescription.
- `POST /api/prescriptions/{id}/terminate/`
  - Request body: `{}`
  - Behavior: allow termination only for active prescriptions, set status to `terminated`, and keep all history records readable.

- [ ] **Step 4: Run API tests**

Run:

```bash
cd backend
. .venv/bin/activate
pytest backend/tests/test_api_smoke.py apps/studies/tests apps/prescriptions/tests apps/training/tests apps/health/tests -v
```

Expected:

- Authentication smoke test passes.
- Patient create smoke test passes.
- Existing domain tests still pass.

- [ ] **Step 5: Commit APIs**

```bash
git add backend/apps backend/tests backend/config/urls.py
git commit -m "feat: expose core web admin APIs"
```

### Task 6: CRF Aggregation and Export

**Files:**

- Create: `backend/apps/crf/models.py`
- Create: `backend/apps/crf/services/aggregate.py`
- Create: `backend/apps/crf/services/export_docx.py`
- Create: `backend/apps/crf/views.py`
- Create: `backend/apps/crf/serializers.py`
- Create: `backend/apps/crf/urls.py`
- Test: `backend/apps/crf/tests/test_crf_aggregate.py`
- Test: `backend/apps/crf/tests/test_crf_export.py`

- [ ] **Step 1: Write CRF aggregation tests**

Create `backend/apps/crf/tests/test_crf_aggregate.py`:

```python
import pytest

from apps.crf.services.aggregate import build_crf_preview


@pytest.mark.django_db
def test_crf_preview_reports_missing_visit_fields(project_patient):
    preview = build_crf_preview(project_patient)

    assert preview["project_patient_id"] == project_patient.id
    assert "T0.访视日期" in preview["missing_fields"]
    assert "T1.访视日期" in preview["missing_fields"]
    assert "T2.访视日期" in preview["missing_fields"]
```

- [ ] **Step 2: Implement CRF export record and aggregation**

Create `backend/apps/crf/models.py`:

```python
from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class CrfExport(TimeStampedModel):
    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="crf_exports",
    )
    exported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    template_version = models.CharField(max_length=40)
    missing_fields = models.JSONField(default=list)
    docx_file = models.FileField(upload_to="crf_exports/", null=True, blank=True)
    pdf_file = models.FileField(upload_to="crf_exports/", null=True, blank=True)
```

Create `backend/apps/crf/services/aggregate.py`:

```python
from apps.visits.models import VisitRecord


REQUIRED_VISIT_FIELDS = {
    "T0": ["visit_date"],
    "T1": ["visit_date"],
    "T2": ["visit_date"],
}


def build_crf_preview(project_patient) -> dict:
    visits = {
        visit.visit_type: visit
        for visit in VisitRecord.objects.filter(project_patient=project_patient)
    }
    missing_fields: list[str] = []
    visit_payload: dict[str, dict] = {}

    for visit_type, fields in REQUIRED_VISIT_FIELDS.items():
        visit = visits.get(visit_type)
        if not visit:
            missing_fields.append(f"{visit_type}.访视记录")
            visit_payload[visit_type] = {}
            continue
        visit_payload[visit_type] = {
            "visit_date": visit.visit_date.isoformat() if visit.visit_date else "",
            "status": visit.status,
            "form_data": visit.form_data,
        }
        for field in fields:
            if not getattr(visit, field):
                missing_fields.append(f"{visit_type}.访视日期")

    patient = project_patient.patient
    return {
        "project_patient_id": project_patient.id,
        "patient": {
            "name": patient.name,
            "gender": patient.gender,
            "age": patient.age,
            "phone": patient.phone,
        },
        "project": {
            "name": project_patient.project.name,
            "crf_template_version": project_patient.project.crf_template_version,
        },
        "group": {
            "name": project_patient.group.name if project_patient.group else "",
        },
        "visits": visit_payload,
        "missing_fields": missing_fields,
    }
```

- [ ] **Step 3: Implement simple DOCX export**

Create `backend/apps/crf/services/export_docx.py`:

```python
from pathlib import Path

from django.conf import settings
from docx import Document


def export_preview_to_docx(preview: dict, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = Document(settings.CRF_TEMPLATE_PATH)
    document.add_page_break()
    document.add_heading("系统生成数据摘要", level=1)
    document.add_paragraph(f"患者姓名：{preview['patient']['name']}")
    document.add_paragraph(f"项目名称：{preview['project']['name']}")
    document.add_paragraph(f"分组：{preview['group']['name']}")
    if preview["missing_fields"]:
        document.add_heading("缺失字段", level=2)
        for field in preview["missing_fields"]:
            document.add_paragraph(field, style="List Bullet")
    document.save(output_path)
    return output_path
```

This export appends a system data summary to the provided CRF template. Full field-level mapping belongs in `specs/patient-rehab-system/crf-field-map.md` before production CRF use.

- [ ] **Step 4: Add CRF API**

Create `backend/apps/crf/serializers.py`:

```python
from rest_framework import serializers

from .models import CrfExport


class CrfExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = CrfExport
        fields = [
            "id",
            "project_patient",
            "exported_by",
            "template_version",
            "missing_fields",
            "docx_file",
            "pdf_file",
            "created_at",
        ]
        read_only_fields = fields
```

Create `backend/apps/crf/views.py`:

```python
from pathlib import Path

from django.conf import settings
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.studies.models import ProjectPatient

from .models import CrfExport
from .serializers import CrfExportSerializer
from .services.aggregate import build_crf_preview
from .services.export_docx import export_preview_to_docx


class CrfViewSet(ViewSet):
    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request, pk=None):
        project_patient = ProjectPatient.objects.select_related("patient", "project", "group").get(pk=pk)
        return Response(build_crf_preview(project_patient))

    @action(detail=True, methods=["post"], url_path="export")
    def export(self, request, pk=None):
        project_patient = ProjectPatient.objects.select_related("patient", "project", "group").get(pk=pk)
        preview = build_crf_preview(project_patient)
        export = CrfExport.objects.create(
            project_patient=project_patient,
            exported_by=request.user,
            template_version=project_patient.project.crf_template_version,
            missing_fields=preview["missing_fields"],
        )
        output = Path(settings.CRF_EXPORT_DIR) / f"crf-{project_patient.id}-{export.id}.docx"
        export_preview_to_docx(preview, output)
        export.docx_file.name = str(output.relative_to(settings.ROOT_DIR / "media"))
        export.save(update_fields=["docx_file"])
        return Response(CrfExportSerializer(export).data)
```

Create `backend/apps/crf/urls.py`:

```python
from rest_framework.routers import DefaultRouter

from .views import CrfViewSet

router = DefaultRouter()
router.register("project-patients", CrfViewSet, basename="crf-project-patient")
urlpatterns = router.urls
```

- [ ] **Step 5: Run CRF tests**

Run:

```bash
cd backend
. .venv/bin/activate
python manage.py makemigrations crf
python manage.py migrate
pytest apps/crf/tests/test_crf_aggregate.py -v
```

Expected:

- CRF preview reports missing fields.

- [ ] **Step 6: Commit CRF preview/export foundation**

```bash
git add backend/apps/crf backend/config/settings.py
git commit -m "feat: add crf preview and docx export foundation"
```

### Task 7: React App Shell, Routing, and API Client

**Files:**

- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/layout/AdminLayout.tsx`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: Add app shell test**

Create `frontend/src/app/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("renders the admin navigation", () => {
    render(<App />);
    expect(screen.getByText("患者档案")).toBeInTheDocument();
    expect(screen.getByText("研究项目")).toBeInTheDocument();
    expect(screen.getByText("CRF 报告")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement API client**

Create `frontend/src/api/client.ts`:

```ts
import axios from "axios";

export const apiClient = axios.create({
  baseURL: "/api",
  withCredentials: true,
});
```

- [ ] **Step 3: Implement layout and routes**

Create `frontend/src/app/layout/AdminLayout.tsx`:

```tsx
import { Layout, Menu } from "antd";
import {
  FileTextOutlined,
  HeartOutlined,
  ProjectOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Outlet, useNavigate } from "react-router-dom";

const { Header, Sider, Content } = Layout;

export function AdminLayout() {
  const navigate = useNavigate();
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider width={220}>
        <div style={{ color: "#fff", padding: 16, fontWeight: 600 }}>MotionCare</div>
        <Menu
          theme="dark"
          mode="inline"
          onClick={(item) => navigate(item.key)}
          items={[
            { key: "/patients", icon: <TeamOutlined />, label: "患者档案" },
            { key: "/projects", icon: <ProjectOutlined />, label: "研究项目" },
            { key: "/training", icon: <HeartOutlined />, label: "训练记录" },
            { key: "/crf", icon: <FileTextOutlined />, label: "CRF 报告" },
          ]}
        />
      </Sider>
      <Layout>
        <Header style={{ background: "#fff", paddingInline: 24 }}>医院康复研究后台</Header>
        <Content style={{ padding: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
```

Create `frontend/src/app/App.tsx`:

```tsx
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AdminLayout } from "./layout/AdminLayout";

function Placeholder({ title }: { title: string }) {
  return <h1>{title}</h1>;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AdminLayout />}>
          <Route path="/patients" element={<Placeholder title="患者档案" />} />
          <Route path="/projects" element={<Placeholder title="研究项目" />} />
          <Route path="/training" element={<Placeholder title="训练记录" />} />
          <Route path="/crf" element={<Placeholder title="CRF 报告" />} />
          <Route path="*" element={<Navigate to="/patients" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

Modify `frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { App } from "./app/App";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ConfigProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 4: Run frontend tests**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected:

- App shell test passes.
- Build succeeds.

- [ ] **Step 5: Commit frontend shell**

```bash
git add frontend/src frontend/package.json frontend/vite.config.ts frontend/tsconfig.json
git commit -m "feat: add react admin shell"
```

### Task 8: Frontend Patient and Project Workflows

**Files:**

- Create: `frontend/src/pages/patients/PatientListPage.tsx`
- Create: `frontend/src/pages/patients/PatientDetailPage.tsx`
- Create: `frontend/src/pages/projects/ProjectListPage.tsx`
- Create: `frontend/src/pages/projects/ProjectDetailPage.tsx`
- Create: `frontend/src/pages/projects/GroupingBatchPanel.tsx`
- Modify: `frontend/src/app/App.tsx`

- [ ] **Step 1: Implement patient list page**

Create `frontend/src/pages/patients/PatientListPage.tsx`:

```tsx
import { Button, Card, Space, Table } from "antd";

export function PatientListPage() {
  return (
    <Card
      title="患者档案"
      extra={<Button type="primary">新建患者</Button>}
    >
      <Table
        rowKey="id"
        dataSource={[]}
        columns={[
          { title: "姓名", dataIndex: "name" },
          { title: "性别", dataIndex: "gender" },
          { title: "年龄", dataIndex: "age" },
          { title: "手机号", dataIndex: "phone" },
          {
            title: "操作",
            render: () => (
              <Space>
                <Button type="link">详情</Button>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
```

- [ ] **Step 2: Implement project list and detail shell**

Create `frontend/src/pages/projects/ProjectListPage.tsx`:

```tsx
import { Button, Card, Table } from "antd";

export function ProjectListPage() {
  return (
    <Card title="研究项目" extra={<Button type="primary">新建项目</Button>}>
      <Table
        rowKey="id"
        dataSource={[]}
        columns={[
          { title: "项目名称", dataIndex: "name" },
          { title: "CRF 模板", dataIndex: "crfTemplateVersion" },
          { title: "状态", dataIndex: "status" },
          { title: "患者数", dataIndex: "patientCount" },
        ]}
      />
    </Card>
  );
}
```

Create `frontend/src/pages/projects/ProjectDetailPage.tsx`:

```tsx
import { Card, Tabs } from "antd";
import { GroupingBatchPanel } from "./GroupingBatchPanel";

export function ProjectDetailPage() {
  return (
    <Card title="项目详情">
      <Tabs
        items={[
          { key: "groups", label: "项目分组", children: <div>分组配置</div> },
          { key: "patients", label: "项目患者", children: <div>患者列表</div> },
          { key: "grouping", label: "随机分组", children: <GroupingBatchPanel /> },
          { key: "crf", label: "CRF 报告", children: <div>CRF 报告</div> },
        ]}
      />
    </Card>
  );
}
```

Create `frontend/src/pages/projects/GroupingBatchPanel.tsx`:

```tsx
import { Alert, Button, Card, Space, Table } from "antd";

export function GroupingBatchPanel() {
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Alert
        type="info"
        message="从全局患者列表选择患者加入项目后，系统会按项目分组比例生成随机分组草案。确认前可调整，确认后不可修改。"
      />
      <Card title="待确认分组草案" extra={<Button type="primary">确认分组</Button>}>
        <Table
          rowKey="id"
          dataSource={[]}
          columns={[
            { title: "患者", dataIndex: "patientName" },
            { title: "当前分组", dataIndex: "groupName" },
            { title: "操作", render: () => <Button type="link">调整</Button> },
          ]}
        />
      </Card>
    </Space>
  );
}
```

- [ ] **Step 3: Wire routes**

Modify `frontend/src/app/App.tsx` to use the page components:

```tsx
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AdminLayout } from "./layout/AdminLayout";
import { PatientListPage } from "../pages/patients/PatientListPage";
import { ProjectListPage } from "../pages/projects/ProjectListPage";
import { ProjectDetailPage } from "../pages/projects/ProjectDetailPage";

function Placeholder({ title }: { title: string }) {
  return <h1>{title}</h1>;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AdminLayout />}>
          <Route path="/patients" element={<PatientListPage />} />
          <Route path="/projects" element={<ProjectListPage />} />
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/training" element={<Placeholder title="训练记录" />} />
          <Route path="/crf" element={<Placeholder title="CRF 报告" />} />
          <Route path="*" element={<Navigate to="/patients" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected:

- Tests pass.
- Build succeeds.

- [ ] **Step 5: Commit patient/project workflows**

```bash
git add frontend/src
git commit -m "feat: add patient and project admin workflows"
```

### Task 9: Frontend Visit, Prescription, Training, Health, and CRF Screens

**Files:**

- Create: `frontend/src/pages/visits/VisitFormPage.tsx`
- Create: `frontend/src/pages/prescriptions/PrescriptionPanel.tsx`
- Create: `frontend/src/pages/training/TrainingEntryPage.tsx`
- Create: `frontend/src/pages/health/DailyHealthPage.tsx`
- Create: `frontend/src/pages/crf/CrfPreviewPage.tsx`
- Modify: `frontend/src/app/App.tsx`

- [ ] **Step 1: Add visit form shell**

Create `frontend/src/pages/visits/VisitFormPage.tsx`:

```tsx
import { Button, Card, Form, Input, Radio, Space } from "antd";

export function VisitFormPage() {
  return (
    <Card title="访视表单">
      <Form layout="vertical">
        <Form.Item label="访视状态" name="status">
          <Radio.Group>
            <Radio value="draft">草稿</Radio>
            <Radio value="completed">已完成</Radio>
          </Radio.Group>
        </Form.Item>
        <Form.Item label="访视日期" name="visitDate">
          <Input placeholder="YYYY-MM-DD" />
        </Form.Item>
        <Form.Item label="表单数据" name="formData">
          <Input.TextArea rows={8} placeholder="第一版按 CRF 章节拆分具体字段" />
        </Form.Item>
        <Space>
          <Button type="primary">保存</Button>
          <Button>返回</Button>
        </Space>
      </Form>
    </Card>
  );
}
```

- [ ] **Step 2: Add prescription panel**

Create `frontend/src/pages/prescriptions/PrescriptionPanel.tsx`:

```tsx
import { Alert, Button, Card, Table } from "antd";

export function PrescriptionPanel() {
  return (
    <Card title="处方管理" extra={<Button type="primary">新建处方版本</Button>}>
      <Alert
        type="info"
        showIcon
        message="处方属于项目患者。调整处方会生成新版本；旧版本归档；训练录入只使用当前生效处方。"
        style={{ marginBottom: 16 }}
      />
      <Table
        rowKey="id"
        dataSource={[]}
        columns={[
          { title: "版本", dataIndex: "version" },
          { title: "状态", dataIndex: "status" },
          { title: "开设医生", dataIndex: "openedBy" },
          { title: "生效时间", dataIndex: "effectiveAt" },
        ]}
      />
    </Card>
  );
}
```

- [ ] **Step 3: Add training and health pages**

Create `frontend/src/pages/training/TrainingEntryPage.tsx`:

```tsx
import { Alert, Button, Card, Form, Input, Select } from "antd";

export function TrainingEntryPage() {
  return (
    <Card title="后台代患者录入训练">
      <Alert
        type="warning"
        showIcon
        message="第一版只能基于当前生效处方录入训练，不支持旧处方历史补录。"
        style={{ marginBottom: 16 }}
      />
      <Form layout="vertical">
        <Form.Item label="当前处方动作" name="prescriptionAction">
          <Select options={[]} placeholder="请选择当前处方动作" />
        </Form.Item>
        <Form.Item label="训练日期" name="trainingDate">
          <Input placeholder="YYYY-MM-DD" />
        </Form.Item>
        <Form.Item label="完成状态" name="status">
          <Select
            options={[
              { label: "已完成", value: "completed" },
              { label: "部分完成", value: "partial" },
              { label: "未完成", value: "missed" },
            ]}
          />
        </Form.Item>
        <Button type="primary">保存训练记录</Button>
      </Form>
    </Card>
  );
}
```

Create `frontend/src/pages/health/DailyHealthPage.tsx`:

```tsx
import { Button, Card, Form, InputNumber } from "antd";

export function DailyHealthPage() {
  return (
    <Card title="每日健康数据">
      <Form layout="vertical">
        <Form.Item label="步数" name="steps">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="运动时长（分钟）" name="exerciseMinutes">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="平均心率" name="averageHeartRate">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="最高心率" name="maxHeartRate">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="最低心率" name="minHeartRate">
          <InputNumber min={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item label="睡眠时长（小时）" name="sleepHours">
          <InputNumber min={0} step={0.5} style={{ width: "100%" }} />
        </Form.Item>
        <Button type="primary">保存健康数据</Button>
      </Form>
    </Card>
  );
}
```

- [ ] **Step 4: Add CRF preview page**

Create `frontend/src/pages/crf/CrfPreviewPage.tsx`:

```tsx
import { Alert, Button, Card, List, Space } from "antd";

export function CrfPreviewPage() {
  const missingFields: string[] = [];
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card title="CRF 预览">
        <Alert
          type="info"
          showIcon
          message="第一版允许带缺失字段导出。缺失字段在预览中提示，导出文件中留空。"
        />
      </Card>
      <Card title="缺失字段">
        <List
          dataSource={missingFields}
          locale={{ emptyText: "暂无缺失字段" }}
          renderItem={(item) => <List.Item>{item}</List.Item>}
        />
      </Card>
      <Space>
        <Button type="primary">导出 DOCX</Button>
        <Button>导出 PDF</Button>
      </Space>
    </Space>
  );
}
```

- [ ] **Step 5: Wire routes**

Modify `frontend/src/app/App.tsx` to add these routes:

```tsx
<Route path="/visits/:visitId" element={<VisitFormPage />} />
<Route path="/training" element={<TrainingEntryPage />} />
<Route path="/health" element={<DailyHealthPage />} />
<Route path="/crf" element={<CrfPreviewPage />} />
```

- [ ] **Step 6: Run frontend checks**

Run:

```bash
cd frontend
npm test
npm run build
```

Expected:

- Tests pass.
- Build succeeds.

- [ ] **Step 7: Commit remaining frontend screens**

```bash
git add frontend/src
git commit -m "feat: add visit prescription training health and crf screens"
```

### Task 10: Seed Data, End-to-End Smoke, and Documentation

**Files:**

- Create: `backend/apps/common/management/commands/seed_demo.py`
- Create: `docs/development.md`
- Create: `specs/patient-rehab-system/changelog.md`
- Modify: `specs/patient-rehab-system/README.md`

- [ ] **Step 1: Add demo seed command**

Create `backend/apps/common/management/commands/seed_demo.py`:

```python
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.prescriptions.services import activate_prescription
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.visits.services import ensure_default_visits


class Command(BaseCommand):
    help = "Create demo data for local development"

    def handle(self, *args, **options):
        doctor, _ = User.objects.get_or_create(
            phone="13800000000",
            defaults={"name": "演示医生", "role": User.Role.DOCTOR, "username": "13800000000"},
        )
        doctor.set_password("pass123456")
        doctor.save()

        patient, _ = Patient.objects.get_or_create(
            phone="13900000000",
            defaults={"name": "演示患者", "gender": Patient.Gender.MALE, "age": 72},
        )
        project, _ = StudyProject.objects.get_or_create(
            name="认知衰弱数字疗法研究",
            defaults={"created_by": doctor, "status": StudyProject.Status.ACTIVE},
        )
        group, _ = StudyGroup.objects.get_or_create(project=project, name="干预组")
        project_patient, _ = ProjectPatient.objects.get_or_create(
            project=project,
            patient=patient,
            defaults={"group": group, "grouping_status": ProjectPatient.GroupingStatus.CONFIRMED},
        )
        ensure_default_visits(project_patient)

        action, _ = ActionLibraryItem.objects.get_or_create(
            name="坐立训练",
            defaults={
                "training_type": "运动训练",
                "internal_type": ActionLibraryItem.InternalType.MOTION,
                "action_type": "平衡训练",
            },
        )
        prescription, _ = Prescription.objects.get_or_create(
            project_patient=project_patient,
            version=1,
            defaults={"opened_by": doctor, "effective_at": timezone.now()},
        )
        if not prescription.actions.exists():
            prescription.add_action_snapshot(action, duration_minutes=10, sets=2)
        activate_prescription(prescription)

        self.stdout.write(self.style.SUCCESS("Demo data created. Doctor: 13800000000 / pass123456"))
```

- [ ] **Step 2: Add development docs**

Create `docs/development.md`:

```markdown
# MotionCare Development

## Stack

- Backend: Django + Django REST Framework
- Database: PostgreSQL
- Task broker: Redis + Celery
- Frontend: React + TypeScript + Ant Design

## Local Startup

```bash
docker compose up -d postgres redis
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Demo Login

- Phone: `13800000000`
- Password: `pass123456`
```

Create `specs/patient-rehab-system/changelog.md`:

```markdown
# 病人康复系统 Spec Changelog

## 0.2 - 2026-05-06

- 明确第一版为医院 Web 后台研究数据闭环版。
- 明确小程序、真实设备、真实游戏、视频上传、AI 动作识别后置。
- 明确患者是全局基础档案。
- 明确项目、分组、患者解耦。
- 明确随机分组确认前可调整，确认后锁定。
- 明确处方版本化、动作快照、当前生效处方训练录入规则。
- 明确健康日数据手动录入。
- 明确 CRF 可带缺失导出。
```

Update `specs/patient-rehab-system/README.md` current documents table:

```markdown
| `implementation-plan.md` | 草稿 0.1 | Web 后台 MVP 实施计划 |
| `changelog.md` | 草稿 0.1 | spec 版本变更记录 |
```

- [ ] **Step 3: Run full checks**

Run:

```bash
docker compose up -d postgres redis
cd backend
. .venv/bin/activate
python manage.py check
python manage.py migrate
pytest -v
cd ../frontend
npm test
npm run build
```

Expected:

- Django check passes.
- Migrations apply.
- Backend tests pass.
- Frontend tests pass.
- Frontend build succeeds.

- [ ] **Step 4: Commit seed and docs**

```bash
git add backend/apps/common/management docs/development.md specs/patient-rehab-system
git commit -m "docs: add mvp implementation and development guide"
```

## Self-Review Checklist

- PRD accounts and roles are covered by Task 2 and Task 5.
- Global patients are covered by Task 3, Task 5, and Task 8.
- Projects, groups, grouping batches, and confirmation locking are covered by Task 3, Task 5, and Task 8.
- Visit records are covered by Task 3, Task 5, and Task 9.
- Prescriptions, versions, and action snapshots are covered by Task 4, Task 5, and Task 9.
- Manual training records are covered by Task 4, Task 5, and Task 9.
- Manual daily health data is covered by Task 4, Task 5, and Task 9.
- CRF preview and DOCX export foundation are covered by Task 6 and Task 9.
- Local startup and demo data are covered by Task 10.

## Execution Options

Plan complete when this document is committed.

Execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh worker per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session with checkpoints.
