# MotionCare Development

## Stack

- Backend: Django + Django REST Framework
- Database: PostgreSQL
- Task broker: Redis + Celery
- Frontend: React + TypeScript + Ant Design

## Local Startup

Backend prerequisites:

```bash
docker compose up -d postgres redis
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e "../packages/motion_analysis_contract"
pip install -e ".[dev]"
ffmpeg -version
ffprobe -version
SERVICE_USER=motioncare
SERVICE_GROUP=motioncare
sudo install -d -m 0700 -o "$SERVICE_USER" -g "$SERVICE_GROUP" /var/lib/motioncare/training-video-staging
sudo -u "$SERVICE_USER" test -rwx /var/lib/motioncare/training-video-staging
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

Run the default Celery worker in another terminal. It handles the default `celery`
queue, including motion analysis, video cleanup, stale recovery, and expiration:

```bash
cd backend
. .venv/bin/activate
celery -A config worker -Q celery
```

Run the video assembly worker in a separate terminal. This queue executes FFmpeg
and final Qiniu upload jobs only, so it must stay at single concurrency:

```bash
cd backend
. .venv/bin/activate
export VIDEO_ASSEMBLY_MAX_CONCURRENCY=1
celery -A config worker -Q video-assembly --concurrency="$VIDEO_ASSEMBLY_MAX_CONCURRENCY"
```

`VIDEO_ASSEMBLY_MAX_CONCURRENCY` is a process startup value for the command
above. Django settings do not read it at runtime; keep it fixed at `1`.

Run Celery Beat in another terminal:

```bash
cd backend
. .venv/bin/activate
celery -A config beat
```

Both Celery workers and Beat must be running. For the segmented training video
flow, Django Web, the default worker, the `video-assembly` worker, and Beat must
run on the same host or otherwise share the same `TRAINING_VIDEO_STAGING_ROOT`.
All four processes must run as the same OS `SERVICE_USER`; a root-owned or
group/world-enumerable staging directory is rejected even when it is writable.

Segmented training video environment variables:

```bash
TRAINING_VIDEO_STAGING_ROOT=/var/lib/motioncare/training-video-staging
TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES=33554432
TRAINING_VIDEO_MAX_SIZE_BYTES=536870912
TRAINING_VIDEO_MAX_DURATION_SECONDS=1800
TRAINING_VIDEO_MAX_SEGMENTS=360
TRAINING_VIDEO_STAGING_TTL_SECONDS=86400
TRAINING_VIDEO_MIN_FREE_BYTES=5368709120
VIDEO_ASSEMBLY_TIMEOUT_SECONDS=1800
QINIU_UPLOAD_TIMEOUT_SECONDS=900
QINIU_UPLOAD_REQUEST_TIMEOUT_SECONDS=30
QINIU_UPLOAD_REQUEST_RETRIES=3
QINIU_UPLOAD_LATE_COMPLETION_GRACE_SECONDS=300
VIDEO_ASSEMBLY_MAX_CONCURRENCY=1
VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS=3600
FFMPEG_PATH=/usr/bin/ffmpeg
FFPROBE_PATH=/usr/bin/ffprobe
QINIU_ACCESS_KEY=<backend-only>
QINIU_SECRET_KEY=<backend-only>
QINIU_BUCKET=<private-bucket>
QINIU_DOWNLOAD_DOMAIN=<private-download-domain>
QINIU_DOWNLOAD_TOKEN_TTL_SECONDS=600
```

On a local macOS Homebrew setup, `FFMPEG_PATH` and `FFPROBE_PATH` may be
`/opt/homebrew/bin/ffmpeg` and `/opt/homebrew/bin/ffprobe`. Qiniu AK/SK must only
exist in backend Web, worker, and Beat environments; never expose them to the
miniapp or frontend.

Nginx upload limits should cover one 32 MB segment plus multipart overhead, for
example:

```nginx
client_max_body_size 40m;
```

Do not raise this to the full 512 MiB training-video limit. The staging directory
must not be exposed by Django, Nginx, or static file serving, and it must be
excluded from server backups.

Start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## 微信小程序构建与上传

正式配置集中在 `miniapp/config/weapp-release.json`。默认 `npm run build:weapp`
与 `npm run build:weapp:prod` 都执行正式构建：固定线上 API 和素材地址，拒绝环境变量
覆盖。正式构建拒绝落后于 `origin/main` 或缺失私有素材签名逻辑的工作区；发布前先同步远端引用。
先生成并检查当前版本的本地素材清单，再通过既有 `verify_miniapp_signed_assets` 命令验证签名下载、正文完整性
以及匿名/篡改/过期访问拒绝。私有素材匿名返回 401 是预期行为，禁止改用公开素材门禁。
该命令默认使用后端 `.venv` 与服务端签名配置，可通过 `PYTHON` 指定解释器。
CI 使用 `build:weapp:ci` 执行离线正式构建和本地门禁，不注入生产签名密钥；CI 构建通过
不等于线上素材验收通过。上传入口始终重新执行完整线上验收，不能复用 CI 包直接上传。
随后检查实际产物的 AppID、地址、域名校验开关和包体。产物位于
`miniapp/deploy_versions/weapp/`，可将这个目录独立导入微信开发者工具。

本地开发使用 `npm run dev:weapp` 或 `npm run build:weapp:dev`，产物仍在 `miniapp/dist/`。
**不得上传 `miniapp/` 或 `miniapp/dist/` 中的开发产物。**

从干净的 `main` 工作区，在 `miniapp/` 中执行：

```bash
npm run upload:weapp
```

默认版本为 `7.1.1`，描述为 `bugs fix`，读取自 `config/weapp-release.json`。
也可用 `npm run upload:weapp -- <版本号> "版本说明"` 同时覆盖这两个值。

上传入口先运行全量小程序测试，重新正式构建并执行门禁，再复制到独立版本目录
`deploy_versions/<版本号>/miniprogram/`，只上传这个快照。任何失败都会停止；构建失败会清理
不完整产物；同一版本禁止覆盖。相邻的 `release.json` 记录提交、版本、地址、文件哈希和上传状态。
可通过 `WECHAT_DEVTOOLS_CLI` 指定微信开发者工具 CLI 的安装路径。

CLI 上传成功只代表开发版上传成功。必须在微信后台核对 AppID 和版本，并确认
`https://mcare-wx.whestsun.com` 在 request 合法域名中、正式素材域名在所需的下载域名配置中；
使用关闭调试的真机验证登录和素材加载后，才能报告发布验收通过。

## Demo Login

- Phone: `13800000000`
- Password: `pass123456`
