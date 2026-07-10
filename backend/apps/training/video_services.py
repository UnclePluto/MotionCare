import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.prescriptions.models import Prescription, PrescriptionAction

from .models import TrainingRecord, TrainingVideo
from .qiniu import generate_upload_token
from .services import create_training_record

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


def _upload_configuration():
    configuration = {
        "access_key": settings.QINIU_ACCESS_KEY,
        "secret_key": settings.QINIU_SECRET_KEY,
        "bucket": settings.QINIU_BUCKET,
        "upload_host": settings.QINIU_UPLOAD_HOST,
    }
    if not all(configuration.values()):
        raise ValidationError("七牛配置不完整，无法生成上传凭证")
    return configuration


def _object_key(project_patient_id):
    today = timezone.localdate()
    return (
        f"training-videos/{project_patient_id}/"
        f"{today:%Y/%m/%d}/{uuid.uuid4().hex}.mp4"
    )


@transaction.atomic
def create_upload_intent(
    *, project_patient, prescription_action_id, content_type, size_bytes, duration_seconds
):
    if size_bytes > settings.TRAINING_VIDEO_MAX_SIZE_BYTES:
        raise ValidationError("训练视频文件过大")
    if duration_seconds > settings.TRAINING_VIDEO_MAX_DURATION_SECONDS:
        raise ValidationError("训练视频时长超过限制")
    active, action = _get_current_shoulder_action(project_patient, prescription_action_id)
    configuration = _upload_configuration()
    expires_at = timezone.now() + timedelta(seconds=settings.QINIU_UPLOAD_TOKEN_TTL_SECONDS)
    key = _object_key(project_patient.id)
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active,
        prescription_action=action,
        bucket=configuration["bucket"],
        object_key=key,
        content_type=content_type,
        size_bytes=size_bytes,
        duration_seconds=duration_seconds,
        upload_token_expires_at=expires_at,
    )
    token = generate_upload_token(
        bucket=configuration["bucket"],
        key=key,
        expires_at=int(expires_at.timestamp()),
    )
    return {
        "video_id": video.id,
        "bucket": video.bucket,
        "key": video.object_key,
        "upload_token": token,
        "upload_host": configuration["upload_host"],
        "expires_at": expires_at.isoformat(),
    }


@transaction.atomic
def complete_training_video(
    *,
    project_patient,
    video_id,
    key,
    object_hash,
    training_date,
    actual_duration_minutes,
    note="",
):
    video = (
        TrainingVideo.objects.select_for_update(of=("self",))
        .select_related("prescription_action", "training_record")
        .filter(pk=video_id, project_patient=project_patient)
        .first()
    )
    if video is None:
        raise ValidationError("训练视频不存在")
    if video.object_key != key:
        raise ValidationError("训练视频对象不匹配")
    if not object_hash or not object_hash.strip():
        raise ValidationError("训练视频 Hash 不能为空")

    active, action = _get_current_shoulder_action(
        project_patient, video.prescription_action_id
    )
    if video.training_record_id:
        return video, False

    record = create_training_record(
        project_patient=project_patient,
        prescription_action=action,
        training_date=training_date,
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=actual_duration_minutes,
        form_data={"video_id": video.id, "video_object_key": video.object_key},
        note=note,
    )
    video.prescription = active
    video.object_hash = object_hash
    video.status = TrainingVideo.Status.ATTACHED
    video.uploaded_at = timezone.now()
    video.training_record = record
    video.save(
        update_fields=[
            "prescription",
            "object_hash",
            "status",
            "uploaded_at",
            "training_record",
            "updated_at",
        ]
    )
    return video, True
