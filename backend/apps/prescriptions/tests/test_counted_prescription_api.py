import pytest
from rest_framework.test import APIClient

from apps.prescriptions.models import ActionLibraryItem


@pytest.mark.django_db
def test_doctor_opens_counted_shoulder_press_without_duration(doctor, project_patient):
    client = APIClient()
    client.force_authenticate(doctor)
    action = ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press")
    response = client.post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        {
            "actions": [
                {
                    "action_library_item": action.id,
                    "repetitions": 10,
                    "sets": 1,
                    "weekly_target_count": 3,
                }
            ]
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    snapshot = response.json()["actions"][0]
    assert (snapshot["repetitions"], snapshot["sets"], snapshot["count_unit"]) == (10, 1, "total")
    assert snapshot["duration_minutes"] is None
    assert snapshot["dose_mode"] == "sets"


@pytest.mark.django_db
def test_cutover_preserves_frequency_and_walking_progress(
    doctor, project_patient, active_prescription
):
    from django.core.management import call_command
    from django.utils import timezone
    from apps.training.models import TrainingRecord
    from io import StringIO

    shoulder = active_prescription.add_action_snapshot(
        ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press"),
        duration_minutes=10,
        weekly_target_count=5,
    )
    walking = active_prescription.add_action_snapshot(
        ActionLibraryItem.objects.get(source_key="motion-aerobic-high-knee"),
        duration_minutes=20,
        weekly_target_count=4,
    )
    for action in [shoulder, walking]:
        TrainingRecord.objects.create(
            project_patient=project_patient,
            prescription=active_prescription,
            prescription_action=action,
            training_date=timezone.localdate(),
            status="completed",
        )
    client = APIClient()
    client.force_authenticate(doctor)
    url = f"/api/prescriptions/current/?project_patient={project_patient.id}"
    call_command("migrate_counted_motion_prescriptions", stdout=StringIO())
    assert client.get(url).json()["version"] == 1
    call_command("migrate_counted_motion_prescriptions", apply=True, stdout=StringIO())
    call_command("migrate_counted_motion_prescriptions", apply=True, stdout=StringIO())
    result = client.get(url).json()
    assert result["version"] == 2
    counted, walk = result["actions"]
    assert (counted["repetitions"], counted["sets"], counted["weekly_target_count"]) == (10, 3, 5)
    assert (walk["duration_minutes"], walk["weekly_target_count"]) == (20, 4)
    detail = client.get(f"/api/training/tracking/patients/{project_patient.patient_id}/").json()
    counts = {
        row["prescription_action"]: row["completed_count"]
        for row in detail["prescription_completion"]
    }
    assert counts[counted["id"]] == 0
    assert counts[walk["id"]] == 1


@pytest.mark.django_db
def test_legacy_pending_prescription_cannot_be_activated_after_cutover(
    project_patient, active_prescription
):
    from django.core.management import call_command
    from django.core.exceptions import ValidationError
    from io import StringIO
    from apps.prescriptions.models import Prescription
    from apps.prescriptions.services import activate_prescription

    legacy = Prescription.objects.create(
        project_patient=project_patient,
        opened_by=active_prescription.opened_by,
        version=2,
        status="pending",
    )
    legacy.add_action_snapshot(
        ActionLibraryItem.objects.get(source_key="motion-resistance-row"), duration_minutes=10
    )
    call_command("migrate_counted_motion_prescriptions", apply=True, stdout=StringIO())
    with pytest.raises(ValidationError, match="个数和组数"):
        activate_prescription(legacy)
    legacy.refresh_from_db()
    assert legacy.status == "pending"


@pytest.mark.django_db(transaction=True)
def test_cutover_rolls_back_failure_and_serializes_concurrent_retries(
    project_patient, active_prescription, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections
    from apps.prescriptions import cutover
    from apps.prescriptions.models import MotionPrescriptionCutover, Prescription

    item, _ = ActionLibraryItem.objects.get_or_create(
        source_key="motion-resistance-row",
        defaults={"name": "坐姿划船", "internal_type": "motion", "training_type": "运动训练"},
    )
    active_prescription.add_action_snapshot(item, duration_minutes=10, weekly_target_count=4)
    invalidate = cutover.invalidate_legacy_training

    def unavailable(_):
        raise RuntimeError("模拟切换事务中途失败")

    monkeypatch.setattr(cutover, "invalidate_legacy_training", unavailable)
    with pytest.raises(RuntimeError, match="中途失败"):
        cutover.cutover_patient(project_patient.pk)
    active_prescription.refresh_from_db()
    assert active_prescription.status == "active"
    assert Prescription.objects.filter(project_patient=project_patient).count() == 1
    assert not MotionPrescriptionCutover.objects.filter(project_patient=project_patient).exists()
    monkeypatch.setattr(cutover, "invalidate_legacy_training", invalidate)
    barrier = Barrier(2)

    def retry():
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return cutover.cutover_patient(project_patient.pk)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(retry) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]
    assert sum(bool(result["new_prescription_version"]) for result in results) == 1
    active = Prescription.objects.get(project_patient=project_patient, status="active")
    assert active.version == 2
    assert active.actions.get().weekly_target_count == 4
    assert MotionPrescriptionCutover.objects.filter(project_patient=project_patient).count() == 1
