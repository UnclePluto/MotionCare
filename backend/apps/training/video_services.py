import hashlib
import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from apps.prescriptions.models import Prescription, PrescriptionAction

from .models import (
    MotionAnalysisJob,
    TrainingVideo,
    TrainingVideoSegment,
    VideoProcessingJob,
)
from .qiniu import private_download_url

SHOULDER_PRESS_SOURCE_KEY = "motion-resistance-shoulder-press"
MAX_MISSING_SEGMENTS_RESPONSE = 100


class SegmentConflictError(Exception):
    pass


class MissingSegmentsError(Exception):
    def __init__(self, missing_segments, *, truncated=False):
        super().__init__("训练视频分片不完整")
        self.missing_segments = missing_segments
        self.truncated = truncated


def _bounded_missing_segments(uploaded_indexes, segment_count):
    missing_total = segment_count - len(uploaded_indexes)
    missing = []
    expected = 0
    for index in sorted(uploaded_indexes):
        if index > expected and len(missing) < MAX_MISSING_SEGMENTS_RESPONSE:
            take = min(index - expected, MAX_MISSING_SEGMENTS_RESPONSE - len(missing))
            missing.extend(range(expected, expected + take))
        expected = index + 1
    if expected < segment_count and len(missing) < MAX_MISSING_SEGMENTS_RESPONSE:
        take = min(segment_count - expected, MAX_MISSING_SEGMENTS_RESPONSE - len(missing))
        missing.extend(range(expected, expected + take))
    return missing, missing_total > len(missing)


def _active_prescription(project_patient):
    return (
        Prescription.objects.filter(
            project_patient=project_patient, status=Prescription.Status.ACTIVE
        )
        .order_by("-effective_at", "-id")
        .first()
    )


def _get_current_shoulder_action(project_patient, prescription_action_id):
    active = _active_prescription(project_patient)
    if active is None:
        raise ValidationError("当前无生效处方")
    action = (
        PrescriptionAction.objects.select_related("action_library_item")
        .filter(pk=prescription_action_id, prescription=active)
        .first()
    )
    if action is None:
        raise ValidationError("处方已更新，请返回当前处方重新进入")
    if action.action_library_item.source_key != SHOULDER_PRESS_SOURCE_KEY:
        raise ValidationError("当前仅肩部推举支持录像上传")
    return active, action


@transaction.atomic
def create_training_video_session(*, project_patient, prescription_action_id):
    active, action = _get_current_shoulder_action(project_patient, prescription_action_id)
    today = timezone.localdate()
    key = (
        f"training-videos/{project_patient.id}/{today:%Y/%m/%d}/"
        f"{uuid.uuid4().hex}.mp4"
    )
    return TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active,
        prescription_action=action,
        storage_backend="qiniu_kodo",
        bucket=settings.QINIU_BUCKET,
        object_key=key,
        content_type="video/mp4",
        status=TrainingVideo.Status.RECORDING,
    )


def _write_uploaded_segment(*, video_id, sequence_index, uploaded_file):
    if uploaded_file.size > settings.TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES:
        raise ValidationError("训练视频分片文件过大")
    temp_root = Path(settings.TRAINING_VIDEO_TEMP_ROOT)
    temp_root.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(temp_root).free
    required_bytes = uploaded_file.size + settings.TRAINING_VIDEO_SERVER_MIN_FREE_BYTES
    if free_bytes < required_bytes:
        raise ValidationError("业务服务器视频存储空间不足，请稍后重试")
    directory = temp_root / str(video_id)
    directory.mkdir(parents=True, exist_ok=True)
    temporary_path = directory / f".{sequence_index}-{uuid.uuid4().hex}.uploading"
    digest = hashlib.sha256()
    try:
        with temporary_path.open("wb") as target:
            for chunk in uploaded_file.chunks():
                digest.update(chunk)
                target.write(chunk)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return temporary_path, digest.hexdigest()


@transaction.atomic
def store_training_video_segment(
    *, project_patient, video_id, sequence_index, duration_seconds, uploaded_file
):
    if duration_seconds > settings.TRAINING_VIDEO_SEGMENT_MAX_DURATION_SECONDS:
        raise ValidationError("训练视频分片时长超过限制")
    if uploaded_file.content_type not in {"video/mp4", "video/quicktime"}:
        raise ValidationError("训练视频分片格式不支持")
    visible_video = TrainingVideo.objects.filter(
        pk=video_id, project_patient=project_patient
    ).values("status").first()
    if visible_video is None:
        raise Http404
    if visible_video["status"] not in {
        TrainingVideo.Status.RECORDING,
        TrainingVideo.Status.UPLOADING,
    }:
        raise ValidationError("训练录像已结束，不能继续上传分片")
    temporary_path, object_hash = _write_uploaded_segment(
        video_id=video_id,
        sequence_index=sequence_index,
        uploaded_file=uploaded_file,
    )
    final_path = temporary_path.parent / f"segment-{sequence_index:06d}.mp4"
    try:
        video = (
            TrainingVideo.objects.select_for_update()
            .filter(pk=video_id, project_patient=project_patient)
            .first()
        )
        if video is None:
            raise Http404
        if video.status not in {
            TrainingVideo.Status.RECORDING,
            TrainingVideo.Status.UPLOADING,
        }:
            raise ValidationError("训练录像已结束，不能继续上传分片")
        existing = TrainingVideoSegment.objects.filter(
            training_video=video, sequence_index=sequence_index
        ).first()
        if existing is not None:
            existing.upload_attempts += 1
            existing.save(update_fields=["upload_attempts", "updated_at"])
            if existing.object_hash != object_hash:
                raise SegmentConflictError("同一分片序号的文件内容不一致")
            if not Path(existing.server_file_path).exists():
                os.replace(temporary_path, existing.server_file_path)
            else:
                temporary_path.unlink(missing_ok=True)
            return existing, False

        os.replace(temporary_path, final_path)
        segment = TrainingVideoSegment.objects.create(
            training_video=video,
            sequence_index=sequence_index,
            server_file_path=str(final_path),
            content_type=uploaded_file.content_type,
            size_bytes=uploaded_file.size,
            duration_seconds=duration_seconds,
            object_hash=object_hash,
        )
        video.uploaded_segment_count = video.segments.count()
        video.status = TrainingVideo.Status.UPLOADING
        video.save(update_fields=["uploaded_segment_count", "status", "updated_at"])
        return segment, True
    except Exception:
        temporary_path.unlink(missing_ok=True)
        if final_path.exists() and not TrainingVideoSegment.objects.filter(
            training_video_id=video_id, sequence_index=sequence_index
        ).exists():
            final_path.unlink(missing_ok=True)
        raise


def get_patient_training_video(*, project_patient, video_id):
    video = (
        TrainingVideo.objects.select_related("training_record")
        .filter(pk=video_id, project_patient=project_patient)
        .first()
    )
    if video is None:
        raise Http404
    return video


def serialize_patient_training_video(video):
    job = None
    try:
        job = video.processing_job
    except ObjectDoesNotExist:
        pass
    return {
        "video_id": video.id,
        "status": video.status,
        "uploaded_segment_count": video.uploaded_segment_count,
        "segment_count": video.segment_count,
        "duration_seconds": video.duration_seconds,
        "processing": (
            {
                "status": job.status,
                "progress_percent": job.progress_percent,
            }
            if job
            else None
        ),
        "training_record_id": video.training_record_id,
    }


@transaction.atomic
def finish_training_video_session(
    *, project_patient, video_id, segment_count, duration_seconds, training_date
):
    video = (
        TrainingVideo.objects.select_for_update()
        .filter(pk=video_id, project_patient=project_patient)
        .first()
    )
    if video is None:
        raise Http404
    try:
        existing_job = video.processing_job
    except ObjectDoesNotExist:
        existing_job = None
    if existing_job is not None:
        if (
            video.segment_count != segment_count
            or video.duration_seconds != duration_seconds
            or video.training_date != training_date
        ):
            raise ValidationError("训练录像已结束，结束参数不一致")
        return video, existing_job, False
    if video.status not in {
        TrainingVideo.Status.RECORDING,
        TrainingVideo.Status.UPLOADING,
    }:
        raise ValidationError("训练录像已结束")

    uploaded_indexes = set(
        video.segments.filter(status=TrainingVideoSegment.Status.UPLOADED).values_list(
            "sequence_index", flat=True
        )
    )
    unexpected_indexes = sorted(index for index in uploaded_indexes if index >= segment_count)
    if unexpected_indexes:
        raise ValidationError("训练视频分片数量与结束参数不一致")
    missing_segments, missing_truncated = _bounded_missing_segments(
        uploaded_indexes, segment_count
    )
    if missing_segments:
        raise MissingSegmentsError(missing_segments, truncated=missing_truncated)

    now = timezone.now()
    expires_at = now + timezone.timedelta(
        hours=settings.TRAINING_VIDEO_PROCESSING_RETENTION_HOURS
    )
    video.segment_count = segment_count
    video.uploaded_segment_count = len(uploaded_indexes)
    video.duration_seconds = duration_seconds
    video.training_date = training_date
    video.recording_finished_at = now
    video.processing_expires_at = expires_at
    video.status = TrainingVideo.Status.QUEUED
    video.failure_reason = ""
    video.save(
        update_fields=[
            "segment_count",
            "uploaded_segment_count",
            "duration_seconds",
            "training_date",
            "recording_finished_at",
            "processing_expires_at",
            "status",
            "failure_reason",
            "updated_at",
        ]
    )
    job = VideoProcessingJob.objects.create(
        training_video=video,
        expires_at=expires_at,
    )

    def enqueue():
        from .tasks import process_training_video_job

        try:
            process_training_video_job.delay(job.id)
        except Exception as exc:
            retry_at = timezone.now() + timezone.timedelta(
                seconds=settings.TRAINING_VIDEO_RETRY_BASE_SECONDS
            )
            VideoProcessingJob.objects.filter(pk=job.id).update(
                status=VideoProcessingJob.Status.FAILED,
                next_retry_at=retry_at,
                failure_reason=f"视频任务投递失败：{str(exc)[:1800]}",
            )
            TrainingVideo.objects.filter(pk=video.id).update(
                status=TrainingVideo.Status.PROCESSING_FAILED,
                failure_reason="视频任务等待自动重投",
            )

    transaction.on_commit(enqueue)
    return video, job, True

def get_training_video_for_user(user, video_id):
    from .tracking import accessible_project_patients

    video = (
        TrainingVideo.objects.select_related(
            "project_patient", "training_record", "prescription_action"
        )
        .filter(pk=video_id, project_patient__in=accessible_project_patients(user))
        .first()
    )
    if video is None:
        raise Http404
    return video


def create_private_download_url(video):
    if video.status != TrainingVideo.Status.ATTACHED or not video.training_record_id:
        raise ValidationError("训练视频尚未处理完成")
    if not settings.QINIU_DOWNLOAD_DOMAIN:
        raise ValidationError("七牛下载域名未配置")
    parsed_domain = urlparse(settings.QINIU_DOWNLOAD_DOMAIN)
    if parsed_domain.scheme not in {"http", "https"} or not parsed_domain.netloc:
        raise ValidationError("七牛下载域名格式无效")
    if not settings.DEBUG and parsed_domain.scheme != "https":
        raise ValidationError("生产环境七牛下载域名必须使用 HTTPS")
    base = f"{settings.QINIU_DOWNLOAD_DOMAIN.rstrip('/')}/{video.object_key}"
    try:
        return private_download_url(
            base,
            expires_in_seconds=settings.QINIU_DOWNLOAD_TOKEN_TTL_SECONDS,
        )
    except ImproperlyConfigured as exc:
        raise ValidationError(str(exc)) from exc


def get_analysis_video_input(video):
    return create_private_download_url(video)


@transaction.atomic
def create_analysis_job(*, video, requested_by):
    if video.status != TrainingVideo.Status.ATTACHED or not video.training_record_id:
        raise ValidationError("训练视频尚未绑定训练记录")
    if MotionAnalysisJob.objects.filter(
        training_video=video,
        status__in=[MotionAnalysisJob.Status.PENDING, MotionAnalysisJob.Status.RUNNING],
    ).exists():
        raise ValidationError("已有进行中的分析任务")
    job = MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=video.training_record,
        project_patient=video.project_patient,
        prescription_action=video.prescription_action,
        requested_by=requested_by,
    )
    from .tasks import run_motion_analysis_job

    def enqueue():
        try:
            run_motion_analysis_job.delay(job.id)
        except Exception as exc:
            MotionAnalysisJob.objects.filter(pk=job.id).update(
                status=MotionAnalysisJob.Status.FAILED,
                failure_reason=f"分析任务投递失败：{str(exc)[:1800]}",
                finished_at=timezone.now(),
            )

    transaction.on_commit(enqueue)
    return job
