import re
import shutil
import tempfile
from pathlib import Path
from urllib.request import urlopen

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .analysis import analyze_shoulder_press_keypoints
from .models import MotionAnalysisJob
from .pose_inference import PP_TINYPOSE_MODEL_NAME, extract_video_keypoint_frames
from .video_services import create_private_download_url


FAILURE_REASON_MAX_LENGTH = 2000
URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"(?i)(token=)[^&\s]+")


def download_private_video(url, destination, *, timeout, opener=urlopen):
    destination = Path(destination)
    with opener(url, timeout=timeout) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _safe_failure_reason(stage, exc):
    message = str(exc)
    message = URL_PATTERN.sub("[URL已隐藏]", message)
    message = TOKEN_PATTERN.sub(r"\1[已隐藏]", message)
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
        .select_related("training_video")
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


@transaction.atomic
def _persist_success(job_id, result):
    total, standard, nonstandard = _validated_counts(result)
    job = MotionAnalysisJob.objects.select_for_update(of=("self",)).get(pk=job_id)
    if job.status != MotionAnalysisJob.Status.RUNNING:
        return job
    job.status = MotionAnalysisJob.Status.SUCCEEDED
    job.algorithm_version = PP_TINYPOSE_MODEL_NAME
    job.total_count = total
    job.standard_count = standard
    job.nonstandard_count = nonstandard
    job.result_payload = result
    job.failure_reason = ""
    job.finished_at = timezone.now()
    job.save(
        update_fields=[
            "status",
            "algorithm_version",
            "total_count",
            "standard_count",
            "nonstandard_count",
            "result_payload",
            "failure_reason",
            "finished_at",
            "updated_at",
        ]
    )
    return job


@transaction.atomic
def _persist_failure(job_id, reason):
    job = MotionAnalysisJob.objects.select_for_update(of=("self",)).get(pk=job_id)
    if job.status != MotionAnalysisJob.Status.RUNNING:
        return job
    job.status = MotionAnalysisJob.Status.FAILED
    job.failure_reason = reason
    job.finished_at = timezone.now()
    job.save(
        update_fields=["status", "failure_reason", "finished_at", "updated_at"]
    )
    return job


@shared_task(ignore_result=True)
def run_motion_analysis_job(job_id):
    job, claimed = _claim_job(job_id)
    if not claimed:
        return job

    temporary_path = None
    stage = "生成下载地址"
    try:
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
        )
        stage = "关键点推理"
        frames = extract_video_keypoint_frames(
            temporary_path,
            sample_fps=settings.MOTION_ANALYSIS_SAMPLE_FPS,
        )
        stage = "规则分析"
        result = analyze_shoulder_press_keypoints(frames)
        stage = "保存结果"
        return _persist_success(job.id, result)
    except Exception as exc:
        return _persist_failure(job.id, _safe_failure_reason(stage, exc))
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
