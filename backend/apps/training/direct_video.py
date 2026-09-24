"""计数组完整录像授权；文件由患者端直传七牛，不进入分片暂存。"""
from datetime import timedelta
import math
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from qiniu import Auth

from apps.studies.models import ProjectPatient
from .models import TrainingVideo
from .set_models import MotionSetAttempt
from . import qiniu

MAX_DURATION_MS = 300000
DURATION_TOLERANCE_SECONDS = 5


def _configuration():
    url = settings.QINIU_DIRECT_UPLOAD_URL
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or parsed.query or parsed.fragment or parsed.path not in {"", "/"}
        or not settings.QINIU_ACCESS_KEY or not settings.QINIU_SECRET_KEY or not settings.QINIU_BUCKET
    ):
        raise ValidationError("整组视频直传配置未就绪，请联系管理员")
    return url.rstrip("/")


def _owned_attempt(pp, attempt_id):
    attempt = MotionSetAttempt.objects.select_related("group__session__prescription_action__prescription").filter(
        pk=attempt_id, group__session__project_patient=pp,
    ).first()
    if attempt is None:
        raise Http404
    group = attempt.group
    if attempt.abandoned_at or group.attempt_id != attempt.id or not group.completed:
        raise ValidationError("本组尚未完成或录像尝试已放弃")
    return attempt


def _validate_duration(group, duration_ms):
    elapsed = (group.ended_at - group.started_at).total_seconds()
    if not 0 < elapsed <= 300 or abs(elapsed - duration_ms / 1000) > DURATION_TOLERANCE_SECONDS:
        raise ValidationError("录像时长与本组起止时间不符")


def _response(video):
    return {"video_id": video.id, "status": video.status}


@transaction.atomic
def grant_direct_upload(*, project_patient, client_session_id, motion_attempt_id, size_bytes, duration_ms):
    upload_url = _configuration()
    pp = ProjectPatient.objects.select_for_update().filter(pk=project_patient.pk).first()
    if pp is None:
        raise Http404
    attempt = _owned_attempt(pp, motion_attempt_id)
    group = attempt.group
    _validate_duration(group, duration_ms)
    video = TrainingVideo.objects.select_for_update().filter(
        project_patient=pp, client_session_id=client_session_id,
    ).first()
    if video and (video.motion_attempt_id != attempt.id or video.upload_mode != "direct"):
        raise ValidationError("上传标识与原录像冲突")
    if not video:
        video = TrainingVideo.objects.select_for_update().filter(
            motion_attempt=attempt, upload_mode="direct", cleanup_requested_at__isnull=True,
        ).exclude(status__in=["expired", "failed"]).first()
    created = video is None
    if video:
        if video.cleanup_requested_at or video.status in {"expired", "failed"}:
            raise ValidationError("该上传已失效，请重新取得上传授权")
        if video.size_bytes != size_bytes or video.actual_duration_seconds != max(1, round(duration_ms / 1000)):
            raise ValidationError("上传文件与原始声明冲突")
        if video.status == "attached":
            return _response(video), False
    else:
        if group.video_id:
            raise ValidationError("本组已有正式视频")
        action = group.session.prescription_action
        video = TrainingVideo.objects.create(
            project_patient=pp, client_session_id=client_session_id, motion_attempt=attempt,
            prescription=action.prescription, prescription_action=action,
            training_date=group.session.training_date, training_started_at=group.started_at,
            training_ended_at=group.ended_at, expected_duration_seconds=300,
            actual_duration_seconds=max(1, round(duration_ms / 1000)),
            size_bytes=size_bytes, bucket=settings.QINIU_BUCKET,
            upload_mode="direct", status=TrainingVideo.Status.RECORDING,
        )
        video.object_key = f"training-videos/direct/{video.id}-{video.client_session_id}.mp4"
    ttl = settings.QINIU_DIRECT_UPLOAD_TOKEN_TTL_SECONDS
    video.direct_upload_expires_at = timezone.now() + timedelta(seconds=ttl)
    video.save(update_fields=["object_key", "direct_upload_expires_at", "updated_at"])
    token = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY).upload_token(
        video.bucket, video.object_key, ttl,
        policy={"insertOnly": 1, "detectMime": 1, "mimeLimit": "video/mp4;video/quicktime",
                "fsizeMin": video.size_bytes, "fsizeLimit": video.size_bytes},
    )
    return {**_response(video), "upload_url": upload_url, "upload_token": token,
            "object_key": video.object_key, "expires_at": video.direct_upload_expires_at.isoformat()}, created


def _owned_video(pp, video_id, *, lock=False, allow_inactive=False):
    query = TrainingVideo.objects.select_related("prescription_action__action_library_item")
    if lock:
        query = query.select_for_update(of=("self",))
    video = query.filter(pk=video_id, project_patient=pp, upload_mode="direct").first()
    if video is None:
        raise Http404
    if video.cleanup_requested_at or (not allow_inactive and video.status in {"failed", "expired"}):
        raise ValidationError("该录像已失效，无法登记上传")
    _owned_attempt(pp, video.motion_attempt_id)
    return video


def verify_direct_video(*, project_patient, video_id):
    video = _owned_video(project_patient, video_id, allow_inactive=True)
    if video.status in {"attached", "failed", "expired"}:
        return _response(video)
    metadata = qiniu.stat_object_metadata_or_none(bucket=video.bucket, key=video.object_key)
    if metadata is None:
        return _response(video)
    content_type = str(metadata.get("mimeType", "")).split(";", 1)[0].lower()
    if (metadata.get("fsize") != video.size_bytes or content_type not in qiniu.ALLOWED_VIDEO_CONTENT_TYPES
            or not re.fullmatch(r"[A-Za-z0-9_-]{28}", str(metadata.get("hash", "")))):
        raise ValidationError("云端录像大小、类型或完整性不符合声明")
    media = qiniu.read_private_video_info(video.object_key)
    try:
        duration = float(media["format"]["duration"])
        size = int(media["format"]["size"])
        stream = next(s for s in media["streams"] if s.get("codec_type") == "video")
        if (not math.isfinite(duration) or not 0 < duration <= 305
                or abs(duration - video.actual_duration_seconds) > DURATION_TOLERANCE_SECONDS
                or size != video.size_bytes or int(stream["width"]) <= 0 or int(stream["height"]) <= 0
                or stream.get("codec_name") not in {"h264", "hevc"}):
            raise ValueError
    except (KeyError, TypeError, ValueError, StopIteration, OverflowError):
        raise ValidationError("云端录像不是有效的本组视频，无法确认上传") from None
    with transaction.atomic():
        pp = ProjectPatient.objects.select_for_update().filter(pk=project_patient.pk).first()
        if pp is None:
            raise Http404
        locked = _owned_video(pp, video_id, lock=True)
        if locked.status == "attached":
            return _response(locked)
        if (locked.object_key, locked.bucket, locked.size_bytes, locked.actual_duration_seconds) != (
            video.object_key, video.bucket, video.size_bytes, video.actual_duration_seconds
        ):
            raise ValidationError("录像信息已变化，请重新确认")
        from .video_attachment import attach_verified_video
        locked.duration_seconds = max(1, round(duration))
        locked.content_type = content_type
        locked.finalized_at = timezone.now()
        locked.save(update_fields=["duration_seconds", "content_type", "finalized_at", "updated_at"])
        attach_verified_video(locked, metadata, object_key=locked.object_key)
        return _response(locked)
