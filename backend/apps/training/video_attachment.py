"""Bind a verified private video after its caller validates ownership and locks the video."""
import math

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from .history import legacy_invalidation_defaults
from .models import TrainingRecord, TrainingVideo


def attach_verified_video(video, metadata, *, object_key):
    if video.status == TrainingVideo.Status.ATTACHED and video.training_record_id:
        return video.training_record
    if video.actual_duration_seconds is None or not video.project_patient_id:
        raise ValidationError("录像归属或实际时长缺失")
    record = TrainingRecord.objects.create(
        project_patient=video.project_patient,
        prescription=video.prescription,
        prescription_action=video.prescription_action,
        training_date=video.training_date,
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=max(1, math.ceil(video.actual_duration_seconds / 60)),
        form_data={"video_id": video.id, "video_object_key": object_key},
        note=video.note,
        **legacy_invalidation_defaults(video.prescription_action),
    )
    video.training_record = record
    video.status = TrainingVideo.Status.ATTACHED
    video.bucket = video.bucket or settings.QINIU_BUCKET
    video.object_key = object_key
    video.object_hash = metadata["hash"]
    video.uploaded_at = timezone.now()
    video.failure_reason = ""
    video.save(update_fields=["training_record", "status", "bucket", "object_key", "object_hash",
                              "uploaded_at", "failure_reason", "updated_at"])
    from .video_tasks import ensure_motion_analysis_job
    from .sets import attach_set_video
    attach_set_video(video)
    ensure_motion_analysis_job(video)
    return record
