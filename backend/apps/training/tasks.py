import re
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import MotionAnalysisJob


FAILURE_REASON_MAX_LENGTH = 2000
URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"(?i)(token=)[^&\s]+")
CREDENTIAL_PATTERN = re.compile(
    r"(?i)\b(access[_-]?key|secret[_-]?key|credential[_-]?id|AK|SK)\b"
    r"\s*[:=]\s*[^\s,;&]+"
)
LOCAL_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s'\";,()]+)")


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
    timeout_seconds = settings.MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS
    now = timezone.now()
    cutoff = now - timedelta(seconds=timeout_seconds)
    failure_reason = (
        "阶段=running_stale_recovery；原因=running_timeout；"
        f"任务运行超过 {timeout_seconds} 秒未完成"
    )
    return MotionAnalysisJob.objects.filter(
        status=MotionAnalysisJob.Status.RUNNING,
        started_at__lt=cutoff,
    ).update(
        status=MotionAnalysisJob.Status.FAILED,
        failure_reason=failure_reason,
        finished_at=now,
        updated_at=now,
    )


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
