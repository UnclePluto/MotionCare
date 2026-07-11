import math
import stat
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
from .qiniu import delete_object_if_exists, upload_local_video
from .video_assembly import AssemblyResult, assemble_video, probe_video
from .video_staging import (
    SESSION_DIRECTORY_PATTERN,
    ensure_working_directory,
    quarantine_and_remove_session,
    remove_orphan_session_directory,
    remove_quarantined_session_directory,
    session_root,
    staging_directory_entries,
    staging_root,
)


MAX_ASSEMBLY_ATTEMPTS = 3
MAX_CLEANUP_ATTEMPTS = 3
RETRY_BASE_SECONDS = 60


class AssemblyLeaseLost(ValidationError):
    pass


def _safe_video_failure_reason(stage, exc):
    # Delay this import so tasks.py can explicitly register this module.
    from .tasks import _safe_failure_reason

    return _safe_failure_reason(stage, exc)


def _session_root(video):
    return session_root(video)


def _safe_staging_relative_path(video, relative_path):
    if not relative_path:
        raise ValidationError("训练视频临时路径无效")

    relative = Path(relative_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValidationError("训练视频临时路径无效")

    root_path = staging_root()
    root = _session_root(video)
    candidate = root_path.joinpath(*relative.parts)
    if not candidate.is_relative_to(root):
        raise ValidationError("训练视频临时路径无效")

    current = root_path
    for part in relative.parts:
        if current.is_symlink():
            raise ValidationError("训练视频临时路径包含符号链接")
        current = current / part
    if current.is_symlink():
        raise ValidationError("训练视频临时路径包含符号链接")
    return candidate


def assembly_output_path(video):
    return ensure_working_directory(video) / "final.mp4"


def absolute_staging_path(video, relative_path):
    return _safe_staging_relative_path(video, relative_path)


def _relative_staging_path(video, path):
    root = _session_root(video)
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not path.is_relative_to(root):
        raise ValidationError("训练视频最终文件无效")
    return path.relative_to(staging_root()).as_posix()


def _touch_heartbeat(job_id, lease_attempt):
    now = timezone.now()
    updated = VideoAssemblyJob.objects.filter(
        pk=job_id,
        status=VideoAssemblyJob.Status.RUNNING,
        attempt_count=lease_attempt,
        training_video__cleanup_requested_at__isnull=True,
        training_video__project_patient__isnull=False,
    ).update(heartbeat_at=now, updated_at=now)
    if updated != 1:
        raise AssemblyLeaseLost("训练视频合并任务租约已失效")


def _job_training_video_id(job_id):
    return VideoAssemblyJob.objects.only("training_video_id").get(pk=job_id).training_video_id


def _lock_training_video_then_job(job_id):
    training_video_id = _job_training_video_id(job_id)
    video = TrainingVideo.objects.select_for_update().get(pk=training_video_id)
    job = VideoAssemblyJob.objects.select_for_update().get(pk=job_id)
    if job.training_video_id != video.id:
        raise ValidationError("训练视频合并任务状态已变更")
    job.training_video = video
    return video, job


def _lock_project_patient_training_video_then_job(job_id):
    ids = (
        VideoAssemblyJob.objects.filter(pk=job_id)
        .values("training_video_id", "training_video__project_patient_id")
        .get()
    )
    project_patient = ProjectPatient.objects.select_for_update().get(
        pk=ids["training_video__project_patient_id"]
    )
    video = TrainingVideo.objects.select_for_update().get(pk=ids["training_video_id"])
    job = VideoAssemblyJob.objects.select_for_update().get(pk=job_id)
    if video.project_patient_id != project_patient.id or job.training_video_id != video.id:
        raise ValidationError("训练视频合并任务状态已变更")
    video.project_patient = project_patient
    job.training_video = video
    return project_patient, video, job


@transaction.atomic
def claim_video_assembly_job(job_id):
    video, job = _lock_training_video_then_job(job_id)
    if (
        job.status != VideoAssemblyJob.Status.PENDING
        or video.status == TrainingVideo.Status.ATTACHED
        or video.project_patient_id is None
        or video.cleanup_requested_at is not None
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


def load_verified_assembly_output(job, lease_attempt):
    if not job.output_relative_path:
        return None

    try:
        output_path = absolute_staging_path(job.training_video, job.output_relative_path)
    except ValidationError:
        return None
    if output_path.is_symlink() or not output_path.is_file():
        return None

    _touch_heartbeat(job.id, lease_attempt)
    try:
        probe = probe_video(
            output_path,
            ffprobe_path=settings.FFPROBE_PATH,
            timeout=settings.VIDEO_ASSEMBLY_TIMEOUT_SECONDS,
        )
    except ValidationError:
        return None
    finally:
        _touch_heartbeat(job.id, lease_attempt)

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
def mark_uploading_qiniu(job_id, result, *, lease_attempt):
    video, job = _lock_training_video_then_job(job_id)
    if (
        job.status != VideoAssemblyJob.Status.RUNNING
        or job.attempt_count != lease_attempt
        or video.project_patient_id is None
        or video.cleanup_requested_at is not None
    ):
        raise AssemblyLeaseLost("训练视频合并任务租约已失效")

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
def attach_training_video(job_id, result, metadata, *, lease_attempt):
    project_patient, video, job = _lock_project_patient_training_video_then_job(job_id)
    if video.status == TrainingVideo.Status.ATTACHED and video.training_record_id:
        return job
    if (
        job.status != VideoAssemblyJob.Status.RUNNING
        or job.attempt_count != lease_attempt
        or video.cleanup_requested_at is not None
    ):
        raise AssemblyLeaseLost("训练视频合并任务租约已失效")

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

    lease_attempt = job.attempt_count
    try:
        video = job.training_video

        def heartbeat():
            _touch_heartbeat(job.id, lease_attempt)

        segments = list(
            video.segments.filter(status=TrainingVideoSegment.Status.UPLOADED).order_by(
                "index"
            )
        )
        heartbeat()
        result = load_verified_assembly_output(job, lease_attempt)
        heartbeat()
        if result is None:
            result = assemble_video(
                [absolute_staging_path(video, segment.relative_path) for segment in segments],
                assembly_output_path(video),
                ffmpeg_path=settings.FFMPEG_PATH,
                ffprobe_path=settings.FFPROBE_PATH,
                timeout=settings.VIDEO_ASSEMBLY_TIMEOUT_SECONDS,
                on_progress=heartbeat,
            )

        mark_uploading_qiniu(job.id, result, lease_attempt=lease_attempt)
        heartbeat()
        try:
            metadata = upload_local_video(
                path=result.output_path,
                bucket=settings.QINIU_BUCKET,
                key=job.qiniu_object_key,
            )
            heartbeat()
        except AssemblyLeaseLost:
            delete_object_if_exists(bucket=settings.QINIU_BUCKET, key=job.qiniu_object_key)
            raise
        return attach_training_video(
            job.id,
            result,
            metadata,
            lease_attempt=lease_attempt,
        )
    except Exception as exc:
        exc.assembly_lease_attempt = lease_attempt
        raise


@transaction.atomic
def _record_assembly_failure(job_id, reason, *, lease_attempt):
    video, job = _lock_training_video_then_job(job_id)
    if (
        job.status != VideoAssemblyJob.Status.RUNNING
        or job.attempt_count != lease_attempt
    ):
        return job, False

    cleanup_requested = (
        video.cleanup_requested_at is not None or video.project_patient_id is None
    )
    retryable = not cleanup_requested and job.attempt_count < MAX_ASSEMBLY_ATTEMPTS
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
    if cleanup_requested:
        transaction.on_commit(
            lambda video_id=video.id: cleanup_unbound_training_video.delay(video_id)
        )
    return job, retryable


@shared_task(bind=True, max_retries=MAX_ASSEMBLY_ATTEMPTS - 1)
def run_video_assembly_job(self, job_id):
    try:
        return process_video_assembly_job(job_id)
    except VideoAssemblyJob.DoesNotExist:
        return None
    except Exception as exc:
        lease_attempt = getattr(exc, "assembly_lease_attempt", None)
        if lease_attempt is None:
            return None
        try:
            job, retryable = _record_assembly_failure(
                job_id,
                _safe_video_failure_reason("视频合并上传", exc),
                lease_attempt=lease_attempt,
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
    quarantine_and_remove_session(video)


@transaction.atomic
def _claim_unbound_video_cleanup(video_id):
    video = TrainingVideo.objects.select_for_update().filter(pk=video_id).first()
    if (
        video is None
        or video.project_patient_id is not None
        or video.cleanup_requested_at is None
    ):
        return video, None, None, False, False

    job = VideoAssemblyJob.objects.select_for_update().filter(training_video=video).first()
    if job is not None and job.status == VideoAssemblyJob.Status.RUNNING:
        cutoff = timezone.now() - timedelta(
            seconds=settings.VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS
        )
        if not _is_stale_assembly_job(job, cutoff):
            return video, None, None, False, True
        job.status = VideoAssemblyJob.Status.FAILED
        job.failure_reason = "训练视频已解绑，旧合并任务租约失效"
        job.finished_at = timezone.now()
        job.save(
            update_fields=["status", "failure_reason", "finished_at", "updated_at"]
        )

    now = timezone.now()
    video.cleanup_status = TrainingVideo.CleanupStatus.RUNNING
    video.cleanup_attempt_count += 1
    video.cleanup_heartbeat_at = now
    video.cleanup_error = ""
    video.save(
        update_fields=[
            "cleanup_status",
            "cleanup_attempt_count",
            "cleanup_heartbeat_at",
            "cleanup_error",
            "updated_at",
        ]
    )
    object_key = video.object_key or (job.qiniu_object_key if job is not None else "")
    bucket = video.bucket or settings.QINIU_BUCKET
    return video, bucket, object_key, True, False


@transaction.atomic
def _record_unbound_cleanup_failure(video_id, cleanup_attempt, reason):
    video = TrainingVideo.objects.select_for_update().filter(pk=video_id).first()
    if (
        video is None
        or video.cleanup_status != TrainingVideo.CleanupStatus.RUNNING
        or video.cleanup_attempt_count != cleanup_attempt
    ):
        return video, False
    video.cleanup_status = TrainingVideo.CleanupStatus.FAILED
    video.cleanup_error = reason
    video.cleanup_heartbeat_at = timezone.now()
    video.save(
        update_fields=[
            "cleanup_status",
            "cleanup_error",
            "cleanup_heartbeat_at",
            "updated_at",
        ]
    )
    return video, cleanup_attempt < MAX_CLEANUP_ATTEMPTS


@transaction.atomic
def _delete_unbound_cleanup_record(video_id, cleanup_attempt):
    video = TrainingVideo.objects.select_for_update().filter(pk=video_id).first()
    if video is None:
        return True
    if (
        video.project_patient_id is not None
        or video.cleanup_status != TrainingVideo.CleanupStatus.RUNNING
        or video.cleanup_attempt_count != cleanup_attempt
    ):
        return False
    video.delete()
    return True


@shared_task(bind=True, max_retries=MAX_CLEANUP_ATTEMPTS - 1)
def cleanup_unbound_training_video(self, video_id):
    video, bucket, object_key, claimed, busy = _claim_unbound_video_cleanup(video_id)
    if video is None:
        return True
    if busy:
        return self.retry(args=[video_id], countdown=RETRY_BASE_SECONDS)
    if not claimed:
        return False

    cleanup_attempt = video.cleanup_attempt_count
    try:
        if object_key:
            delete_object_if_exists(bucket=bucket, key=object_key)
        _remove_session_files(video)
    except Exception as exc:
        video, retryable = _record_unbound_cleanup_failure(
            video_id,
            cleanup_attempt,
            _safe_video_failure_reason("解绑训练视频清理", exc),
        )
        if retryable:
            return self.retry(
                args=[video_id],
                countdown=RETRY_BASE_SECONDS * 2 ** (cleanup_attempt - 1),
            )
        return False
    return _delete_unbound_cleanup_record(video_id, cleanup_attempt)


@shared_task(ignore_result=True)
def recover_training_video_cleanup():
    cutoff = timezone.now() - timedelta(
        seconds=settings.VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS
    )
    candidate_ids = list(
        TrainingVideo.objects.filter(
            project_patient__isnull=True,
            cleanup_requested_at__isnull=False,
        )
        .filter(
            Q(
                cleanup_status__in=[
                    TrainingVideo.CleanupStatus.PENDING,
                    TrainingVideo.CleanupStatus.FAILED,
                ]
            )
            | Q(
                cleanup_status=TrainingVideo.CleanupStatus.RUNNING,
                cleanup_heartbeat_at__lt=cutoff,
            )
        )
        .values_list("id", flat=True)
    )
    for video_id in candidate_ids:
        transaction.on_commit(
            lambda durable_video_id=video_id: cleanup_unbound_training_video.delay(
                durable_video_id
            )
        )
    return len(candidate_ids)


@transaction.atomic
def _claim_cleanup(job_id):
    video, job = _lock_training_video_then_job(job_id)
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


def _mark_stale_job_failed(job, video, now):
    reason = "视频合并上传任务心跳超时，已达到最大尝试次数"
    job.status = VideoAssemblyJob.Status.FAILED
    job.failure_reason = reason
    job.finished_at = now
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
    video.status = TrainingVideo.Status.FAILED
    video.failure_reason = reason
    video.save(update_fields=["status", "failure_reason", "updated_at"])


@shared_task(ignore_result=True)
def recover_stale_video_assembly_jobs():
    if (
        settings.VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS
        <= settings.VIDEO_ASSEMBLY_TIMEOUT_SECONDS
    ):
        raise ValidationError("视频合并 stale timeout 必须大于整体 assembly timeout")
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
            try:
                video, job = _lock_training_video_then_job(job_id)
            except VideoAssemblyJob.DoesNotExist:
                continue
            if not _is_stale_assembly_job(job, cutoff):
                continue
            now = timezone.now()
            if video.cleanup_requested_at is not None or video.project_patient_id is None:
                job.status = VideoAssemblyJob.Status.FAILED
                job.failure_reason = "训练视频已解绑，旧合并任务租约失效"
                job.finished_at = now
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
                transaction.on_commit(
                    lambda video_id=video.id: cleanup_unbound_training_video.delay(
                        video_id
                    )
                )
                continue
            if job.attempt_count >= MAX_ASSEMBLY_ATTEMPTS:
                _mark_stale_job_failed(job, video, now)
                continue
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


def _remove_expired_orphan_staging(cutoff):
    _, sessions, quarantined = staging_directory_entries()
    cutoff_timestamp = cutoff.timestamp()
    removed = 0
    for path in sessions:
        match = SESSION_DIRECTORY_PATTERN.fullmatch(path.name)
        if match is None:
            continue
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_mtime >= cutoff_timestamp
        ):
            continue
        video_id = int(match.group("video_id"))
        if TrainingVideo.objects.filter(pk=video_id).exists():
            continue
        if remove_orphan_session_directory(path.name):
            removed += 1

    for path in quarantined:
        match = SESSION_DIRECTORY_PATTERN.fullmatch(path.name)
        if match is None:
            continue
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_mtime >= cutoff_timestamp
        ):
            continue
        video = TrainingVideo.objects.filter(pk=int(match.group("video_id"))).first()
        if video is not None and video.cleanup_requested_at is None:
            continue
        if remove_quarantined_session_directory(path.name):
            removed += 1
    return removed


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
    return expired + _remove_expired_orphan_staging(cutoff)
