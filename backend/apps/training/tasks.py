import re
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from urllib.request import urlopen

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .analysis_registry import get_motion_analyzer
from .models import MotionAnalysisJob
from .pose_inference import extract_video_keypoint_frames
from .video_services import create_private_download_url


FAILURE_REASON_MAX_LENGTH = 2000
DOWNLOAD_CHUNK_SIZE_BYTES = 64 * 1024
URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"(?i)(token=)[^&\s]+")
CREDENTIAL_PATTERN = re.compile(
    r"(?i)\b(access[_-]?key|secret[_-]?key|credential[_-]?id|AK|SK)\b"
    r"\s*[:=]\s*[^\s,;&]+"
)
LOCAL_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s'\";,()]+)")


def _remaining_deadline_timeout(deadline, configured_timeout):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("视频下载超过整体下载时限")
    return min(configured_timeout, remaining)


def _set_urllib_response_socket_timeout(response, timeout):
    """Set urlopen's HTTPResponse socket timeout before a blocking read.

    urllib.request.urlopen() returns http.client.HTTPResponse. Its ``fp`` is a
    buffered reader, whose raw SocketIO keeps the actual socket at ``_sock``.
    """
    try:
        response.fp.raw._sock.settimeout(timeout)
    except (AttributeError, OSError) as exc:
        raise RuntimeError("无法设置 urllib HTTPResponse 的 socket timeout") from exc


def download_private_video(
    url,
    destination,
    *,
    timeout,
    max_bytes,
    deadline_seconds,
    opener=urlopen,
):
    if max_bytes <= 0:
        raise ValueError("视频下载允许大小必须大于 0")
    if deadline_seconds <= 0:
        raise ValueError("视频整体下载时限必须大于 0")
    if timeout <= 0:
        raise ValueError("视频下载 socket timeout 必须大于 0")

    destination = Path(destination)
    deadline = time.monotonic() + deadline_seconds
    connect_timeout = _remaining_deadline_timeout(deadline, timeout)
    with opener(url, timeout=connect_timeout) as response:
        if time.monotonic() >= deadline:
            raise TimeoutError("视频下载超过整体下载时限")

        declared_length = response.headers.get("Content-Length")
        try:
            declared_length = int(declared_length) if declared_length is not None else None
        except (TypeError, ValueError):
            declared_length = None
        if declared_length is not None and declared_length > max_bytes:
            raise ValueError("视频响应声明大小超过允许大小")

        downloaded_bytes = 0
        with destination.open("wb") as output:
            while True:
                read_timeout = _remaining_deadline_timeout(deadline, timeout)
                _set_urllib_response_socket_timeout(response, read_timeout)
                chunk = response.read(DOWNLOAD_CHUNK_SIZE_BYTES)
                if time.monotonic() >= deadline:
                    raise TimeoutError("视频下载超过整体下载时限")
                if not chunk:
                    break
                downloaded_bytes += len(chunk)
                if downloaded_bytes > max_bytes:
                    raise ValueError("视频流式内容超过允许大小")
                output.write(chunk)


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


@transaction.atomic
def _claim_job(job_id):
    job = (
        MotionAnalysisJob.objects.select_for_update(of=("self",))
        .select_related(
            "training_video",
            "prescription_action__action_library_item",
        )
        .get(pk=job_id)
    )
    if job.status != MotionAnalysisJob.Status.PENDING:
        return job, False
    job.status = MotionAnalysisJob.Status.RUNNING
    job.started_at = timezone.now()
    job.finished_at = None
    job.failure_reason = ""
    job.save(
        update_fields=[
            "status",
            "started_at",
            "finished_at",
            "failure_reason",
            "updated_at",
        ]
    )
    return job, True


def _validated_counts(result):
    counts = []
    for name in ("total_count", "standard_count", "nonstandard_count"):
        value = result.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"分析结果 {name} 无效")
        counts.append(value)
    total, standard, nonstandard = counts
    if total != standard + nonstandard:
        raise ValueError("分析结果计数不满足 total=standard+nonstandard")
    return total, standard, nonstandard


def _persist_success(job_id, result, algorithm_version):
    total, standard, nonstandard = _validated_counts(result)
    now = timezone.now()
    MotionAnalysisJob.objects.filter(
        pk=job_id,
        status=MotionAnalysisJob.Status.RUNNING,
    ).update(
        status=MotionAnalysisJob.Status.SUCCEEDED,
        algorithm_version=algorithm_version,
        total_count=total,
        standard_count=standard,
        nonstandard_count=nonstandard,
        result_payload=result,
        failure_reason="",
        finished_at=now,
        updated_at=now,
    )
    return MotionAnalysisJob.objects.get(pk=job_id)


def _persist_failure(job_id, reason):
    now = timezone.now()
    MotionAnalysisJob.objects.filter(
        pk=job_id,
        status=MotionAnalysisJob.Status.RUNNING,
    ).update(
        status=MotionAnalysisJob.Status.FAILED,
        failure_reason=reason,
        finished_at=now,
        updated_at=now,
    )
    return MotionAnalysisJob.objects.get(pk=job_id)


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


@shared_task(ignore_result=True)
def run_motion_analysis_job(job_id):
    job, claimed = _claim_job(job_id)
    if not claimed:
        return job

    temporary_path = None
    stage = "选择分析器"
    try:
        source_key = job.prescription_action.action_library_item.source_key
        analyzer = get_motion_analyzer(source_key)
        if analyzer is None:
            raise ValueError("不支持当前动作分析")

        stage = "生成下载地址"
        private_url = create_private_download_url(job.training_video)
        suffix = Path(job.training_video.object_key).suffix or ".mp4"
        with tempfile.NamedTemporaryFile(
            prefix=f"motion-analysis-{job.id}-",
            suffix=suffix,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        stage = "下载视频"
        download_private_video(
            private_url,
            temporary_path,
            timeout=settings.MOTION_ANALYSIS_DOWNLOAD_TIMEOUT_SECONDS,
            max_bytes=job.training_video.size_bytes,
            deadline_seconds=settings.MOTION_ANALYSIS_DOWNLOAD_DEADLINE_SECONDS,
        )
        stage = "关键点推理"
        frames = extract_video_keypoint_frames(
            temporary_path,
            sample_fps=settings.MOTION_ANALYSIS_SAMPLE_FPS,
        )
        stage = "规则分析"
        result = analyzer.analyze_keypoints(frames)
        stage = "保存结果"
        return _persist_success(job.id, result, analyzer.algorithm_version)
    except Exception as exc:
        return _persist_failure(job.id, _safe_failure_reason(stage, exc))
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


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
