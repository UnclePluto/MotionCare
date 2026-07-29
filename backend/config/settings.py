from pathlib import Path
import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(ROOT_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "local-dev-secret")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
DEFAULT_ALLOWED_HOSTS = "localhost,127.0.0.1,*" if DEBUG else "localhost,127.0.0.1"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS).split(",")
CSRF_TRUSTED_ORIGINS = os.getenv(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:5174,http://127.0.0.1:5174",
).split(",")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SESSION_COOKIE_SECURE", str(not DEBUG)).lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_CSRF_COOKIE_SECURE", str(not DEBUG)).lower() == "true"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "apps.accounts",
    "apps.common",
    "apps.patients",
    "apps.studies",
    "apps.visits",
    "apps.prescriptions",
    "apps.training",
    "apps.health",
    "apps.patient_app",
    "apps.crf",
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

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_CONN_MAX_AGE = int(os.getenv("DATABASE_CONN_MAX_AGE", "0" if DEBUG else "60"))
DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL", "postgres://motioncare:motioncare@localhost:5432/motioncare"),
        conn_max_age=DATABASE_CONN_MAX_AGE,
        conn_health_checks=True,
    )
}

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = ROOT_DIR / os.getenv("STATIC_ROOT", "staticfiles")
MEDIA_URL = "media/"
MEDIA_ROOT = ROOT_DIR / "media"
QINIU_ACCESS_KEY = os.getenv("QINIU_ACCESS_KEY", "")
QINIU_SECRET_KEY = os.getenv("QINIU_SECRET_KEY", "")
QINIU_BUCKET = os.getenv("QINIU_BUCKET", "motioncare-training")
QINIU_DOWNLOAD_DOMAIN = os.getenv("QINIU_DOWNLOAD_DOMAIN", "")
QINIU_DOWNLOAD_TOKEN_TTL_SECONDS = int(os.getenv("QINIU_DOWNLOAD_TOKEN_TTL_SECONDS", "600"))
TRAINING_VIDEO_MAX_SIZE_BYTES = int(
    os.getenv("TRAINING_VIDEO_MAX_SIZE_BYTES", str(200 * 1024 * 1024))
)
TRAINING_VIDEO_MAX_DURATION_SECONDS = int(
    os.getenv("TRAINING_VIDEO_MAX_DURATION_SECONDS", "600")
)
TRAINING_VIDEO_STAGING_ROOT = Path(os.getenv(
    "TRAINING_VIDEO_STAGING_ROOT",
    "/var/lib/motioncare/training-video-staging",
))
TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES = int(os.getenv(
    "TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES", str(32 * 1024 * 1024)
))
TRAINING_VIDEO_MAX_SEGMENTS = int(os.getenv("TRAINING_VIDEO_MAX_SEGMENTS", "120"))
TRAINING_VIDEO_STAGING_TTL_SECONDS = int(os.getenv(
    "TRAINING_VIDEO_STAGING_TTL_SECONDS", "86400"
))
TRAINING_VIDEO_MIN_FREE_BYTES = int(os.getenv(
    "TRAINING_VIDEO_MIN_FREE_BYTES", str(5 * 1024 * 1024 * 1024)
))
VIDEO_ASSEMBLY_TIMEOUT_SECONDS = int(os.getenv("VIDEO_ASSEMBLY_TIMEOUT_SECONDS", "1800"))
QINIU_UPLOAD_TIMEOUT_SECONDS = int(os.getenv("QINIU_UPLOAD_TIMEOUT_SECONDS", "900"))
QINIU_UPLOAD_REQUEST_TIMEOUT_SECONDS = int(
    os.getenv("QINIU_UPLOAD_REQUEST_TIMEOUT_SECONDS", "30")
)
QINIU_MOVE_REQUEST_TIMEOUT_SECONDS = int(
    os.getenv("QINIU_MOVE_REQUEST_TIMEOUT_SECONDS", "10")
)
QINIU_UPLOAD_REQUEST_RETRIES = int(os.getenv("QINIU_UPLOAD_REQUEST_RETRIES", "3"))
QINIU_UPLOAD_LATE_COMPLETION_GRACE_SECONDS = int(
    os.getenv("QINIU_UPLOAD_LATE_COMPLETION_GRACE_SECONDS", "300")
)
VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS = int(os.getenv(
    "VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS", "3600"
))
if min(
    QINIU_UPLOAD_TIMEOUT_SECONDS,
    QINIU_UPLOAD_REQUEST_TIMEOUT_SECONDS,
    QINIU_MOVE_REQUEST_TIMEOUT_SECONDS,
    QINIU_UPLOAD_LATE_COMPLETION_GRACE_SECONDS,
) <= 0 or QINIU_UPLOAD_REQUEST_RETRIES <= 0:
    raise ImproperlyConfigured("七牛上传超时与补偿配置无效")
if VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS <= (
    VIDEO_ASSEMBLY_TIMEOUT_SECONDS + QINIU_UPLOAD_TIMEOUT_SECONDS
):
    raise ImproperlyConfigured(
        "VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS 必须大于合并与七牛上传超时之和"
    )
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "/usr/bin/ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "/usr/bin/ffprobe")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# Task 2 will switch to custom user model ("accounts.User").
AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["apps.common.permissions.IsAuthenticatedAndPasswordChanged"],
}

CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_ROUTES = {
    "apps.training.video_tasks.run_video_assembly_job": {"queue": "video-assembly"},
}
MOTION_ANALYSIS_DOWNLOAD_TIMEOUT_SECONDS = int(
    os.getenv("MOTION_ANALYSIS_DOWNLOAD_TIMEOUT_SECONDS", "30")
)
MOTION_ANALYSIS_DOWNLOAD_DEADLINE_SECONDS = int(
    os.getenv("MOTION_ANALYSIS_DOWNLOAD_DEADLINE_SECONDS", "120")
)
MOTION_ANALYSIS_SAMPLE_FPS = float(os.getenv("MOTION_ANALYSIS_SAMPLE_FPS", "5"))
MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS = int(
    os.getenv("MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS", "1800")
)
MOTION_ANALYSIS_STALE_RECOVERY_INTERVAL_SECONDS = int(
    os.getenv("MOTION_ANALYSIS_STALE_RECOVERY_INTERVAL_SECONDS", "300")
)
CELERY_BEAT_SCHEDULE = {
    "recover-stale-motion-analysis-jobs": {
        "task": "apps.training.tasks.recover_stale_motion_analysis_jobs",
        "schedule": MOTION_ANALYSIS_STALE_RECOVERY_INTERVAL_SECONDS,
    },
    "recover-stale-video-assembly-jobs": {
        "task": "apps.training.video_tasks.recover_stale_video_assembly_jobs",
        "schedule": 300,
    },
    "expire-stale-training-video-sessions": {
        "task": "apps.training.video_tasks.expire_stale_training_video_sessions",
        "schedule": 900,
    },
    "recover-training-video-cleanup": {
        "task": "apps.training.video_tasks.recover_training_video_cleanup",
        "schedule": 900,
    },
    "cleanup-qiniu-tombstones": {
        "task": "apps.training.video_tasks.cleanup_qiniu_tombstones",
        "schedule": 300,
    },
}
CRF_TEMPLATE_PATH = ROOT_DIR / os.getenv(
    "CRF_TEMPLATE_PATH",
    "docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx",
)
CRF_EXPORT_DIR = ROOT_DIR / os.getenv("CRF_EXPORT_DIR", "media/crf_exports")
