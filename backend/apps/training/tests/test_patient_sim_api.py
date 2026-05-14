import pytest

from apps.prescriptions.models import ActionLibraryItem
from apps.training.models import TrainingRecord


@pytest.mark.django_db
def test_patient_sim_current_prescription_returns_active_actions(
    client, doctor, active_prescription, prescription_action
):
    client.force_login(doctor)

    response = client.get(
        f"/api/patient-sim/project-patients/"
        f"{active_prescription.project_patient_id}/current-prescription/"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == active_prescription.id
    assert body["actions"][0]["id"] == prescription_action.id
    assert body["actions"][0]["action_name_snapshot"] == (
        prescription_action.action_name_snapshot
    )


@pytest.mark.django_db
def test_patient_sim_current_prescription_orders_actions_by_sort_order(
    client, doctor, active_prescription, prescription_action
):
    client.force_login(doctor)
    prescription_action.sort_order = 20
    prescription_action.save(update_fields=["sort_order", "updated_at"])
    second_action = ActionLibraryItem.objects.create(
        name="先返回动作",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="柔韧训练",
    )
    first_snapshot = active_prescription.add_action_snapshot(second_action, sort_order=10)

    response = client.get(
        f"/api/patient-sim/project-patients/"
        f"{active_prescription.project_patient_id}/current-prescription/"
    )

    assert response.status_code == 200
    action_ids = [action["id"] for action in response.json()["actions"]]
    assert action_ids == [first_snapshot.id, prescription_action.id]


@pytest.mark.django_db
def test_patient_sim_current_prescription_empty_without_active(client, doctor, project_patient):
    client.force_login(doctor)

    response = client.get(
        f"/api/patient-sim/project-patients/{project_patient.id}/current-prescription/"
    )

    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.django_db
def test_patient_sim_training_submit_creates_record(
    client, doctor, active_prescription, prescription_action
):
    client.force_login(doctor)

    response = client.post(
        f"/api/patient-sim/project-patients/"
        f"{active_prescription.project_patient_id}/training-records/",
        {
            "prescription_action": prescription_action.id,
            "training_date": "2026-05-06",
            "status": "completed",
            "actual_duration_minutes": 15,
            "form_data": {
                "perceived_difficulty": "中",
                "discomfort": "无",
            },
            "note": "完成顺利",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["project_patient"] == active_prescription.project_patient_id
    assert body["prescription"] == active_prescription.id
    assert body["prescription_action"] == prescription_action.id
    assert body["form_data"]["perceived_difficulty"] == "中"
    assert "completed_sets" not in body["form_data"]
    assert "completed_repetitions" not in body["form_data"]


@pytest.mark.django_db
def test_patient_sim_training_submit_rejects_too_large_actual_duration(
    client, doctor, active_prescription, prescription_action
):
    client.force_login(doctor)

    response = client.post(
        f"/api/patient-sim/project-patients/"
        f"{active_prescription.project_patient_id}/training-records/",
        {
            "prescription_action": prescription_action.id,
            "training_date": "2026-05-06",
            "status": "completed",
            "actual_duration_minutes": 2147483648,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert not TrainingRecord.objects.filter(
        project_patient=active_prescription.project_patient
    ).exists()


@pytest.mark.django_db
def test_patient_sim_training_submit_rejects_array_body(
    client, doctor, active_prescription
):
    client.force_login(doctor)

    response = client.post(
        f"/api/patient-sim/project-patients/"
        f"{active_prescription.project_patient_id}/training-records/",
        [],
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "请求体格式错误"
    assert not TrainingRecord.objects.filter(
        project_patient=active_prescription.project_patient
    ).exists()


@pytest.mark.django_db
def test_patient_sim_training_submit_requires_active_prescription(
    client, doctor, project_patient
):
    client.force_login(doctor)

    response = client.post(
        f"/api/patient-sim/project-patients/{project_patient.id}/training-records/",
        {
            "prescription_action": 999,
            "training_date": "2026-05-06",
            "status": "completed",
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "当前无生效处方" in str(response.json())
