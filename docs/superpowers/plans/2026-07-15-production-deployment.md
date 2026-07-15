# MotionCare 生产部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 状态：implementing
> 日期：2026-07-15
> 范围：在不改动服务器既有业务容器的前提下，将 MotionCare 以独立 Docker Compose 项目部署到 171.43.135.71，并接入现有 OpenResty。
> 实施基线 commit：96be89d

**Goal:** 建立可重复、可回滚的 MotionCare 生产部署链路，并完成首次上线。

**Architecture:** GitHub 保存源码并在主分支或 `deploy-*` 标签上构建 amd64 镜像，镜像推送至阿里云 ACR 的 `dypluto/motioncare` 仓库。服务器只运行 `motioncare-prod` Compose 项目，PostgreSQL、Redis 和媒体目录使用 `/opt/motioncare-prod/data` 下的独立持久化目录；三个应用端口仅绑定回环地址，同时通过已有 `whest_Lan` 网络供 OpenResty 访问。

**Tech Stack:** Docker Buildx、Docker Compose v2、GitHub Actions、阿里云 ACR、Django/Gunicorn/Celery、PostgreSQL 16、Redis 7、Nginx/OpenResty。

## Global Constraints

- 不停止、重启、重建或修改任何现有业务容器。
- 不执行 `docker system prune`、`docker image prune -a`、`docker network prune` 或全局资源清理。
- Compose 项目名固定为 `motioncare-prod`，容器名和网络别名使用 `motioncare-*` 前缀。
- 对外调试端口只绑定 `127.0.0.1:18080-18082`。
- OpenResty 只新增 `/opt/service/openresty_ssl_conf.d/motioncare.conf`；先 `nginx -t`，成功后只执行平滑 reload。
- 生产密钥只保存在 GitHub Secrets 或服务器 `/opt/motioncare-prod/.env`，权限为 `0600`。
- PostgreSQL、Redis 和媒体文件不使用现有服务器的数据库、缓存、对象存储或 Docker volume。

---

### Task 1：生产镜像与运行配置

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.prod.conf`
- Create: `miniapp/Dockerfile`
- Create: `miniapp/nginx.prod.conf`
- Create: `.dockerignore`
- Modify: `backend/pyproject.toml`
- Modify: `backend/config/settings.py`
- Modify: `.gitignore`
- Track: `docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx`

- [ ] 构建 Python 3.12 amd64 后端镜像，安装 Gunicorn 与 FFmpeg，使用非 root 用户运行。
- [ ] 构建管理端和患者 H5 的静态 Nginx 镜像，并提供 `/healthz`。
- [ ] 补齐生产代理、安全 Cookie、静态目录配置，并保持本地 CSRF 默认来源不变。
- [ ] 运行后端测试、Ruff、迁移检查及前端/小程序测试构建。

### Task 2：隔离 Compose 与部署脚本

**Files:**
- Create: `deploy/docker-compose.prod.yml`
- Create: `deploy/deploy.sh`
- Create: `deploy/openresty/motioncare.conf`
- Create: `deploy/env.production.example`

- [ ] 定义独立 PostgreSQL、Redis、迁移、API、Celery、管理端和患者 H5 服务。
- [ ] 将数据库、Redis、媒体、静态和备份目录绑定到 `/opt/motioncare-prod/data`。
- [ ] 部署脚本只操作 `docker compose -p motioncare-prod`，更新前仅备份 MotionCare 数据库。
- [ ] 使用 `docker compose config` 校验配置，不启动本地生产容器。

### Task 3：GitHub Actions 构建与发布

**Files:**
- Create: `.github/workflows/deploy-production.yml`

- [ ] 在 `main` 推送、`deploy-*` 标签和手动触发时运行全量验证。
- [ ] 使用 Buildx 构建 `linux/amd64` 的 backend/web/wx 镜像并推送 ACR。
- [ ] 将 PostgreSQL 16 与 Redis 7 基础镜像镜像到同一 ACR 仓库固定标签。
- [ ] 通过固定 SSH 主机指纹把 Compose 和部署脚本发布到服务器，再执行远端部署。

### Task 4：服务器隔离初始化

- [ ] 创建 `motioncare` 部署用户并加入 Docker 组，不修改现有用户权限。
- [ ] 创建 `/opt/motioncare-prod` 及其数据子目录，只授权 MotionCare 使用。
- [ ] 生成独立数据库密码和 Django Secret Key，把本地七牛变量安全写入服务器 `.env`。
- [ ] 安装专用 SSH 公钥，并把私钥、主机指纹和服务器变量写入 GitHub Secrets/Variables。

### Task 5：首次镜像发布与容器启动

- [ ] 提交并推送部署文件，创建 `deploy-20260715-initial` 标签触发构建。
- [ ] 确认 ACR 中存在本 commit 的 backend/web/wx 标签及固定 infra 标签。
- [ ] 服务器拉取镜像、执行迁移和静态文件收集，再启动全部 MotionCare 服务。
- [ ] 验证所有 MotionCare 容器健康、`18080-18082` 可访问，现有容器 ID 与运行状态未变化。

### Task 6：OpenResty 增量接入与外部验收

- [ ] 备份现有 OpenResty 配置文件清单和 `motioncare.conf`（若存在）。
- [ ] 原子写入新的 MotionCare 配置，运行 `docker exec OpenResty nginx -t`。
- [ ] 配置测试成功后执行 `docker exec OpenResty nginx -s reload`。
- [ ] 验证三个 HTTPS 域名、管理端 `/api/auth/csrf/`、患者 H5 和 API 响应。
- [ ] 再次确认所有部署前存在的容器仍保持运行，未发生重建。

### Task 7：收口与轮换

- [ ] 创建必须修改密码的首个管理员账号，不导入演示弱密码。
- [ ] 记录部署 commit、镜像标签和回滚命令。
- [ ] 首次部署验收后轮换已在聊天中出现的 ACR 密码，并同步更新 GitHub Secret 与服务器 Docker 登录。
