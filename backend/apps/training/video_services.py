import os
import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.http import Http404
from django.utils import timezone

from apps.prescriptions.models import Prescription, PrescriptionAction

from .models import (
    MotionAnalysisJob,
    TrainingVideo,
    TrainingVideoSegment,
    VideoAssemblyJob,
)
from .qiniu import private_download_url
from .video_staging import (
    SegmentConflict,
    segment_path,
    write_uploaded_segment,
)

SHOULDER_PRESS_SOURCE_KEY = "motion-resistance-shoulder-press"


def _active_prescription(project_patient):
    return (
        Prescription.objects.filter(
            project_patient=project_patient,
            status=Prescription.Status.ACTIVE,
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


def _ensure_staging_available():
    if shutil.which(str(settings.FFMPEG_PATH)) is None:
        raise ValidationError("FFmpeg 不可用，暂时无法开始录像")

    root = Path(settings.TRAINING_VIDEO_STAGING_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < settings.TRAINING_VIDEO_MIN_FREE_BYTES:
        raise ValidationError("训练视频临时磁盘空间不足")


def create_training_video_session(
    *,
    project_patient,
    client_session_id,
    prescription_action_id,
    training_date,
    expected_duration_seconds,
):
    if expected_duration_seconds > settings.TRAINING_VIDEO_MAX_DURATION_SECONDS:
        raise ValidationError("训练视频时长超过限制")
    _ensure_staging_available()
    active, action = _get_current_shoulder_action(
        project_patient, prescription_action_id
    )
    video, created = TrainingVideo.objects.get_or_create(
        project_patient=project_patient,
        client_session_id=client_session_id,
        defaults={
            "prescription": active,
            "prescription_action": action,
            "training_date": training_date,
            "expected_duration_seconds": expected_duration_seconds,
            "status": TrainingVideo.Status.RECORDING,
        },
    )
    return video, created


def _validate_segment_request(index, uploaded_file, duration_ms, declared_size_bytes):
    if index >= settings.TRAINING_VIDEO_MAX_SEGMENTS:
        raise ValidationError("训练视频分段数量超过限制")
    if declared_size_bytes > settings.TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES:
        raise ValidationError("训练视频分段过大")
    if duration_ms > settings.TRAINING_VIDEO_MAX_DURATION_SECONDS * 1000:
        raise ValidationError("训练视频分段时长超过限制")
    content_type = (uploaded_file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type != "video/mp4":
        raise ValidationError("训练视频分段必须是 MP4 文件")


def _segment_matches(segment, *, duration_ms, size_bytes, sha256):
    return (
        segment.status == TrainingVideoSegment.Status.UPLOADED
        and segment.duration_ms == duration_ms
        and segment.size_bytes == size_bytes
        and segment.sha256 == sha256
    )


def store_training_video_segment(
    *,
    project_patient,
    video_id,
    index,
    uploaded_file,
    duration_ms,
    declared_size_bytes,
):
    preliminary_video = TrainingVideo.objects.filter(
        pk=video_id,
        project_patient=project_patient,
    ).first()
    if preliminary_video is None:
        raise Http404

    _validate_segment_request(index, uploaded_file, duration_ms, declared_size_bytes)
    temporary, actual_size_bytes, sha256 = write_uploaded_segment(
        preliminary_video, index, uploaded_file
    )
    destination = segment_path(preliminary_video, index)
    destination_was_installed = False
    try:
        if actual_size_bytes != declared_size_bytes:
            raise ValidationError("训练视频分段实际大小与声明不一致")

        with transaction.atomic():
            video = (
                TrainingVideo.objects.select_for_update(of=("self",))
                .filter(pk=video_id, project_patient=project_patient)
                .first()
            )
            if video is None:
                raise Http404
            if video.status not in {
                TrainingVideo.Status.RECORDING,
                TrainingVideo.Status.UPLOADING_SEGMENTS,
            }:
                raise ValidationError("训练视频会话当前不可上传分段")

            existing = TrainingVideoSegment.objects.filter(
                training_video=video,
                index=index,
            ).first()
            if existing is not None:
                if _segment_matches(
                    existing,
                    duration_ms=duration_ms,
                    size_bytes=actual_size_bytes,
                    sha256=sha256,
                ):
                    return existing, False
                raise SegmentConflict("重复分段与已上传内容冲突")

            totals = TrainingVideoSegment.objects.filter(
                training_video=video,
                status=TrainingVideoSegment.Status.UPLOADED,
            ).aggregate(
                segment_count=Count("id"),
                total_size_bytes=Sum("size_bytes"),
                total_duration_ms=Sum("duration_ms"),
            )
            segment_count = totals["segment_count"] or 0
            total_size_bytes = totals["total_size_bytes"] or 0
            total_duration_ms = totals["total_duration_ms"] or 0
            if segment_count + 1 > settings.TRAINING_VIDEO_MAX_SEGMENTS:
                raise ValidationError("训练视频分段数量超过限制")
            if total_size_bytes + actual_size_bytes > settings.TRAINING_VIDEO_MAX_SIZE_BYTES:
                raise ValidationError("训练视频总大小超过限制")
            if (
                total_duration_ms + duration_ms
                > settings.TRAINING_VIDEO_MAX_DURATION_SECONDS * 1000
            ):
                raise ValidationError("训练视频总时长超过限制")

            destination = segment_path(video, index)
            os.replace(temporary, destination)
            destination_was_installed = True
            relative_path = destination.relative_to(
                Path(settings.TRAINING_VIDEO_STAGING_ROOT).resolve()
            ).as_posix()
            segment = TrainingVideoSegment.objects.create(
                training_video=video,
                index=index,
                duration_ms=duration_ms,
                size_bytes=actual_size_bytes,
                sha256=sha256,
                relative_path=relative_path,
                status=TrainingVideoSegment.Status.UPLOADED,
                uploaded_at=timezone.now(),
            )
            video.status = TrainingVideo.Status.UPLOADING_SEGMENTS
            video.uploaded_segment_count = segment_count + 1
            video.save(
                update_fields=["status", "uploaded_segment_count", "updated_at"]
            )
            return segment, True
    except Exception:
        if destination_was_installed:
            destination.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def training_video_session_status(*, project_patient, video_id):
    video = (
        TrainingVideo.objects.select_related("training_record")
        .filter(pk=video_id, project_patient=project_patient)
        .first()
    )
    if video is None:
        raise Http404
    uploaded_segments = list(
        video.segments.filter(status=TrainingVideoSegment.Status.UPLOADED)
        .order_by("index")
        .values_list("index", flat=True)
    )
    try:
        processing_stage = video.assembly_job.status
    except VideoAssemblyJob.DoesNotExist:
        processing_stage = None
    return {
        "video_id": video.id,
        "client_session_id": str(video.client_session_id),
        "status": video.status,
        "uploaded_segments": uploaded_segments,
        "uploaded_segment_count": len(uploaded_segments),
        "expected_duration_seconds": video.expected_duration_seconds,
        "processing_stage": processing_stage,
        "training_record_id": video.training_record_id,
        "failure_reason": video.failure_reason,
        "retryable": video.status
        in {
            TrainingVideo.Status.RECORDING,
            TrainingVideo.Status.UPLOADING_SEGMENTS,
        },
    }


def get_training_video_for_user(user, video_id):
    from .tracking import accessible_project_patients

    video = (
        TrainingVideo.objects.select_related(
            "project_patient",
            "training_record",
            "prescription_action__action_library_item",
        )
        .filter(
            pk=video_id,
            project_patient__in=accessible_project_patients(user),
        )
        .first()
    )
    if video is None:
        raise Http404
    return video


def create_private_download_url(video):
    if video.status != TrainingVideo.Status.ATTACHED or not video.training_record_id:
        raise ValidationError("训练视频尚未绑定训练记录")
    if not all(
        [
            settings.QINIU_ACCESS_KEY,
            settings.QINIU_SECRET_KEY,
            settings.QINIU_DOWNLOAD_DOMAIN,
        ]
    ):
        raise ValidationError("七牛下载配置不完整")
    expires_at = timezone.now() + timedelta(
        seconds=settings.QINIU_DOWNLOAD_TOKEN_TTL_SECONDS
    )
    base_url = f"{settings.QINIU_DOWNLOAD_DOMAIN.rstrip('/')}/{video.object_key}"
    return private_download_url(base_url, expires_at=int(expires_at.timestamp()))


@transaction.atomic
def create_analysis_job(*, video, requested_by):
    locked_video = (
        TrainingVideo.objects.select_for_update(of=("self",))
        .select_related(
            "training_record",
            "prescription_action__action_library_item",
        )
        .get(pk=video.pk)
    )
    if (
        locked_video.status != TrainingVideo.Status.ATTACHED
        or not locked_video.training_record_id
    ):
        raise ValidationError("训练视频尚未绑定训练记录")
    if (
        locked_video.prescription_action.action_library_item.source_key
        != SHOULDER_PRESS_SOURCE_KEY
    ):
        raise ValidationError("当前仅支持肩部推举动作分析")
    if MotionAnalysisJob.objects.filter(
        training_video=locked_video,
        status__in=[MotionAnalysisJob.Status.PENDING, MotionAnalysisJob.Status.RUNNING],
    ).exists():
        raise ValidationError("已有进行中的分析任务")

    try:
        with transaction.atomic():
            job = MotionAnalysisJob.objects.create(
                training_video=locked_video,
                training_record=locked_video.training_record,
                project_patient=locked_video.project_patient,
                prescription_action=locked_video.prescription_action,
                requested_by=requested_by,
            )
    except IntegrityError as exc:
        raise ValidationError("已有进行中的分析任务") from exc

    from .tasks import run_motion_analysis_job

    transaction.on_commit(lambda: run_motion_analysis_job.delay(job.id))
    return job
