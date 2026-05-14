import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient
from apps.visits.models import VisitRecord
from apps.visits.services import ensure_default_visits


@pytest.fixture
def auth_client(doctor):
    client = APIClient()
    client.force_authenticate(user=doctor)
    return client


@pytest.mark.django_db
def test_project_patient_serializer_exposes_visit_ids(auth_client, project_patient):
    r = auth_client.get(f"/api/studies/project-patients/?project={project_patient.project_id}")
    assert r.status_code == 200, r.content

    rows = r.data if isinstance(r.data, list) else r.data["results"]
    assert len(rows) == 1

    visit_ids = rows[0]["visit_ids"]
    assert set(visit_ids.keys()) == {"T0", "T1", "T2"}
    for vt in ("T0", "T1", "T2"):
        assert visit_ids[vt] == VisitRecord.objects.get(project_patient=project_patient, visit_type=vt).id


@pytest.mark.django_db
def test_project_patient_serializer_exposes_visit_summaries(auth_client, project_patient):
    t0 = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    t0.status = VisitRecord.Status.COMPLETED
    t0.visit_date = "2026-05-14"
    t0.save(update_fields=["status", "visit_date"])

    r = auth_client.get(f"/api/studies/project-patients/?project={project_patient.project_id}")

    assert r.status_code == 200, r.content
    rows = r.data if isinstance(r.data, list) else r.data["results"]
    row = rows[0]
    assert row["project_name"] == project_patient.project.name
    assert row["project_status"] == project_patient.project.status
    assert row["visit_summaries"]["T0"] == {
        "id": t0.id,
        "status": VisitRecord.Status.COMPLETED,
        "visit_date": "2026-05-14",
    }
    assert row["visit_summaries"]["T1"]["status"] == VisitRecord.Status.DRAFT
    assert row["visit_summaries"]["T2"]["status"] == VisitRecord.Status.DRAFT


@pytest.mark.django_db
def test_project_patient_serializer_exposes_updated_at(auth_client, project_patient):
    r = auth_client.get(f"/api/studies/project-patients/?project={project_patient.project_id}")

    assert r.status_code == 200, r.content
    rows = r.data if isinstance(r.data, list) else r.data["results"]
    row = rows[0]
    assert row["updated_at"]
    assert "T" in row["updated_at"]


@pytest.mark.django_db
def test_project_patient_list_filters_patient_name_and_phone(auth_client, project_patient):
    other_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900002222",
        primary_doctor=project_patient.patient.primary_doctor,
    )
    other_project_patient = ProjectPatient.objects.create(
        project=project_patient.project,
        patient=other_patient,
        group=project_patient.group,
    )
    ensure_default_visits(other_project_patient)

    by_name = auth_client.get("/api/studies/project-patients/", {"patient_name": "患者甲"})
    by_phone = auth_client.get("/api/studies/project-patients/", {"patient_phone": "13900001111"})
    no_name_match = auth_client.get("/api/studies/project-patients/", {"patient_name": "不存在"})
    no_phone_match = auth_client.get("/api/studies/project-patients/", {"patient_phone": "000000"})

    assert by_name.status_code == 200, by_name.content
    assert by_phone.status_code == 200, by_phone.content
    assert no_name_match.status_code == 200, no_name_match.content
    assert no_phone_match.status_code == 200, no_phone_match.content
    assert [row["id"] for row in by_name.data] == [project_patient.id]
    assert [row["id"] for row in by_phone.data] == [project_patient.id]
    assert no_name_match.data == []
    assert no_phone_match.data == []
