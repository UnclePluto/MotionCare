import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_get_patient_baseline_creates_and_returns_empty_demographics(doctor, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.get(f"/api/patients/{patient.id}/baseline/")

    assert resp.status_code == 200
    assert resp.data["patient"] == patient.id
    assert resp.data["demographics"] == {}
    assert resp.data["surgery_allergy"] == {}
    assert resp.data["comorbidities"] == {}
    assert resp.data["lifestyle"] == {}
    assert resp.data["baseline_medications"] == {}


@pytest.mark.django_db
def test_patch_patient_baseline_updates_json_fields(doctor, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/patients/{patient.id}/baseline/",
        data={
            "subject_id": "SUBJ-001",
            "demographics": {"education_years": 16},
            "baseline_medications": {"notes": "ibuprofen"},
        },
        format="json",
    )

    assert resp.status_code == 200
    assert resp.data["subject_id"] == "SUBJ-001"
    assert resp.data["demographics"]["education_years"] == 16
    assert resp.data["baseline_medications"]["notes"] == "ibuprofen"

    resp2 = client.get(f"/api/patients/{patient.id}/baseline/")
    assert resp2.status_code == 200
    assert resp2.data["subject_id"] == "SUBJ-001"
    assert resp2.data["demographics"]["education_years"] == 16
    assert resp2.data["baseline_medications"]["notes"] == "ibuprofen"
