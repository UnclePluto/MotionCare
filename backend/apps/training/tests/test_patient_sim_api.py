import pytest


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
                "completed_sets": 2,
                "completed_repetitions": 12,
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
    assert body["form_data"]["completed_sets"] == 2


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
