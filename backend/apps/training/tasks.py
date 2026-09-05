import re
import logging

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from .motion_analysis_monitoring import (
    expire_stale_motion_analysis_jobs,
    motion_analysis_health_snapshot,
    reconcile_motion_analysis_cleanup_tombstones,
)


FAILURE_REASON_MAX_LENGTH = 2000
URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"(?i)(token=)[^&\s]+")
CREDENTIAL_PATTERN = re.compile(
    r"(?i)\b(access[_-]?key|secret[_-]?key|credential[_-]?id|AK|SK)\b"
    r"\s*[:=]\s*[^\s,;&]+"
)
LOCAL_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s'\";,()]+)")
logger = logging.getLogger(__name__)


def _safe_failure_reason(stage, exc):
    message = str(exc)
    message = URL_PATTERN.sub("[URL已隐藏]", message)
    message = TOKEN_PATTERN.sub(r"\1[已隐藏]", message)
    message = CREDENTIAL_PATTERN.sub(r"\1=[密钥已隐藏]", message)
    message = LOCAL_PATH_PATTERN.sub("[路径已隐藏]", message)
    for secret in (settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY):
        if secret:
            message = message.replace(secret, "[密钥已隐藏]")
    if not message:
        message = "无详细信息"
    reason = f"{stage}失败（{type(exc).__name__}）：{message}"
    return reason[:FAILURE_REASON_MAX_LENGTH]


@shared_task(ignore_result=True)
def recover_stale_motion_analysis_jobs():
    _positive_monitoring_setting("PP_MCARE_MONITOR_INTERVAL_SECONDS")
    reconcile_motion_analysis_cleanup_tombstones()
    return expire_stale_motion_analysis_jobs()


def _positive_monitoring_setting(name):
    value = getattr(settings, name, None)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ImproperlyConfigured(f"{name} 配置无效")
    return value


@shared_task(ignore_result=True)
def record_motion_analysis_health_snapshot():
    _positive_monitoring_setting("PP_MCARE_MONITOR_INTERVAL_SECONDS")
    warning_threshold = _positive_monitoring_setting("PP_MCARE_PENDING_WARNING_SECONDS")
    snapshot = motion_analysis_health_snapshot(now=timezone.now())
    metrics = snapshot.to_dict()
    logger.info("motion_analysis_health_snapshot", extra=metrics)
    if snapshot.oldest_pending_age_seconds > warning_threshold:
        logger.warning(
            "motion_analysis_pending_age_warning",
            extra={
                "reason_code": "oldest_pending_age_exceeded",
                "pending_count": snapshot.pending_count,
                "oldest_pending_age_seconds": snapshot.oldest_pending_age_seconds,
                "warning_threshold_seconds": warning_threshold,
                "running_count": snapshot.running_count,
                "expired_running_lease_count": snapshot.expired_running_lease_count,
            },
        )
    return metrics


from .video_tasks import (  # noqa: E402,F401
    cleanup_qiniu_tombstone,
    cleanup_qiniu_tombstones,
    cleanup_training_video_files,
    cleanup_unbound_training_video,
    expire_stale_training_video_sessions,
    recover_training_video_cleanup,
    recover_stale_video_assembly_jobs,
    run_video_assembly_job,
)
