import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.prescriptions.models import Prescription

from apps.training.services import create_training_record


@pytest.mark.django_db
def test_training_requires_active_prescription(project_patient):
    with pytest.raises(ValidationError, match="当前无生效处方"):
        create_training_record(project_patient=project_patient, training_date="2026-05-06")


@pytest.mark.django_db
def test_training_uses_current_active_prescription(active_prescription, prescription_action):
    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date="2026-05-06",
        prescription_action=prescription_action,
        status="completed",
        actual_duration_minutes=20,
    )

    assert record.prescription == active_prescription
    assert record.prescription_action == prescription_action
    assert record.status == "completed"


@pytest.mark.django_db
def test_training_rejects_action_from_archived_prescription(
    active_prescription, prescription_action, doctor
):
    newer = Prescription.objects.create(
        project_patient=active_prescription.project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    active_prescription.status = Prescription.Status.ARCHIVED
    active_prescription.save(update_fields=["status"])

    with pytest.raises(ValidationError, match="只能录入当前生效处方下的动作"):
        create_training_record(
            project_patient=active_prescription.project_patient,
            training_date="2026-05-06",
            prescription_action=prescription_action,
            status="completed",
        )

    assert newer.status == Prescription.Status.ACTIVE
