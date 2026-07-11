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
pip install -e ".[dev]"
ffmpeg -version
ffprobe -version
mkdir -p /var/lib/motioncare/training-video-staging
test -w /var/lib/motioncare/training-video-staging
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

Segmented training video environment variables:

```bash
TRAINING_VIDEO_STAGING_ROOT=/var/lib/motioncare/training-video-staging
TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES=33554432
TRAINING_VIDEO_MAX_SIZE_BYTES=209715200
TRAINING_VIDEO_MAX_DURATION_SECONDS=600
TRAINING_VIDEO_MAX_SEGMENTS=120
TRAINING_VIDEO_STAGING_TTL_SECONDS=86400
TRAINING_VIDEO_MIN_FREE_BYTES=5368709120
VIDEO_ASSEMBLY_TIMEOUT_SECONDS=1800
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

Do not raise this to the full 200 MB training-video limit. The staging directory
must not be exposed by Django, Nginx, or static file serving, and it must be
excluded from server backups.

Start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Demo Login

- Phone: `13800000000`
- Password: `pass123456`
