import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.prescriptions.services import lock_open_project_patient_for_prescription
from apps.studies.models import StudyProject


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


def _payload(action, *, expected_active_version=None, action_overrides=None):
    action_data = {
        "action_library_item": action.id,
        "weekly_frequency": "3 次/周",
        "weekly_target_count": 3,
        "duration_minutes": 20,
        "difficulty": "中",
        "notes": "注意呼吸",
        "sort_order": 1,
    }
    if action_overrides:
        action_data.update(action_overrides)
    return {
        "expected_active_version": expected_active_version,
        "note": None,
        "actions": [action_data],
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
    assert body["note"] == ""
    assert prescription.note == ""

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
    assert snapshot["weekly_target_count"] == 3
    assert snapshot["duration_minutes"] == 20
    assert "sets" not in snapshot
    assert "repetitions" not in snapshot
    assert snapshot["difficulty"] == "中"
    assert snapshot["notes"] == "注意呼吸"
    assert snapshot["sort_order"] == 1


@pytest.mark.django_db
def test_activate_now_derives_weekly_target_count_from_frequency_when_omitted(
    project_patient, doctor
):
    action = _action()
    payload = _payload(action, action_overrides={"weekly_frequency": "4 次/周"})
    del payload["actions"][0]["weekly_target_count"]

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=payload,
        format="json",
    )

    assert response.status_code == 201
    snapshot = response.json()["actions"][0]
    assert snapshot["weekly_frequency"] == "4 次/周"
    assert snapshot["weekly_target_count"] == 4


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
    assert first.archived_at is not None
    assert second.status == Prescription.Status.ACTIVE
    assert second.archived_at is None
    assert response.json()["version"] == 2


@pytest.mark.django_db
def test_activate_now_archives_all_existing_active_prescriptions(project_patient, doctor):
    action = _action()
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
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=_payload(action, expected_active_version=2),
        format="json",
    )

    assert response.status_code == 201
    first.refresh_from_db()
    second.refresh_from_db()
    active_prescriptions = Prescription.objects.filter(
        project_patient=project_patient,
        status=Prescription.Status.ACTIVE,
    )
    assert response.json()["version"] == 3
    assert first.status == Prescription.Status.ARCHIVED
    assert second.status == Prescription.Status.ARCHIVED
    assert first.archived_at is not None
    assert second.archived_at is not None
    assert list(active_prescriptions.values_list("version", flat=True)) == [3]


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


@pytest.mark.django_db
@pytest.mark.parametrize(
    "action_overrides",
    [
        {"weekly_frequency": "x" * 81},
        {"difficulty": "x" * 41},
        {"duration_minutes": 0},
        {"weekly_target_count": 0},
    ],
)
def test_activate_now_rejects_invalid_action_parameters(
    project_patient, doctor, action_overrides
):
    action = _action()

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=_payload(action, action_overrides=action_overrides),
        format="json",
    )

    assert response.status_code == 400
    assert not Prescription.objects.filter(project_patient=project_patient).exists()


@pytest.mark.django_db
def test_activate_now_rejects_invalid_expected_active_version(project_patient, doctor):
    action = _action()

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=_payload(action, expected_active_version=0),
        format="json",
    )

    assert response.status_code == 400
    assert not Prescription.objects.filter(project_patient=project_patient).exists()


@pytest.mark.django_db
def test_activate_now_accepts_non_aerobic_action_with_adjustable_duration(project_patient, doctor):
    action = _action(action_type="抗阻训练")

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=_payload(
            action,
            action_overrides={
                "duration_minutes": 12,
            },
        ),
        format="json",
    )

    assert response.status_code == 201
    snapshot = response.json()["actions"][0]
    assert snapshot["duration_minutes"] == 12
    assert "sets" not in snapshot
    assert "repetitions" not in snapshot


@pytest.mark.django_db
def test_activate_now_rejects_missing_duration_for_any_motion_action(
    project_patient,
    doctor,
):
    action = _action(action_type="抗阻训练")

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=_payload(action, action_overrides={"duration_minutes": None}),
        format="json",
    )

    assert response.status_code == 400
    assert "动作需填写时长" in str(response.data)
    assert not Prescription.objects.filter(project_patient=project_patient).exists()


@pytest.mark.django_db
def test_activate_now_rejects_legacy_set_or_repetition_payload(project_patient, doctor):
    action = _action()

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=_payload(action, action_overrides={"sets": 2}),
        format="json",
    )

    assert response.status_code == 400
    assert "不支持组数或次数" in str(response.data)
    assert not Prescription.objects.filter(project_patient=project_patient).exists()


@pytest.mark.django_db
def test_prescription_base_post_returns_405(doctor):
    response = _client(doctor).post("/api/prescriptions/", data={}, format="json")

    assert response.status_code == 405


@pytest.mark.django_db
def test_prescription_action_base_post_returns_405(doctor):
    response = _client(doctor).post(
        "/api/prescriptions/prescription-actions/",
        data={},
        format="json",
    )

    assert response.status_code == 405


@pytest.mark.django_db
def test_activate_now_rejects_completed_project(project_patient, doctor):
    action = _action()
    project_patient.project.status = StudyProject.Status.ARCHIVED
    project_patient.project.save(update_fields=["status", "updated_at"])

    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        data=_payload(action),
        format="json",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "项目已完结，不能调整处方。"}
    assert not Prescription.objects.filter(project_patient=project_patient).exists()


@pytest.mark.django_db
def test_terminate_rejects_completed_project(project_patient, doctor):
    prescription = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    project_patient.project.status = StudyProject.Status.ARCHIVED
    project_patient.project.save(update_fields=["status", "updated_at"])

    response = _client(doctor).post(f"/api/prescriptions/{prescription.id}/terminate/")

    assert response.status_code == 400
    assert response.json() == {"detail": "项目已完结，不能调整处方。"}
    prescription.refresh_from_db()
    assert prescription.status == Prescription.Status.ACTIVE
    assert prescription.archived_at is None


@pytest.mark.django_db
def test_terminate_sets_archived_at(project_patient, doctor):
    prescription = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )

    response = _client(doctor).post(f"/api/prescriptions/{prescription.id}/terminate/")

    assert response.status_code == 200
    prescription.refresh_from_db()
    assert prescription.status == Prescription.Status.TERMINATED
    assert prescription.archived_at is not None
    assert response.json()["archived_at"] is not None


@pytest.mark.django_db
def test_prescription_history_can_include_terminated(project_patient, doctor):
    terminated = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.TERMINATED,
        effective_at=timezone.now(),
        archived_at=timezone.now(),
    )

    default_response = _client(doctor).get(
        "/api/prescriptions/",
        {"project_patient": project_patient.id},
    )
    history_response = _client(doctor).get(
        "/api/prescriptions/",
        {"project_patient": project_patient.id, "include_terminated": "true"},
    )

    assert default_response.status_code == 200
    assert history_response.status_code == 200
    assert all(item["id"] != terminated.id for item in default_response.json())
    assert any(item["id"] == terminated.id for item in history_response.json())


@pytest.mark.django_db
def test_legacy_activate_endpoint_is_disabled(project_patient, doctor):
    prescription = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.DRAFT,
    )

    response = _client(doctor).post(f"/api/prescriptions/{prescription.id}/activate/")

    assert response.status_code == 405
    assert response.json() == {"detail": "请通过项目患者处方立即生效接口开具或调整处方。"}
    prescription.refresh_from_db()
    assert prescription.status == Prescription.Status.DRAFT


@pytest.mark.django_db
def test_legacy_activate_endpoint_does_not_archive_current_active(project_patient, doctor):
    active = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    prescription = Prescription.objects.create(
        project_patient=project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.DRAFT,
    )

    response = _client(doctor).post(f"/api/prescriptions/{prescription.id}/activate/")

    assert response.status_code == 405
    active.refresh_from_db()
    prescription.refresh_from_db()
    assert active.status == Prescription.Status.ACTIVE
    assert prescription.status == Prescription.Status.DRAFT


@pytest.mark.django_db
def test_lock_open_project_patient_handles_missing_link():
    with pytest.raises(ValidationError) as exc_info:
        lock_open_project_patient_for_prescription(999999)

    assert "入组关系已不存在" in str(exc_info.value.detail)
