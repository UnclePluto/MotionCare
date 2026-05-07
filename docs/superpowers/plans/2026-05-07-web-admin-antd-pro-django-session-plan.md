# Web 管理端（Ant Design Pro + Django Session）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地第一版 Web 管理端的“可运行骨架”：Ant Design Pro 前端 + Django API（Session+CSRF+RBAC 骨架）+ 反向代理同站点 `/api`，并提供最小可用的认证与一个样例资源接口用于端到端验证。

**Architecture:** 前端静态站点使用 Ant Design Pro；后端用 Django + DRF 提供 REST API。通过 Nginx/网关将 `https://admin.<domain>/api/*` 反向代理至 Django，保证浏览器同站点 Cookie/CSRF 流程顺滑。静态资源 `assets` 域名先按公开 URL 直链处理（后续再做签名/权限）。

**Tech Stack:** Ant Design Pro（React）、TypeScript、Vite（或 Umi/Pro 默认构建链）、Django、Django REST Framework、pytest、Nginx（或同类反向代理）。

---

## Scope Check（拆分建议）

该架构涉及多个子系统：前端工程、后端工程、反代/部署、静态资源域名策略。为了降低并行开发冲突，建议实际实现时拆成两个执行批次：

- **批次 1（本计划覆盖）**：前端/后端“可运行骨架” + Session/CSRF/RBAC 最小闭环 + `/api/me` + 一个示例资源 CRUD（患者或项目），以及反代同站点 `/api` 的开发环境验证。
- **批次 2（后续计划）**：按 `specs/patient-rehab-system/prd.md` 扩展全量业务域（分组批次、访视、处方、训练、健康日、CRF 导出）。

本计划严格覆盖 `specs/patient-rehab-system/architecture/2026-05-07-web-admin-architecture-antd-pro-design.md` 中的架构边界、鉴权与 API 风格，但只实现“最小可验证集合”。

---

## File Structure（将要创建/修改的文件）

> 本仓库目前只有 specs/docs，没有代码。以下结构将作为第一版工程落地的目录约定。

### Repository root

- Create: `apps/web-admin/`（Ant Design Pro 前端）
- Create: `apps/api/`（Django 后端）
- Create: `infra/dev/nginx.conf`（开发环境反代示例）
- Create: `infra/dev/docker-compose.yml`（可选：本地一键启动 web/api/nginx）
- Modify: `specs/patient-rehab-system/README.md`（补充工程目录索引）

### Web Admin (frontend)

- Create: `apps/web-admin/package.json`
- Create: `apps/web-admin/src/`（路由、鉴权、API client、页面骨架）
- Create: `apps/web-admin/src/services/api.ts`（封装 fetch/CSRF/错误）
- Create: `apps/web-admin/src/access.ts`（前端可见性权限过滤）
- Create: `apps/web-admin/src/pages/Login/`（登录页）
- Create: `apps/web-admin/src/pages/Dashboard/`（最小 Dashboard 占位页）

### API (backend)

- Create: `apps/api/pyproject.toml`（或 `requirements.txt`，本计划用 `pyproject.toml`）
- Create: `apps/api/manage.py`
- Create: `apps/api/api/settings.py`（含 Session/CSRF/CORS 配置）
- Create: `apps/api/api/urls.py`
- Create: `apps/api/auth/`（登录、csrf、me）
- Create: `apps/api/patients/`（示例资源：Patient）
- Create: `apps/api/tests/`（pytest + API tests）

---

## Task 1: 创建工作树与基础目录（安全隔离）

**Files:**
- Create: `docs/superpowers/plans/2026-05-07-web-admin-antd-pro-django-session-plan.md` (this file)

- [ ] **Step 1: 创建独立 worktree 分支用于实现**

Run:

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/web-admin-skeleton
git worktree add .worktrees/feat-web-admin-skeleton feat/web-admin-skeleton
```

Expected:
- `git worktree list` 出现 `.worktrees/feat-web-admin-skeleton`

- [ ] **Step 2: 在 worktree 中创建顶层目录**

Run:

```bash
cd .worktrees/feat-web-admin-skeleton
mkdir -p apps infra/dev
```

- [ ] **Step 3: Commit**

Run:

```bash
git add apps infra
git commit -m "chore: add apps and infra folders"
```

---

## Task 2: 后端骨架（Django + DRF + pytest）

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/manage.py`
- Create: `apps/api/api/__init__.py`
- Create: `apps/api/api/settings.py`
- Create: `apps/api/api/urls.py`
- Create: `apps/api/api/wsgi.py`
- Create: `apps/api/api/asgi.py`
- Create: `apps/api/tests/test_health.py`

- [ ] **Step 1: 写一个会失败的健康检查测试（TDD）**

Create `apps/api/tests/test_health.py`:

```python
import pytest


@pytest.mark.django_db
def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: 初始化 Django/DRF 项目依赖**

Create `apps/api/pyproject.toml`:

```toml
[project]
name = "motioncare-api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "Django>=5.0",
  "djangorestframework>=3.15",
  "pytest>=8.0",
  "pytest-django>=4.9",
]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "api.settings"
python_files = ["test_*.py"]
addopts = "-q"
```

Run:

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
django-admin startproject api .
```

Expected:
- 生成 `manage.py`、`api/settings.py` 等

- [ ] **Step 3: 增加 `/api/health` 并跑测试**

Modify `apps/api/api/urls.py` to include:

```python
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", health),
]
```

Run:

```bash
pytest
```

Expected: PASS（`test_health_endpoint`）

- [ ] **Step 4: Commit**

Run:

```bash
git add apps/api
git commit -m "feat(api): add Django/DRF skeleton with health endpoint"
```

---

## Task 3: Session + CSRF 最小闭环（login / csrf / me）

**Files:**
- Create: `apps/api/auth/apps.py`
- Create: `apps/api/auth/urls.py`
- Create: `apps/api/auth/views.py`
- Modify: `apps/api/api/settings.py`
- Modify: `apps/api/api/urls.py`
- Create: `apps/api/tests/test_auth_flow.py`

- [ ] **Step 1: 写失败测试：获取 CSRF、登录、读取 /api/me**

Create `apps/api/tests/test_auth_flow.py`:

```python
import re

import pytest
from django.contrib.auth.models import User


@pytest.mark.django_db
def test_csrf_login_me_flow(client):
    User.objects.create_user(username="doc", password="pass1234")

    csrf = client.get("/api/auth/csrf")
    assert csrf.status_code == 200
    assert "csrftoken" in csrf.cookies
    token = csrf.cookies["csrftoken"].value
    assert re.fullmatch(r"[A-Za-z0-9]+", token) is not None

    resp = client.post(
        "/api/auth/login",
        data={"username": "doc", "password": "pass1234"},
        HTTP_X_CSRFTOKEN=token,
    )
    assert resp.status_code == 204
    assert "sessionid" in resp.cookies

    me = client.get("/api/me")
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == "doc"
    assert body["roles"] == ["doctor"]
    assert "permissions" in body
```

- [ ] **Step 2: 实现 auth app 与 settings**

Modify `apps/api/api/settings.py`:

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "auth",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
```

Create `apps/api/auth/views.py`:

```python
from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST


@ensure_csrf_cookie
@require_GET
def csrf(_request):
    return JsonResponse({"ok": True})


@require_POST
def login_view(request):
    user = authenticate(
        request,
        username=request.POST.get("username", ""),
        password=request.POST.get("password", ""),
    )
    if user is None:
        return JsonResponse({"code": "AUTH_INVALID", "message": "用户名或密码错误"}, status=401)
    login(request, user)
    return JsonResponse({}, status=204)


@require_GET
def me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"code": "AUTH_REQUIRED", "message": "未登录"}, status=401)

    # 第一版最小：基于用户名映射角色；后续替换为 Group/Permission
    roles = ["doctor"]
    permissions = ["patient.read", "patient.write", "project.read", "project.write"]
    return JsonResponse(
        {"username": request.user.username, "roles": roles, "permissions": permissions}
    )
```

Create `apps/api/auth/urls.py`:

```python
from django.urls import path

from .views import csrf, login_view, me

urlpatterns = [
    path("csrf", csrf),
    path("login", login_view),
    path("../me", me),
]
```

> 注：此处为了保持路径清晰，后续实现时建议把 `/api/me` 放在顶层 `api/urls.py`，避免相对路径技巧；本任务目标是先让测试跑通，随后会做一次小重构把 URL 整理清楚并补测试。

- [ ] **Step 3: 修正 URL 组织（避免 ../me），让测试通过**

Modify `apps/api/api/urls.py`:

```python
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from auth.views import me


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", health),
    path("api/auth/", include("auth.urls")),
    path("api/me", me),
]
```

Run:

```bash
pytest -q
```

Expected: PASS（`test_csrf_login_me_flow`）

- [ ] **Step 4: Commit**

Run:

```bash
git add apps/api
git commit -m "feat(api): add session auth, csrf, and /api/me bootstrap"
```

---

## Task 4: 示例业务资源（Patient）+ 权限拦截骨架

**Files:**
- Create: `apps/api/patients/models.py`
- Create: `apps/api/patients/serializers.py`
- Create: `apps/api/patients/views.py`
- Create: `apps/api/patients/urls.py`
- Modify: `apps/api/api/settings.py`
- Modify: `apps/api/api/urls.py`
- Create: `apps/api/tests/test_patients_api.py`

- [ ] **Step 1: 写失败测试：未登录 401，登录后可列出患者**

Create `apps/api/tests/test_patients_api.py`:

```python
import pytest
from django.contrib.auth.models import User


@pytest.mark.django_db
def test_patients_requires_auth(client):
    resp = client.get("/api/patients")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_patients_list_after_login(client):
    User.objects.create_user(username="doc", password="pass1234")
    client.get("/api/auth/csrf")
    token = client.cookies["csrftoken"].value
    client.post(
        "/api/auth/login",
        data={"username": "doc", "password": "pass1234"},
        HTTP_X_CSRFTOKEN=token,
    )

    resp = client.get("/api/patients")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}
```

- [ ] **Step 2: 实现 Patient 最小模型与列表接口**

Create `apps/api/patients/models.py`:

```python
from django.db import models


class Patient(models.Model):
    name = models.CharField(max_length=64)
    phone = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
```

Create `apps/api/patients/views.py`:

```python
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Patient


@require_GET
def list_patients(request):
    if not request.user.is_authenticated:
        return JsonResponse({"code": "AUTH_REQUIRED", "message": "未登录"}, status=401)

    items = [{"id": p.id, "name": p.name, "phone": p.phone} for p in Patient.objects.all()]
    return JsonResponse({"items": items})
```

Create `apps/api/patients/urls.py`:

```python
from django.urls import path

from .views import list_patients

urlpatterns = [
    path("", list_patients),
]
```

Modify `apps/api/api/settings.py` add app:

```python
INSTALLED_APPS += ["patients"]
```

Modify `apps/api/api/urls.py` add route:

```python
from django.urls import include, path

urlpatterns += [
    path("api/patients", include("patients.urls")),
]
```

Run:

```bash
python manage.py makemigrations patients
python manage.py migrate
pytest -q
```

Expected: PASS（两个 patient tests）

- [ ] **Step 3: Commit**

Run:

```bash
git add apps/api
git commit -m "feat(api): add minimal patients list endpoint with auth gate"
```

---

## Task 5: 前端骨架（Ant Design Pro）+ 登录/会话引导

**Files:**
- Create: `apps/web-admin/`（由 AntD Pro 脚手架生成）
- Create/Modify: `apps/web-admin/src/services/api.ts`
- Create/Modify: `apps/web-admin/src/pages/Login/index.tsx`
- Create/Modify: `apps/web-admin/src/access.ts`
- Create/Modify: `apps/web-admin/src/app.tsx`（或 Pro 默认入口文件）

- [ ] **Step 1: 创建 Ant Design Pro 工程**

Run（任选其一，取决于团队偏好；建议优先官方脚手架）:

```bash
cd apps
npx @ant-design/pro-cli create web-admin
```

Expected:
- 生成可运行的 Pro 工程

- [ ] **Step 2: 实现 API client（带 cookie + CSRF）**

Create `apps/web-admin/src/services/api.ts`:

```ts
export type ApiError = { code: string; message: string; details?: unknown };

async function getCsrfToken(): Promise<string> {
  const resp = await fetch("/api/auth/csrf", { credentials: "include" });
  if (!resp.ok) throw new Error("Failed to init csrf");
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return match?.[1] ?? "";
}

export async function apiPost<T>(path: string, body: Record<string, string>): Promise<T> {
  const csrf = await getCsrfToken();
  const form = new URLSearchParams(body);
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": csrf },
    credentials: "include",
    body: form.toString(),
  });
  if (resp.status === 204) return {} as T;
  const data = await resp.json().catch(() => null);
  if (!resp.ok) throw (data ?? { code: "HTTP_ERROR", message: "请求失败" }) as ApiError;
  return data as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  const resp = await fetch(path, { credentials: "include" });
  const data = await resp.json().catch(() => null);
  if (!resp.ok) throw (data ?? { code: "HTTP_ERROR", message: "请求失败" }) as ApiError;
  return data as T;
}
```

- [ ] **Step 3: 登录页调用 `/api/auth/login` 并跳转**

在 Pro 的登录页中，提交用户名/密码后调用：

```ts
await apiPost("/api/auth/login", { username, password });
```

成功后 `apiGet("/api/me")` 获取角色与权限点，缓存到内存（或 local state），并跳转 Dashboard。

- [ ] **Step 4: access.ts 实现权限点过滤**

Create/Modify `apps/web-admin/src/access.ts`:

```ts
export default function access(initialState: { permissions?: string[] }) {
  const perms = new Set(initialState.permissions ?? []);
  return {
    canPatientRead: perms.has("patient.read"),
    canPatientWrite: perms.has("patient.write"),
    canProjectRead: perms.has("project.read"),
    canProjectWrite: perms.has("project.write"),
  };
}
```

- [ ] **Step 5: Commit**

Run:

```bash
git add apps/web-admin
git commit -m "feat(web): scaffold Ant Design Pro with session login and access control"
```

---

## Task 6: 开发环境反代验证（同站点 /api）

**Files:**
- Create: `infra/dev/nginx.conf`
- (Optional) Create: `infra/dev/docker-compose.yml`

- [ ] **Step 1: 写 Nginx 反代配置**

Create `infra/dev/nginx.conf`:

```nginx
events {}
http {
  server {
    listen 8080;

    # web admin static site
    location / {
      proxy_pass http://web:8000/;
    }

    # same-site API proxy
    location /api/ {
      proxy_pass http://api:8001/api/;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
    }
  }
}
```

- [ ] **Step 2: 运行并手动验证**

Run（示例：用两个终端分别启动）:

```bash
# terminal 1
cd apps/api && source .venv/bin/activate && python manage.py runserver 0.0.0.0:8001

# terminal 2
cd apps/web-admin && npm i && npm run dev -- --host 0.0.0.0 --port 8000
```

验证点：
- 浏览器访问 `http://localhost:8000` 能看到前端页面
- 前端登录成功后，`/api/me` 返回用户信息
- 浏览器 Network 中对 `/api/*` 的请求 **自动携带 Cookie**（credentials: include）

- [ ] **Step 3: Commit**

Run:

```bash
git add infra/dev
git commit -m "chore(infra): add dev reverse proxy config for same-site /api"
```

---

## Self-Review Checklist（执行者在实现前再确认）

- 计划中是否所有路径都是“同站点 /api 反代”而非跨站点请求？
- 是否存在任何 “TBD/TODO/后面再说” 的占位？如有，必须补齐或删除
- `/api/me` 是否能支撑前端菜单/路由过滤？
- 401/403/400/409 是否有清晰的返回结构，便于前端处理？

