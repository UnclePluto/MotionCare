"""旧模式运动逻辑作废；原记录、录像和分析结果保留备查。"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.prescriptions.models import MotionPrescriptionCutover
from apps.studies.models import ProjectPatient
from .models import TrainingRecord

LEGACY_MOTION_KEYS = (
    "motion-balance-sit-stand",
    "motion-resistance-row",
    "motion-resistance-leg-kickback",
    "motion-resistance-shoulder-press",
)
INVALIDATION_REASON = "运动处方已切换按组计数，旧模式训练仅保留历史备查"


def legacy_training_records(project_patient):
    return TrainingRecord.objects.filter(
        project_patient=project_patient,
        prescription_action__dose_mode="duration",
        prescription_action__action_library_item__source_key__in=LEGACY_MOTION_KEYS,
    )


def preview_legacy_training(project_patient):
    records = legacy_training_records(project_patient)
    return {
        "project_patient": project_patient.pk,
        "affected_records": records.filter(invalidated_at__isnull=True).count(),
        "already_invalidated_records": records.filter(invalidated_at__isnull=False).count(),
    }


@transaction.atomic
def invalidate_legacy_training(project_patient):
    # 与处方切换、录像发布共用患者项目锁，避免扫描与晚发布互相穿透。
    ProjectPatient.objects.select_for_update().get(pk=project_patient.pk)
    cutover = MotionPrescriptionCutover.objects.filter(project_patient=project_patient).first()
    if cutover is None:
        raise ValidationError("尚无处方切换标记，不能作废旧训练")
    count = (
        legacy_training_records(project_patient)
        .filter(invalidated_at__isnull=True)
        .update(
            invalidated_at=timezone.now(),
            invalidation_reason=INVALIDATION_REASON,
            cutover_marker=cutover.marker,
        )
    )
    return {
        **preview_legacy_training(project_patient),
        "invalidated_records": count,
        "cutover_marker": str(cutover.marker),
    }


def legacy_invalidation_defaults(action):
    if (
        action.dose_mode != "duration"
        or action.action_library_item.source_key not in LEGACY_MOTION_KEYS
    ):
        return {}
    cutover = MotionPrescriptionCutover.objects.filter(
        project_patient_id=action.prescription.project_patient_id
    ).first()
    if cutover is None:
        return {}
    return {
        "invalidated_at": timezone.now(),
        "invalidation_reason": INVALIDATION_REASON,
        "cutover_marker": cutover.marker,
    }
