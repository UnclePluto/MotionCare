import math
import os
from datetime import timedelta
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.studies.models import ProjectPatient

from .models import TrainingRecord, TrainingVideo, TrainingVideoSegment, VideoAssemblyJob
from .qiniu import upload_local_video
from .video_assembly import AssemblyResult, assemble_video, probe_video


MAX_ASSEMBLY_ATTEMPTS = 3
MAX_CLEANUP_ATTEMPTS = 3
RETRY_BASE_SECONDS = 60


def _safe_video_failure_reason(stage, exc):
    # Delay this import so tasks.py can explicitly register this module.
    from .tasks import _safe_failure_reason

    return _safe_failure_reason(stage, exc)


def _session_root(video):
    staging_root = Path(settings.TRAINING_VIDEO_STAGING_ROOT).resolve()
    root = staging_root / f"{video.id}-{video.client_session_id.hex}"
    if root.is_symlink() or not root.is_relative_to(staging_root):
        raise ValidationError("训练视频临时目录无效")
    return root


def _safe_staging_relative_path(video, relative_path):
    if not relative_path:
        raise ValidationError("训练视频临时路径无效")

    relative = Path(relative_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValidationError("训练视频临时路径无效")

    staging_root = Path(settings.TRAINING_VIDEO_STAGING_ROOT).resolve()
    root = _session_root(video)
    candidate = staging_root.joinpath(*relative.parts)
    if not candidate.is_relative_to(root):
        raise ValidationError("训练视频临时路径无效")

    current = staging_root
    for part in relative.parts:
        if current.is_symlink():
            raise ValidationError("训练视频临时路径包含符号链接")
        current = current / part
    if current.is_symlink() or not current.resolve(strict=False).is_relative_to(root.resolve()):
        raise ValidationError("训练视频临时路径包含符号链接")
    return candidate


def assembly_output_path(video):
    return _session_root(video) / "working" / "final.mp4"


def absolute_staging_path(video, relative_path):
    return _safe_staging_relative_path(video, relative_path)


def _relative_staging_path(video, path):
    root = _session_root(video)
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not path.is_relative_to(root):
        raise ValidationError("训练视频最终文件无效")
    return path.relative_to(Path(settings.TRAINING_VIDEO_STAGING_ROOT).resolve()).as_posix()


def _touch_heartbeat(job_id):
    now = timezone.now()
    VideoAssemblyJob.objects.filter(
        pk=job_id,
        status=VideoAssemblyJob.Status.RUNNING,
    ).update(heartbeat_at=now, updated_at=now)


@transaction.atomic
def claim_video_assembly_job(job_id):
    job = VideoAssemblyJob.objects.select_for_update().select_related("training_video").get(
        pk=job_id
    )
    video = TrainingVideo.objects.select_for_update().get(pk=job.training_video_id)
    if (
        job.status != VideoAssemblyJob.Status.PENDING
        or video.status == TrainingVideo.Status.ATTACHED
    ):
        return job, False

    now = timezone.now()
    job.status = VideoAssemblyJob.Status.RUNNING
    job.attempt_count += 1
    job.started_at = now
    job.finished_at = None
    job.failure_reason = ""
    job.heartbeat_at = now
    job.save(
        update_fields=[
            "status",
            "attempt_count",
            "started_at",
            "finished_at",
            "failure_reason",
            "heartbeat_at",
            "updated_at",
        ]
    )
    video.status = TrainingVideo.Status.ASSEMBLING
    video.failure_reason = ""
    video.save(update_fields=["status", "failure_reason", "updated_at"])
    return job, True


def load_verified_assembly_output(job):
    if not job.output_relative_path:
        return None

    try:
        output_path = absolute_staging_path(job.training_video, job.output_relative_path)
    except ValidationError:
        return None
    if output_path.is_symlink() or not output_path.is_file():
        return None

    _touch_heartbeat(job.id)
    try:
        probe = probe_video(
            output_path,
            ffprobe_path=settings.FFPROBE_PATH,
            timeout=settings.VIDEO_ASSEMBLY_TIMEOUT_SECONDS,
        )
    except ValidationError:
        return None
    finally:
        _touch_heartbeat(job.id)

    video = job.training_video
    if (
        output_path.stat().st_size != video.size_bytes
        or math.ceil(probe.duration_seconds) != video.duration_seconds
    ):
        return None
    return AssemblyResult(
        output_path=output_path,
        probe=probe,
        size_bytes=video.size_bytes,
        transcoded=False,
    )


@transaction.atomic
def mark_uploading_qiniu(job_id, result):
    job = VideoAssemblyJob.objects.select_for_update().select_related("training_video").get(
        pk=job_id
    )
    video = TrainingVideo.objects.select_for_update().get(pk=job.training_video_id)
    if job.status != VideoAssemblyJob.Status.RUNNING:
        raise ValidationError("训练视频合并任务当前不可上传")

    now = timezone.now()
    job.output_relative_path = _relative_staging_path(video, result.output_path)
    job.heartbeat_at = now
    job.save(update_fields=["output_relative_path", "heartbeat_at", "updated_at"])
    video.status = TrainingVideo.Status.UPLOADING_QINIU
    video.size_bytes = result.size_bytes
    video.duration_seconds = max(1, math.ceil(result.probe.duration_seconds))
    video.content_type = "video/mp4"
    video.save(
        update_fields=[
            "status",
            "size_bytes",
            "duration_seconds",
            "content_type",
            "updated_at",
        ]
    )
    return job


@transaction.atomic
def attach_training_video(job_id, result, metadata):
    initial_job = VideoAssemblyJob.objects.select_related("training_video").get(pk=job_id)
    project_patient = ProjectPatient.objects.select_for_update().get(
        pk=initial_job.training_video.project_patient_id
    )
    video = TrainingVideo.objects.select_for_update().get(pk=initial_job.training_video_id)
    job = VideoAssemblyJob.objects.select_for_update().get(pk=job_id)
    if video.status == TrainingVideo.Status.ATTACHED and video.training_record_id:
        return job
    if job.status != VideoAssemblyJob.Status.RUNNING:
        raise ValidationError("训练视频合并任务当前不可绑定")

    object_hash = metadata.get("hash")
    object_size = metadata.get("fsize")
    if not isinstance(object_hash, str) or object_size != result.size_bytes:
        raise ValidationError("七牛训练视频对象元数据无效")

    actual_duration_seconds = video.actual_duration_seconds
    if actual_duration_seconds is None:
        raise ValidationError("训练视频实际时长缺失")

    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=video.prescription,
        prescription_action=video.prescription_action,
        training_date=video.training_date,
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=max(1, math.ceil(actual_duration_seconds / 60)),
        form_data={
            "video_id": video.id,
            "video_object_key": job.qiniu_object_key,
        },
        note=video.note,
    )
    now = timezone.now()
    video.training_record = record
    video.status = TrainingVideo.Status.ATTACHED
    video.bucket = settings.QINIU_BUCKET
    video.object_key = job.qiniu_object_key
    video.object_hash = object_hash
    video.uploaded_at = now
    video.failure_reason = ""
    video.save(
        update_fields=[
            "training_record",
            "status",
            "bucket",
            "object_key",
            "object_hash",
            "uploaded_at",
            "failure_reason",
            "updated_at",
        ]
    )
    job.status = VideoAssemblyJob.Status.SUCCEEDED
    job.qiniu_object_hash = object_hash
    job.failure_reason = ""
    job.finished_at = now
    job.heartbeat_at = now
    job.save(
        update_fields=[
            "status",
            "qiniu_object_hash",
            "failure_reason",
            "finished_at",
            "heartbeat_at",
            "updated_at",
        ]
    )
    transaction.on_commit(lambda job_id=job.id: cleanup_training_video_files.delay(job_id))
    return job


def process_video_assembly_job(job_id):
    job, claimed = claim_video_assembly_job(job_id)
    if not claimed:
        return job

    video = job.training_video
    segments = list(
        video.segments.filter(status=TrainingVideoSegment.Status.UPLOADED).order_by("index")
    )
    _touch_heartbeat(job.id)
    result = load_verified_assembly_output(job)
    _touch_heartbeat(job.id)
    if result is None:
        _touch_heartbeat(job.id)
        try:
            result = assemble_video(
                [absolute_staging_path(video, segment.relative_path) for segment in segments],
                assembly_output_path(video),
                ffmpeg_path=settings.FFMPEG_PATH,
                ffprobe_path=settings.FFPROBE_PATH,
                timeout=settings.VIDEO_ASSEMBLY_TIMEOUT_SECONDS,
            )
        finally:
            _touch_heartbeat(job.id)

    mark_uploading_qiniu(job.id, result)
    _touch_heartbeat(job.id)
    try:
        metadata = upload_local_video(
            path=result.output_path,
            bucket=settings.QINIU_BUCKET,
            key=job.qiniu_object_key,
        )
    finally:
        _touch_heartbeat(job.id)
    return attach_training_video(job.id, result, metadata)


@transaction.atomic
def _record_assembly_failure(job_id, reason):
    job = VideoAssemblyJob.objects.select_for_update().select_related("training_video").get(
        pk=job_id
    )
    video = TrainingVideo.objects.select_for_update().get(pk=job.training_video_id)
    if job.status == VideoAssemblyJob.Status.SUCCEEDED:
        return job, False

    retryable = job.attempt_count < MAX_ASSEMBLY_ATTEMPTS
    now = timezone.now()
    job.status = VideoAssemblyJob.Status.PENDING if retryable else VideoAssemblyJob.Status.FAILED
    job.failure_reason = reason
    job.finished_at = None if retryable else now
    job.heartbeat_at = now
    job.save(
        update_fields=[
            "status",
            "failure_reason",
            "finished_at",
            "heartbeat_at",
            "updated_at",
        ]
    )
    video.status = TrainingVideo.Status.QUEUED if retryable else TrainingVideo.Status.FAILED
    video.failure_reason = reason
    video.save(update_fields=["status", "failure_reason", "updated_at"])
    return job, retryable


@shared_task(bind=True, max_retries=MAX_ASSEMBLY_ATTEMPTS - 1)
def run_video_assembly_job(self, job_id):
    try:
        return process_video_assembly_job(job_id)
    except VideoAssemblyJob.DoesNotExist:
        return None
    except Exception as exc:
        try:
            job, retryable = _record_assembly_failure(
                job_id,
                _safe_video_failure_reason("视频合并上传", exc),
            )
        except VideoAssemblyJob.DoesNotExist:
            return None
        if retryable:
            return self.retry(
                args=[job_id],
                countdown=RETRY_BASE_SECONDS * 2 ** (job.attempt_count - 1),
            )
        return job


def _remove_session_files(video):
    root = _session_root(video)
    if not root.exists():
        return
    if root.is_symlink() or not root.is_dir():
        raise ValidationError("训练视频临时目录无效")

    files = []
    directories = []
    for directory, dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
        current = Path(directory)
        if not current.is_relative_to(root) or current.is_symlink():
            raise ValidationError("训练视频清理路径无效")
        for name in [*dirnames, *filenames]:
            path = current / name
            if not path.is_relative_to(root) or path.is_symlink():
                raise ValidationError("训练视频清理路径包含符号链接")
        files.extend(current / filename for filename in filenames)
        directories.append(current)

    for path in files:
        if path.is_symlink():
            raise ValidationError("训练视频清理路径包含符号链接")
        path.unlink(missing_ok=True)
    for directory in directories:
        if directory.is_symlink():
            raise ValidationError("训练视频清理路径包含符号链接")
        directory.rmdir()


@transaction.atomic
def _claim_cleanup(job_id):
    job = VideoAssemblyJob.objects.select_for_update().select_related("training_video").get(
        pk=job_id
    )
    video = TrainingVideo.objects.select_for_update().get(pk=job.training_video_id)
    if (
        video.status != TrainingVideo.Status.ATTACHED
        or job.cleanup_status == VideoAssemblyJob.CleanupStatus.SUCCEEDED
    ):
        return job, False

    job.cleanup_attempt_count += 1
    job.cleanup_error = ""
    job.save(update_fields=["cleanup_attempt_count", "cleanup_error", "updated_at"])
    return job, True


@transaction.atomic
def _mark_cleanup_succeeded(job_id):
    job = VideoAssemblyJob.objects.select_for_update().select_related("training_video").get(
        pk=job_id
    )
    TrainingVideoSegment.objects.filter(training_video_id=job.training_video_id).update(
        status=TrainingVideoSegment.Status.DELETED,
        updated_at=timezone.now(),
    )
    job.cleanup_status = VideoAssemblyJob.CleanupStatus.SUCCEEDED
    job.cleanup_error = ""
    job.save(update_fields=["cleanup_status", "cleanup_error", "updated_at"])
    return job


@transaction.atomic
def _record_cleanup_failure(job_id, reason):
    job = VideoAssemblyJob.objects.select_for_update().get(pk=job_id)
    retryable = job.cleanup_attempt_count < MAX_CLEANUP_ATTEMPTS
    job.cleanup_status = VideoAssemblyJob.CleanupStatus.FAILED
    job.cleanup_error = reason
    job.save(update_fields=["cleanup_status", "cleanup_error", "updated_at"])
    return job, retryable


@shared_task(bind=True, max_retries=MAX_CLEANUP_ATTEMPTS - 1)
def cleanup_training_video_files(self, job_id):
    try:
        job, claimed = _claim_cleanup(job_id)
    except VideoAssemblyJob.DoesNotExist:
        return None
    if not claimed:
        return job

    try:
        _remove_session_files(job.training_video)
    except Exception as exc:
        job, retryable = _record_cleanup_failure(
            job_id,
            _safe_video_failure_reason("训练视频临时文件清理", exc),
        )
        if retryable:
            return self.retry(
                args=[job_id],
                countdown=RETRY_BASE_SECONDS * 2 ** (job.cleanup_attempt_count - 1),
            )
        return job
    return _mark_cleanup_succeeded(job_id)


def _is_stale_assembly_job(job, cutoff):
    if job.status != VideoAssemblyJob.Status.RUNNING:
        return False
    if job.heartbeat_at is not None:
        return job.heartbeat_at < cutoff
    return job.started_at is not None and job.started_at < cutoff


@shared_task(ignore_result=True)
def recover_stale_video_assembly_jobs():
    cutoff = timezone.now() - timedelta(
        seconds=settings.VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS
    )
    candidate_ids = VideoAssemblyJob.objects.filter(
        status=VideoAssemblyJob.Status.RUNNING
    ).filter(
        Q(heartbeat_at__lt=cutoff)
        | Q(heartbeat_at__isnull=True, started_at__lt=cutoff)
    ).values_list("id", flat=True)
    recovered = 0
    for job_id in candidate_ids:
        with transaction.atomic():
            job = (
                VideoAssemblyJob.objects.select_for_update()
                .select_related("training_video")
                .filter(pk=job_id)
                .first()
            )
            if job is None or not _is_stale_assembly_job(job, cutoff):
                continue
            video = TrainingVideo.objects.select_for_update().get(pk=job.training_video_id)
            now = timezone.now()
            job.status = VideoAssemblyJob.Status.PENDING
            job.heartbeat_at = now
            job.save(update_fields=["status", "heartbeat_at", "updated_at"])
            video.status = TrainingVideo.Status.QUEUED
            video.save(update_fields=["status", "updated_at"])
            transaction.on_commit(
                lambda recovered_job_id=job.id: run_video_assembly_job.delay(
                    recovered_job_id
                )
            )
            recovered += 1
    return recovered


def _is_expirable_video(video, job, cutoff):
    if (
        video.finalized_at is None
        and video.status
        in {TrainingVideo.Status.RECORDING, TrainingVideo.Status.UPLOADING_SEGMENTS}
    ):
        return video.updated_at < cutoff
    if video.status != TrainingVideo.Status.FAILED or video.updated_at >= cutoff:
        return False
    return job is None or (
        job.status == VideoAssemblyJob.Status.FAILED
        and (job.heartbeat_at is None or job.heartbeat_at < cutoff)
    )


@shared_task(ignore_result=True)
def expire_stale_training_video_sessions():
    cutoff = timezone.now() - timedelta(seconds=settings.TRAINING_VIDEO_STAGING_TTL_SECONDS)
    candidate_ids = TrainingVideo.objects.filter(updated_at__lt=cutoff).filter(
        Q(
            finalized_at__isnull=True,
            status__in=[
                TrainingVideo.Status.RECORDING,
                TrainingVideo.Status.UPLOADING_SEGMENTS,
            ],
        )
        | Q(status=TrainingVideo.Status.FAILED)
    ).values_list("id", flat=True)
    expired = 0
    for video_id in candidate_ids:
        with transaction.atomic():
            video = TrainingVideo.objects.select_for_update().filter(pk=video_id).first()
            if video is None:
                continue
            job = VideoAssemblyJob.objects.select_for_update().filter(
                training_video=video
            ).first()
            if not _is_expirable_video(video, job, cutoff):
                continue
            _remove_session_files(video)
            now = timezone.now()
            TrainingVideoSegment.objects.filter(training_video=video).update(
                status=TrainingVideoSegment.Status.DELETED,
                updated_at=now,
            )
            video.status = TrainingVideo.Status.EXPIRED
            video.save(update_fields=["status", "updated_at"])
            if job is not None:
                job.cleanup_status = VideoAssemblyJob.CleanupStatus.SUCCEEDED
                job.cleanup_error = ""
                job.save(update_fields=["cleanup_status", "cleanup_error", "updated_at"])
            expired += 1
    return expired
