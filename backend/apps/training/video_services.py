import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from apps.prescriptions.models import Prescription, PrescriptionAction
from apps.studies.models import ProjectPatient

from .models import MotionAnalysisJob, TrainingRecord, TrainingVideo
from .qiniu import (
    generate_upload_token,
    private_download_url,
    stat_object_metadata,
    validate_object_metadata,
)
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
    object_hash = object_hash.strip() if object_hash else ""
    if not object_hash:
        raise ValidationError("训练视频 Hash 不能为空")

    preliminary_video = (
        TrainingVideo.objects.select_related("training_record")
        .filter(pk=video_id, project_patient=project_patient)
        .first()
    )
    if preliminary_video is None:
        raise ValidationError("训练视频不存在")
    if not preliminary_video.training_record_id and preliminary_video.object_key != key:
        raise ValidationError("训练视频对象不匹配")

    metadata = None
    if not preliminary_video.training_record_id:
        metadata = stat_object_metadata(
            bucket=preliminary_video.bucket,
            key=preliminary_video.object_key,
        )

    with transaction.atomic():
        locked_project_patient = (
            ProjectPatient.objects.select_for_update(of=("self",))
            .select_related("project")
            .filter(pk=project_patient.pk)
            .first()
        )
        if locked_project_patient is None:
            raise ValidationError("患者项目绑定不存在")

        video = (
            TrainingVideo.objects.select_for_update(of=("self",))
            .select_related("prescription_action", "training_record")
            .filter(pk=video_id, project_patient=locked_project_patient)
            .first()
        )
        if video is None:
            raise ValidationError("训练视频不存在")

        if video.training_record_id:
            _validate_attached_request(
                video,
                key=key,
                object_hash=object_hash,
                training_date=training_date,
                actual_duration_minutes=actual_duration_minutes,
                note=note,
            )
            return video, False

        if video.object_key != key:
            raise ValidationError("训练视频对象不匹配")
        if metadata is None:
            raise ValidationError("训练视频状态已变化，请重试")
        validate_object_metadata(
            metadata,
            expected_hash=object_hash,
            expected_size_bytes=video.size_bytes,
            expected_content_type=video.content_type,
        )

        active, action = _get_current_shoulder_action(
            locked_project_patient, video.prescription_action_id
        )
        record = create_training_record(
            project_patient=locked_project_patient,
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


def _validate_attached_request(
    video,
    *,
    key,
    object_hash,
    training_date,
    actual_duration_minutes,
    note,
):
    record = video.training_record
    matches = (
        video.object_key == key
        and video.object_hash == object_hash
        and record.training_date == training_date
        and record.actual_duration_minutes == actual_duration_minutes
        and record.note == note
    )
    if not matches:
        raise ValidationError("重复完成请求与已绑定训练记录冲突")


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
