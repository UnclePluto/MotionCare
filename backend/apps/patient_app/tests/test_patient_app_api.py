import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.health.models import DailyHealthRecord
from apps.patient_app.services import bind_project_patient_with_code, create_binding_code
from apps.training.models import TrainingRecord


def _auth_client(project_patient, doctor):
    code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    token, _ = bind_project_patient_with_code(code, wx_openid="openid-a")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
def test_bind_api_returns_token_and_bound_identity(project_patient, doctor):
    code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    client = APIClient()

    response = client.post(
        "/api/patient-app/bind/",
        {"code": code, "wx_openid": "openid-a"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["token"]
    assert response.data["project_patient_id"] == project_patient.id
    assert response.data["patient"]["name"] == project_patient.patient.name
    assert response.data["project"]["name"] == project_patient.project.name


@pytest.mark.parametrize(
    "payload",
    [
        {"code": "12AB", "wx_openid": "openid-a"},
        {"code": "１２３４", "wx_openid": "openid-a"},
        {"code": "", "wx_openid": "openid-a"},
        {"code": "123", "wx_openid": "openid-a"},
        {"code": "12345", "wx_openid": "openid-a"},
        {"code": " 1234 ", "wx_openid": "openid-a"},
        {"code": "\t1234\n", "wx_openid": "openid-a"},
        {"code": 1234, "wx_openid": "openid-a"},
        {"code": None, "wx_openid": "openid-a"},
        {"wx_openid": "openid-a"},
    ],
)
@pytest.mark.django_db
def test_bind_api_rejects_non_numeric_or_wrong_length_code(payload):
    client = APIClient()
    response = client.post(
        "/api/patient-app/bind/",
        payload,
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "4 位数字" in str(response.data)


@pytest.mark.django_db
def test_patient_app_me_uses_bearer_token(project_patient, doctor):
    client = _auth_client(project_patient, doctor)

    response = client.get("/api/patient-app/me/")

    assert response.status_code == 200, response.data
    assert response.data["project_patient_id"] == project_patient.id
    assert response.data["patient"]["id"] == project_patient.patient_id
    assert response.data["project"]["id"] == project_patient.project_id


@pytest.mark.django_db
def test_current_prescription_includes_weekly_progress_and_recent_record(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    prescription_action.weekly_target_count = 2
    prescription_action.save(update_fields=["weekly_target_count", "updated_at"])
    TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=12,
    )
    client = _auth_client(project_patient, doctor)

    response = client.get("/api/patient-app/current-prescription/")

    assert response.status_code == 200, response.data
    assert response.data["id"] == active_prescription.id
    action = response.data["actions"][0]
    assert action["id"] == prescription_action.id
    assert action["weekly_target_count"] == 2
    assert action["weekly_completed_count"] == 1
    assert action["recent_record"]["status"] == TrainingRecord.Status.COMPLETED


@pytest.mark.django_db
def test_training_record_api_allows_multiple_records_same_day(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    client = _auth_client(project_patient, doctor)
    payload = {
        "prescription_action": prescription_action.id,
        "training_date": str(timezone.localdate()),
        "status": TrainingRecord.Status.COMPLETED,
        "actual_duration_minutes": 10,
        "note": "完成",
    }

    first = client.post("/api/patient-app/training-records/", payload, format="json")
    second = client.post("/api/patient-app/training-records/", payload, format="json")

    assert first.status_code == 201, first.data
    assert second.status_code == 201, second.data
    assert TrainingRecord.objects.filter(project_patient=project_patient).count() == 2
    assert first.data["prescription"] == active_prescription.id
    assert second.data["prescription_action"] == prescription_action.id


@pytest.mark.django_db
def test_action_history_only_returns_current_action_records(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
    )
    client = _auth_client(project_patient, doctor)

    response = client.get(f"/api/patient-app/actions/{prescription_action.id}/history/")

    assert response.status_code == 200, response.data
    assert response.data["last_7_days_completed_count"] == 1
    assert response.data["last_30_days_completed_count"] == 1
    assert len(response.data["records"]) == 1
    assert response.data["records"][0]["prescription_action"] == prescription_action.id


@pytest.mark.django_db
def test_daily_health_today_upserts_patient_record(project_patient, doctor):
    client = _auth_client(project_patient, doctor)

    first = client.put("/api/patient-app/daily-health/today/", {"steps": 1000}, format="json")
    second = client.put("/api/patient-app/daily-health/today/", {"steps": 2000}, format="json")

    assert first.status_code == 200, first.data
    assert second.status_code == 200, second.data
    assert DailyHealthRecord.objects.filter(patient=project_patient.patient).count() == 1
    record = DailyHealthRecord.objects.get(patient=project_patient.patient)
    assert record.record_date == timezone.localdate()
    assert record.steps == 2000
