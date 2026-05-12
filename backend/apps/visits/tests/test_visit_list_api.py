import pytest
from rest_framework.test import APIClient

from apps.visits.models import VisitRecord


@pytest.mark.django_db
def test_visit_list_pagination_and_nested_fields(doctor, project_patient, patient, project):
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.get("/api/visits/")
    assert r.status_code == 200
    body = r.json()
    assert "results" in body
    assert "count" in body
    assert body["count"] >= 3
    row = next(x for x in body["results"] if x["visit_type"] == "T0")
    assert row["patient_id"] == patient.id
    assert row["patient_name"] == patient.name
    assert row["patient_phone"] == patient.phone
    assert row["project_id"] == project.id
    assert row["project_name"] == project.name
    assert "form_data" not in row


@pytest.mark.django_db
def test_visit_list_filter_visit_type(doctor, project_patient):
    t0 = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.get("/api/visits/", {"visit_type": "T0"})
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()["results"]}
    assert t0.id in ids
    for item in r.json()["results"]:
        assert item["visit_type"] == "T0"


@pytest.mark.django_db
def test_visit_list_filter_patient_name_icontains(doctor, project_patient, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.get("/api/visits/", {"patient_name": "患者甲"})
    assert r.status_code == 200
    assert r.json()["count"] >= 1
    assert all("患者甲" in (x.get("patient_name") or "") for x in r.json()["results"])


@pytest.mark.django_db
def test_visit_detail_still_includes_form_data(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.get(f"/api/visits/{visit.id}/")
    assert r.status_code == 200
    assert "form_data" in r.json()
