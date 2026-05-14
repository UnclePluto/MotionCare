from django.core.exceptions import ValidationError

from apps.prescriptions.models import Prescription
from apps.studies.project_status import ensure_project_open

from .models import TrainingRecord


def create_training_record(*, project_patient, training_date, prescription_action=None, **fields):
    ensure_project_open(project_patient.project)
    active = (
        Prescription.objects.filter(
            project_patient=project_patient,
            status=Prescription.Status.ACTIVE,
        )
        .order_by("-effective_at", "-id")
        .first()
    )
    if not active:
        raise ValidationError("当前无生效处方，不能录入训练")
    if prescription_action is None:
        raise ValidationError("必须选择当前处方动作")
    if prescription_action.prescription_id != active.id:
        raise ValidationError("只能录入当前生效处方下的动作")
    fields.pop("prescription", None)
    return TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active,
        prescription_action=prescription_action,
        training_date=training_date,
        **fields,
    )
