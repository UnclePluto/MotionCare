import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient

from apps.training.models import TrainingRecord
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


@pytest.mark.django_db
def test_training_create_ignores_malicious_controlled_foreign_key_ids(
    active_prescription,
    prescription_action,
    doctor,
    project,
    group,
):
    other_patient = Patient.objects.create(
        name="患者乙",
        phone="13900002222",
        primary_doctor=doctor,
    )
    other_project_patient = ProjectPatient.objects.create(
        project=project,
        patient=other_patient,
        group=group,
    )
    other_prescription = Prescription.objects.create(
        project_patient=other_project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    other_action = ActionLibraryItem.objects.create(
        name="错误动作",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="力量训练",
    )
    other_prescription_action = other_prescription.add_action_snapshot(other_action)

    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date="2026-05-06",
        prescription_action=prescription_action,
        status=TrainingRecord.Status.COMPLETED,
        prescription_id=other_prescription.id,
        prescription_action_id=other_prescription_action.id,
        project_patient_id=other_project_patient.id,
    )

    assert record.project_patient == active_prescription.project_patient
    assert record.prescription == active_prescription
    assert record.prescription_action == prescription_action


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["patch", "put"])
def test_training_record_update_methods_are_not_allowed(
    method,
    active_prescription,
    prescription_action,
    doctor,
):
    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date="2026-05-06",
        prescription_action=prescription_action,
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=20,
    )
    client = APIClient()
    client.force_authenticate(user=doctor)

    response = getattr(client, method)(
        f"/api/training/{record.id}/",
        {"prescription_action": 999},
        format="json",
    )

    assert response.status_code == 405
    record.refresh_from_db()
    assert record.project_patient == active_prescription.project_patient
    assert record.prescription == active_prescription
    assert record.prescription_action == prescription_action
