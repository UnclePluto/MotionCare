from apps.studies.tests.conftest import *  # noqa: F403

import pytest
from django.utils import timezone

from apps.prescriptions.models import ActionLibraryItem, Prescription


@pytest.fixture
def active_prescription(db, project_patient, doctor):
    return Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )


@pytest.fixture
def prescription_action(db, active_prescription):
    action = ActionLibraryItem.objects.create(
        name="坐立训练",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="平衡训练",
        instruction_text="从椅子坐下后站起。\n\n动作要点：保持躯干稳定。",
    )
    return active_prescription.add_action_snapshot(
        action,
        weekly_frequency="2 次/周",
        duration_minutes=10,
        sets=2,
    )
