import uuid

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.patient_app.authentication import PatientAppPrincipal
from apps.patient_app.models import PatientAppSession
from apps.prescriptions.models import ActionLibraryItem


def counted_client(project_patient, active_prescription, sets=1):
    item, _ = ActionLibraryItem.objects.get_or_create(
        source_key="motion-resistance-shoulder-press",
        defaults={
            "name": "肩部推举",
            "internal_type": "motion",
            "training_type": "运动训练",
            "action_type": "抗阻训练",
        },
    )
    action = active_prescription.add_action_snapshot(
        item,
        dose_mode="sets",
        repetitions=10,
        sets=sets,
        weekly_target_count=3,
    )
    session = PatientAppSession(project_patient=project_patient, patient=project_patient.patient)
    client = APIClient()
    client.force_authenticate(PatientAppPrincipal(session))
    return client, action


@pytest.mark.django_db
def test_user_confirms_one_group_without_waiting_for_upload(project_patient, active_prescription):
    client, action = counted_client(project_patient, active_prescription)
    session_id, attempt_id = str(uuid.uuid4()), str(uuid.uuid4())
    start = timezone.now() - timezone.timedelta(seconds=40)
    opened = client.post(
        "/api/patient-app/motion-sessions/",
        {
            "client_session_id": session_id,
            "prescription_action": action.id,
            "started_at": start.isoformat(),
        },
        format="json",
    )
    assert opened.status_code == 201, opened.data
    motion_id = opened.json()["id"]
    path = f"/api/patient-app/motion-sessions/{motion_id}/sets/1/"
    began = client.post(
        path,
        {"operation": "start", "attempt_id": attempt_id, "started_at": start.isoformat()},
        format="json",
    )
    assert began.status_code == 200, began.data
    finished = client.post(
        path,
        {"operation": "complete", "attempt_id": attempt_id, "ended_at": timezone.now().isoformat()},
        format="json",
    )
    assert finished.status_code == 200, finished.data
    progress = client.get(f"/api/patient-app/motion-sessions/{motion_id}/").json()
    assert progress["completed_sets"] == 1
    assert progress["uploaded_sets"] == 0
    assert progress["status"] == "awaiting_upload"


@pytest.mark.django_db
def test_three_uploaded_groups_count_as_one_weekly_completion(
    project_patient, active_prescription, settings, doctor
):
    from types import SimpleNamespace
    from apps.training.models import TrainingVideo, VideoAssemblyJob
    from apps.training.video_tasks import attach_training_video

    client, action = counted_client(project_patient, active_prescription, sets=3)
    start = timezone.now() - timezone.timedelta(minutes=15)
    opened = client.post(
        "/api/patient-app/motion-sessions/",
        {
            "client_session_id": str(uuid.uuid4()),
            "prescription_action": action.id,
            "started_at": start.isoformat(),
        },
        format="json",
    )
    motion_id = opened.json()["id"]
    for index in range(1, 4):
        attempt = str(uuid.uuid4())
        began_at = start + timezone.timedelta(minutes=4 * (index - 1))
        end = began_at + timezone.timedelta(seconds=40)
        path = f"/api/patient-app/motion-sessions/{motion_id}/sets/{index}/"
        assert (
            client.post(
                path,
                {"operation": "start", "attempt_id": attempt, "started_at": began_at.isoformat()},
                format="json",
            ).status_code
            == 200
        )
        assert (
            client.post(
                path,
                {"operation": "complete", "attempt_id": attempt, "ended_at": end.isoformat()},
                format="json",
            ).status_code
            == 200
        )
        # 视频处理器的外部存储已确认；随后从患者公共接口验证计次结果。
        video = TrainingVideo.objects.create(
            project_patient=project_patient,
            prescription=active_prescription,
            prescription_action=action,
            motion_attempt_id=attempt,
            training_date=timezone.localdate(start),
            training_started_at=began_at,
            training_ended_at=end,
            actual_duration_seconds=40,
            status="queued",
        )
        job = VideoAssemblyJob.objects.create(
            training_video=video, status="running", qiniu_object_key=f"sets/{uuid.uuid4()}.mp4"
        )
        attach_training_video(
            job.id,
            SimpleNamespace(size_bytes=1024),
            {"hash": "hash", "fsize": 1024},
            lease_attempt=0,
        )
        current = client.get("/api/patient-app/current-prescription/").json()
        assert current["actions"][0]["weekly_completed_count"] == (1 if index == 3 else 0)
    progress = client.get(f"/api/patient-app/motion-sessions/{motion_id}/").json()
    assert progress["status"] == "completed"
    assert progress["uploaded_sets"] == 3
    staff = APIClient()
    staff.force_authenticate(doctor)
    detail = staff.get(f"/api/training/tracking/patients/{project_patient.patient_id}/").json()
    assert detail["prescription_completion"][0]["completed_count"] == 1
    assert detail["motion_sessions"][0]["uploaded_sets"] == 3
    assert sum(day["completed_count"] for day in detail["trend"]["daily"]) == 1
    assert sum(day["duration_minutes"] for day in detail["trend"]["daily"]) == 2


@pytest.mark.django_db
def test_counted_video_health_window_uses_actual_end(doctor, project_patient, active_prescription):
    from apps.training.models import TrainingVideo, TrainingRecord

    _, action = counted_client(project_patient, active_prescription)
    start = timezone.now() - timezone.timedelta(minutes=20)
    end = start + timezone.timedelta(seconds=40)
    from apps.training.tests.test_training_video_wearable_api import _bound_device, _measurement
    from apps.wearables.models import WearableMeasurement

    device, binding = _bound_device(project_patient, doctor)
    _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.HEART_RATE,
        measured_at=start,
        heart_rate=80,
    )
    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate(start),
        status="completed",
    )
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_record=record,
        status="attached",
        training_started_at=start,
        training_ended_at=end,
        expected_duration_seconds=1800,
    )
    client = APIClient()
    client.force_authenticate(doctor)
    response = client.get(f"/api/training/videos/{video.id}/wearable-window/")
    assert response.status_code == 200, response.data
    from django.utils.dateparse import parse_datetime

    assert parse_datetime(response.json()["window_ended_at"]) == end + timezone.timedelta(minutes=5)


@pytest.mark.django_db
def test_completed_old_prescription_can_recover_but_cannot_start_after_change(
    project_patient, active_prescription
):
    client, action = counted_client(project_patient, active_prescription, sets=3)
    now = timezone.now()
    active_prescription.effective_at = now - timezone.timedelta(days=2)
    active_prescription.archived_at = now - timezone.timedelta(minutes=10)
    active_prescription.status = "archived"
    active_prescription.save()
    start = now - timezone.timedelta(minutes=20)
    payload = {
        "client_session_id": str(uuid.uuid4()),
        "prescription_action": action.id,
        "started_at": start.isoformat(),
        "completed_sets": [
            {
                "index": 1,
                "attempt_id": str(uuid.uuid4()),
                "started_at": start.isoformat(),
                "ended_at": (start + timezone.timedelta(seconds=40)).isoformat(),
            }
        ],
    }
    response = client.post("/api/patient-app/motion-sessions/recover/", payload, format="json")
    assert response.status_code == 200, response.data
    assert response.json()["completed_sets"] == 1
    repeated = client.post("/api/patient-app/motion-sessions/recover/", payload, format="json")
    assert repeated.json()["id"] == response.json()["id"]
    payload["completed_sets"].append(
        {
            "index": 2,
            "attempt_id": str(uuid.uuid4()),
            "started_at": (now - timezone.timedelta(minutes=3)).isoformat(),
            "ended_at": (now - timezone.timedelta(minutes=2)).isoformat(),
        }
    )
    rejected = client.post("/api/patient-app/motion-sessions/recover/", payload, format="json")
    assert rejected.status_code == 400
    assert (
        client.get(f"/api/patient-app/motion-sessions/{response.json()['id']}/").json()[
            "completed_sets"
        ]
        == 1
    )


@pytest.mark.django_db
def test_short_rest_and_abandoned_attempt_cannot_be_completed(project_patient, active_prescription):
    client, action = counted_client(project_patient, active_prescription, sets=3)
    start = timezone.now() - timezone.timedelta(minutes=10)
    response = client.post(
        "/api/patient-app/motion-sessions/",
        {
            "client_session_id": str(uuid.uuid4()),
            "prescription_action": action.id,
            "started_at": start.isoformat(),
        },
        format="json",
    )
    prefix = f"/api/patient-app/motion-sessions/{response.json()['id']}/sets/"
    attempt = str(uuid.uuid4())
    first = {"operation": "start", "attempt_id": attempt, "started_at": start.isoformat()}
    assert client.post(prefix + "1/", first, format="json").status_code == 200
    assert (
        client.post(
            prefix + "1/", {"operation": "abandon", "attempt_id": attempt}, format="json"
        ).status_code
        == 200
    )
    assert (
        client.post(
            prefix + "1/",
            {
                "operation": "complete",
                "attempt_id": attempt,
                "ended_at": (start + timezone.timedelta(seconds=40)).isoformat(),
            },
            format="json",
        ).status_code
        == 400
    )
    first["attempt_id"] = str(uuid.uuid4())
    assert client.post(prefix + "1/", first, format="json").status_code == 200
    assert (
        client.post(
            prefix + "1/",
            {
                "operation": "complete",
                "attempt_id": first["attempt_id"],
                "ended_at": (start + timezone.timedelta(seconds=40)).isoformat(),
            },
            format="json",
        ).status_code
        == 200
    )
    assert (
        client.post(
            prefix + "2/",
            {
                "operation": "start",
                "attempt_id": str(uuid.uuid4()),
                "started_at": (start + timezone.timedelta(seconds=100)).isoformat(),
            },
            format="json",
        ).status_code
        == 400
    )
