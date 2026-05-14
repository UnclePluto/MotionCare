import pytest
from django.utils import timezone

from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.prescriptions.services import activate_prescription


@pytest.mark.django_db
def test_activating_new_prescription_archives_existing_active(project_patient, doctor):
    first = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    second = Prescription.objects.create(
        project_patient=project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.DRAFT,
    )

    activate_prescription(second)

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == Prescription.Status.ARCHIVED
    assert first.archived_at is not None
    assert second.status == Prescription.Status.ACTIVE
    assert second.archived_at is None


@pytest.mark.django_db
def test_prescription_action_keeps_snapshot(project_patient, doctor):
    action = ActionLibraryItem.objects.create(
        name="坐立训练",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="平衡训练",
        instruction_text="从椅子坐下后站起。\n\n动作要点：保持躯干稳定。",
    )

    prescription = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
    )
    snapshot = prescription.add_action_snapshot(action, duration_minutes=10)

    action.name = "已修改动作名"
    action.save()

    snapshot.refresh_from_db()
    assert snapshot.action_library_item == action
    assert snapshot.action_name_snapshot == "坐立训练"
    assert snapshot.action_instruction_snapshot == "从椅子坐下后站起。\n\n动作要点：保持躯干稳定。"
