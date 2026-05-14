import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.prescriptions.models import ActionLibraryItem, Prescription


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _action(**overrides):
    data = {
        "source_key": "activate-now-action",
        "name": "高抬腿踏步",
        "training_type": "运动训练",
        "internal_type": ActionLibraryItem.InternalType.MOTION,
        "action_type": "有氧训练",
        "instruction_text": "原地高抬腿踏步。",
        "suggested_frequency": "3 次/周",
        "suggested_duration_minutes": 20,
        "default_difficulty": "中",
        "video_url": "https://example.com/high-knee.mp4",
        "has_ai_supervision": True,
        "is_active": True,
    }
    data.update(overrides)
    return ActionLibraryItem.objects.create(**data)


def _payload(action, *, expected_active_version=None):
    return {
        "expected_active_version": expected_active_version,
        "note": "立即生效处方",
        "actions": [
            {
                "action_library_item": action.id,
                "weekly_frequency": "3 次/周",
                "duration_minutes": 20,
                "sets": 2,
                "repetitions": 12,
                "difficulty": "中",
                "notes": "注意呼吸",
                "sort_order": 1,
            }
        ],
    }


@pytest.mark.django_db
def test_activate_now_creates_active_prescription_and_snapshots(project_patient, doctor):
    action = _action()

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=_payload(action),
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    prescription = Prescription.objects.get(project_patient=project_patient)
    assert body["id"] == prescription.id
    assert body["version"] == 1
    assert body["status"] == Prescription.Status.ACTIVE
    assert body["opened_by"] == doctor.id
    assert body["opened_by_name"] == doctor.name
    assert body["effective_at"] is not None
    assert prescription.version == 1
    assert prescription.status == Prescription.Status.ACTIVE
    assert prescription.opened_by == doctor
    assert prescription.effective_at is not None

    assert len(body["actions"]) == 1
    snapshot = body["actions"][0]
    assert snapshot["action_library_item"] == action.id
    assert snapshot["action_name_snapshot"] == action.name
    assert snapshot["training_type_snapshot"] == action.training_type
    assert snapshot["internal_type_snapshot"] == action.internal_type
    assert snapshot["action_type_snapshot"] == action.action_type
    assert snapshot["action_instruction_snapshot"] == action.instruction_text
    assert snapshot["video_url_snapshot"] == action.video_url
    assert snapshot["has_ai_supervision_snapshot"] is True
    assert snapshot["weekly_frequency"] == "3 次/周"
    assert snapshot["duration_minutes"] == 20
    assert snapshot["sets"] == 2
    assert snapshot["repetitions"] == 12
    assert snapshot["difficulty"] == "中"
    assert snapshot["notes"] == "注意呼吸"
    assert snapshot["sort_order"] == 1


@pytest.mark.django_db
def test_activate_now_archives_previous_active(project_patient, doctor):
    action = _action()
    first = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=_payload(action, expected_active_version=1),
        format="json",
    )

    assert response.status_code == 201
    first.refresh_from_db()
    second = Prescription.objects.get(project_patient=project_patient, version=2)
    assert first.status == Prescription.Status.ARCHIVED
    assert second.status == Prescription.Status.ACTIVE
    assert response.json()["version"] == 2


@pytest.mark.django_db
def test_activate_now_rejects_duplicate_actions(project_patient, doctor):
    action = _action()
    payload = _payload(action)
    payload["actions"].append(payload["actions"][0] | {"sort_order": 2})

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=payload,
        format="json",
    )

    assert response.status_code == 400
    assert "重复动作" in str(response.data)
    assert not Prescription.objects.filter(project_patient=project_patient).exists()


@pytest.mark.django_db
def test_activate_now_rejects_stale_active_version(project_patient, doctor):
    action = _action()
    Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=_payload(action, expected_active_version=None),
        format="json",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "当前处方已变化，请刷新后重试。"}
