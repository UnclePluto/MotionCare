import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_patient_list_requires_authentication():
    client = APIClient()
    response = client.get("/api/patients/")
    assert response.status_code in {401, 403}


@pytest.mark.django_db
def test_authenticated_doctor_can_create_patient(doctor):
    client = APIClient()
    client.force_authenticate(user=doctor)

    response = client.post(
        "/api/patients/",
        {
            "name": "患者乙",
            "gender": "female",
            "age": 68,
            "phone": "13900002222",
            "primary_doctor": doctor.id,
            "symptom_note": "记忆力下降",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["name"] == "患者乙"

