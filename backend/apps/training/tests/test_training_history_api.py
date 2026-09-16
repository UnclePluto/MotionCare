from io import StringIO
import json

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.prescriptions.models import ActionLibraryItem
from apps.training.tests.test_tracking_api import _record


@pytest.fixture
def history_client(db):
    user = User.objects.create_user(
        phone="13800009997", password="pass123456", role=User.Role.ADMIN
    )
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def old_motion_records(project_patient, active_prescription):
    records = []
    for key in (
        "motion-balance-sit-stand",
        "motion-resistance-row",
        "motion-resistance-leg-kickback",
        "motion-resistance-shoulder-press",
        "motion-aerobic-high-knee",
    ):
        item, _ = ActionLibraryItem.objects.get_or_create(
            source_key=key,
            defaults={
                "name": key,
                "internal_type": "motion",
                "training_type": "运动训练",
                "action_type": "运动",
            },
        )
        action = active_prescription.add_action_snapshot(
            item, duration_minutes=10, weekly_target_count=2
        )
        records.append(
            _record(
                project_patient, active_prescription, action, training_date=timezone.localdate()
            )
        )
    return records


@pytest.mark.django_db
def test_preview_counts_only_four_legacy_actions_without_invalidating(
    history_client, project_patient, old_motion_records
):
    output = StringIO()
    call_command(
        "invalidate_legacy_motion_training", project_patient=project_patient.pk, stdout=output
    )
    result = json.loads(output.getvalue())
    assert result["affected_records"] == 4
    assert result["already_invalidated_records"] == 0
    normal = history_client.get("/api/training/")
    assert {row["id"] for row in normal.data} == {row.pk for row in old_motion_records}


@pytest.mark.django_db
def test_invalidated_record_only_visible_in_authorized_history(
    history_client, doctor, project_patient, old_motion_records, settings
):
    settings.TRAINING_HEALTH_ENFORCE_ROW_SCOPE = True
    import uuid

    record = old_motion_records[0]
    record.invalidated_at = timezone.now()
    record.invalidation_reason = "运动处方已切换按组计数，旧模式训练仅保留历史备查"
    record.cutover_marker = uuid.uuid4()
    record.save()
    history = history_client.get("/api/training/history/", {"project_patient": project_patient.pk})
    assert history.status_code == 200
    assert [row["id"] for row in history.data] == [record.pk]
    assert history.data[0]["cutover_marker"] == str(record.cutover_marker)
    assert history.data[0]["invalidation_reason"] == record.invalidation_reason
    normal = history_client.get("/api/training/")
    assert record.pk not in {row["id"] for row in normal.data}
    assert history_client.get(f"/api/training/{record.pk}/").status_code == 404
    assert history_client.get(f"/api/training/history/{record.pk}/").status_code == 200
    other_doctor = User.objects.create_user(
        phone="13800009998", password="pass123456", role=User.Role.DOCTOR
    )
    history_client.force_authenticate(other_doctor)
    assert history_client.get(f"/api/training/history/{record.pk}/").status_code == 404
    assert (
        history_client.get(
            "/api/training/history/", {"project_patient": project_patient.pk}
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_cutover_is_idempotent_and_preserves_walking_and_new_mode(
    history_client, project_patient, active_prescription, old_motion_records
):
    from apps.prescriptions.models import MotionPrescriptionCutover, PrescriptionAction

    cutover = MotionPrescriptionCutover.objects.create(project_patient=project_patient)
    old_action = old_motion_records[0].prescription_action
    new_action = PrescriptionAction.objects.get(pk=old_action.pk)
    new_action.pk = None
    new_action.dose_mode = "sets"
    new_action.repetitions = 10
    new_action.sets = 3
    new_action.count_unit = "total"
    new_action.duration_minutes = None
    new_action.save()
    new_record = _record(
        project_patient, active_prescription, new_action, training_date=timezone.localdate()
    )
    call_command(
        "invalidate_legacy_motion_training",
        project_patient=project_patient.pk,
        execute=True,
        stdout=StringIO(),
    )
    first = history_client.get("/api/training/history/", {"project_patient": project_patient.pk})
    assert len(first.data) == 4
    assert all(
        row["cutover_marker"] == str(cutover.marker)
        and row["invalidated_at"]
        and row["invalidation_reason"]
        for row in first.data
    )
    call_command(
        "invalidate_legacy_motion_training",
        project_patient=project_patient.pk,
        execute=True,
        stdout=StringIO(),
    )
    assert (
        history_client.get("/api/training/history/", {"project_patient": project_patient.pk}).data
        == first.data
    )
    normal = history_client.get("/api/training/")
    assert {row["id"] for row in normal.data} == {old_motion_records[-1].pk, new_record.pk}


@pytest.mark.django_db
def test_old_video_published_after_cutover_stays_history_and_keeps_analysis(
    history_client, project_patient, active_prescription, old_motion_records, settings
):
    from apps.prescriptions.models import MotionPrescriptionCutover
    from apps.training.tests.test_training_video_api import _queued_video_job, _attach

    settings.PP_MCARE_AUTO_ENQUEUE_ENABLED = True
    settings.QINIU_BUCKET = "motioncare-training"
    settings.QINIU_ACCESS_KEY = "test-access"
    settings.QINIU_SECRET_KEY = "test-secret"
    settings.QINIU_DOWNLOAD_DOMAIN = "https://cdn.example.com"
    video, job = _queued_video_job(
        project_patient, active_prescription, old_motion_records[0].prescription_action
    )
    cutover = MotionPrescriptionCutover.objects.create(project_patient=project_patient)
    call_command(
        "invalidate_legacy_motion_training",
        project_patient=project_patient.pk,
        execute=True,
        stdout=StringIO(),
    )
    _attach(job)
    _attach(job)
    history = history_client.get("/api/training/history/", {"project_patient": project_patient.pk})
    assert len(history.data) == 5
    published = next(row for row in history.data if row["video_id"] == video.pk)
    assert published["cutover_marker"] == str(cutover.marker)
    assert history_client.get(f"/api/training/{published['id']}/").status_code == 404
    assert history_client.get(f"/api/training/videos/{video.pk}/download-url/").status_code == 200
    analysis = history_client.get(f"/api/training/videos/{video.pk}/analysis-jobs/latest/")
    assert analysis.status_code == 200
    assert analysis.data["status"] == "pending"


@pytest.mark.django_db(transaction=True)
def test_export_excludes_invalidated_records(history_client, project_patient, old_motion_records):
    from apps.training.tests.test_training_detail_export_api import download, read_response, records

    old_motion_records[0].invalidated_at = timezone.now()
    old_motion_records[0].save(update_fields=["invalidated_at"])
    book = read_response(download(history_client, project_patient))
    exported = records(book["训练场次"])
    assert len(exported) == 4
    assert {str(row["训练记录编号"]) for row in exported} == {
        str(row.pk) for row in old_motion_records[1:]
    }
