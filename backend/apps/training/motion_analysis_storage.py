import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.utils import timezone
from motion_analysis_contract import (
    ContractValidationError,
    DownloadGrant,
    SkeletonArtifact,
    UploadGrant,
)
import qiniu
from qiniu import Auth

from .qiniu import (
    create_private_object_download_url,
    stat_object_metadata,
    validate_object_metadata,
)
from .video_models import MotionAnalysisJob, QiniuCleanupTombstone, TrainingVideo


SKELETON_CONTENT_TYPE = "video/mp4"
_QINIU_ETAG_PATTERN = re.compile(r"\A[A-Za-z0-9_-]{28}\Z")


@dataclass(frozen=True, repr=False)
class AnalysisStorageGrant:
    download: DownloadGrant
    upload: UploadGrant

    def __repr__(self) -> str:
        return (
            "AnalysisStorageGrant("
            f"download=DownloadGrant(bucket={self.download.bucket!r}, "
            f"object_key={self.download.object_key!r}, download_url=<redacted>), "
            f"upload=UploadGrant(bucket={self.upload.bucket!r}, "
            f"object_key={self.upload.object_key!r}, upload_credential=<redacted>))"
        )


def build_skeleton_object_key(video: TrainingVideo) -> str:
    return (
        f"motion-analysis/{video.project_patient_id}/"
        f"{video.training_date:%Y/%m}/{uuid.uuid4()}/skeleton.mp4"
    )


def issue_storage_grant(job: MotionAnalysisJob, now) -> AnalysisStorageGrant:
    validate_skeleton_destination(job)
    download_expires_at = now + timedelta(seconds=settings.PP_MCARE_DOWNLOAD_TOKEN_TTL_SECONDS)
    upload_expires_at = now + timedelta(seconds=settings.PP_MCARE_UPLOAD_TOKEN_TTL_SECONDS)
    video = job.training_video
    upload_token = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY).upload_token(
        job.skeleton_bucket,
        job.skeleton_object_key,
        settings.PP_MCARE_UPLOAD_TOKEN_TTL_SECONDS,
        policy={"insertOnly": 1},
    )
    return AnalysisStorageGrant(
        download=DownloadGrant(
            url=create_private_object_download_url(
                object_key=video.object_key,
                expires_at=download_expires_at,
            ),
            bucket=video.bucket,
            object_key=video.object_key,
            object_hash=video.object_hash,
            expires_at=download_expires_at.isoformat(),
            size_bytes=video.size_bytes,
            content_type=video.content_type,
        ),
        upload=UploadGrant(
            bucket=job.skeleton_bucket,
            object_key=job.skeleton_object_key,
            token=upload_token,
            expires_at=upload_expires_at.isoformat(),
        ),
    )


def validate_skeleton_destination(job: MotionAnalysisJob) -> None:
    bucket = job.skeleton_bucket
    key = job.skeleton_object_key
    if not isinstance(bucket, str) or not bucket.strip() or bucket != settings.QINIU_BUCKET:
        raise ValidationError("骨架对象空间无效")
    if not isinstance(key, str) or not key:
        raise ValidationError("骨架对象 Key 无效")

    expected_prefix = (
        f"motion-analysis/{job.project_patient_id}/{job.training_video.training_date:%Y/%m}/"
    )
    if not key.startswith(expected_prefix) or not key.endswith("/skeleton.mp4"):
        raise ValidationError("骨架对象 Key 不在任务预分配目录内")
    directory = key.removeprefix(expected_prefix).removesuffix("/skeleton.mp4")
    try:
        if "/" in directory or not directory or uuid.UUID(directory).version != 4:
            raise ValueError
    except (AttributeError, ValueError) as exc:
        raise ValidationError("骨架对象 Key 不在任务预分配目录内") from exc


def validate_published_skeleton_metadata(job: MotionAnalysisJob | None) -> None:
    if job is None or job.status != MotionAnalysisJob.Status.SUCCEEDED:
        raise ValidationError("骨架视频不可用")
    validate_skeleton_destination(job)
    if not isinstance(job.skeleton_object_hash, str) or not _QINIU_ETAG_PATTERN.fullmatch(
        job.skeleton_object_hash
    ):
        raise ValidationError("骨架对象 Hash 无效")
    try:
        SkeletonArtifact(
            bucket=job.skeleton_bucket,
            object_key=job.skeleton_object_key,
            object_hash=job.skeleton_object_hash,
            size_bytes=job.skeleton_size_bytes,
            duration_seconds=job.skeleton_duration_seconds,
            width=job.skeleton_width,
            height=job.skeleton_height,
            fps=job.skeleton_fps,
            # 完成登记已校验远端对象类型；签发阶段只复核持久化元数据与固定文件 scope。
            content_type=SKELETON_CONTENT_TYPE,
        )
    except (ContractValidationError, TypeError) as exc:
        raise ValidationError("骨架对象元数据无效") from exc


def verify_skeleton_upload(job: MotionAnalysisJob, metadata: Mapping[str, object]) -> dict:
    if metadata.get("bucket") != job.skeleton_bucket:
        raise ValidationError("骨架对象空间不匹配")
    if metadata.get("object_key") != job.skeleton_object_key:
        raise ValidationError("骨架对象 Key 不匹配")

    expected_hash = metadata.get("object_hash")
    expected_size_bytes = metadata.get("size_bytes")
    expected_content_type = metadata.get("content_type")
    if not isinstance(expected_hash, str) or not expected_hash:
        raise ValidationError("骨架对象 Hash 无效")
    if (
        isinstance(expected_size_bytes, bool)
        or not isinstance(expected_size_bytes, int)
        or expected_size_bytes < 0
    ):
        raise ValidationError("骨架对象大小无效")
    if expected_content_type != "video/mp4":
        raise ValidationError("骨架对象类型不匹配")

    timeout_seconds = settings.PP_MCARE_OBJECT_STAT_TIMEOUT_SECONDS
    retry_count = settings.PP_MCARE_OBJECT_STAT_RETRIES
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or timeout_seconds <= 0
        or isinstance(retry_count, bool)
        or not isinstance(retry_count, int)
        or retry_count <= 0
    ):
        raise ImproperlyConfigured("pp-mcare 七牛对象查询配置无效")
    qiniu.config.set_default(
        connection_timeout=timeout_seconds,
        connection_retries=retry_count,
    )
    remote_metadata = stat_object_metadata(
        bucket=job.skeleton_bucket,
        key=job.skeleton_object_key,
    )
    validate_object_metadata(
        remote_metadata,
        expected_hash=expected_hash,
        expected_size_bytes=expected_size_bytes,
        expected_content_type="video/mp4",
    )
    return remote_metadata


def _skeleton_directory_prefix(job: MotionAnalysisJob) -> str:
    directory, separator, filename = job.skeleton_object_key.rpartition("/")
    if not separator or not directory or filename != "skeleton.mp4":
        raise ValidationError("骨架对象 Key 无效")
    return f"{directory}/"


@transaction.atomic
def queue_skeleton_cleanup(job: MotionAnalysisJob) -> QiniuCleanupTombstone:
    if not job.skeleton_bucket or not job.skeleton_object_key:
        raise ValidationError("骨架对象清理信息不完整")

    prefix = _skeleton_directory_prefix(job)
    now = timezone.now()
    tombstone, created = QiniuCleanupTombstone.objects.get_or_create(
        attempt_key_prefix=prefix,
        defaults={
            "session_id": job.training_video.client_session_id,
            "bucket": job.skeleton_bucket,
            "max_attempt_number": 0,
            "canonical_key": job.skeleton_object_key,
            "retain_canonical": False,
            "next_check_at": now,
        },
    )
    if created:
        return tombstone

    tombstone = QiniuCleanupTombstone.objects.select_for_update().get(pk=tombstone.pk)
    tombstone.session_id = job.training_video.client_session_id
    tombstone.bucket = job.skeleton_bucket
    tombstone.max_attempt_number = 0
    tombstone.canonical_key = job.skeleton_object_key
    tombstone.retain_canonical = False
    tombstone.next_check_at = min(tombstone.next_check_at, now)
    tombstone.archived_at = None
    tombstone.save(
        update_fields=[
            "session_id",
            "bucket",
            "max_attempt_number",
            "canonical_key",
            "retain_canonical",
            "next_check_at",
            "archived_at",
            "updated_at",
        ]
    )
    return tombstone
