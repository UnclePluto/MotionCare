import pytest
from rest_framework.test import APIClient

from apps.studies.models import ProjectPatient, StudyGroup, StudyProject


@pytest.mark.django_db
def test_enroll_projects_creates_links(doctor, patient, project):
    p2 = StudyProject.objects.create(name="第二项研究", created_by=doctor)
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {"project_ids": [project.id, p2.id]},
        format="json",
    )
    assert r.status_code == 200
    assert len(r.data["created"]) == 2
    assert r.data["skipped_project_ids"] == []
    assert ProjectPatient.objects.filter(patient=patient, project=project).exists()
    assert ProjectPatient.objects.filter(patient=patient, project=p2).exists()
    assert "detail" in r.data


@pytest.mark.django_db
def test_enroll_projects_idempotent_skip(doctor, patient, project):
    g = StudyGroup.objects.create(project=project, name="G", target_ratio=1)
    ProjectPatient.objects.create(project=project, patient=patient, group=g)
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {"project_ids": [project.id]},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["created"] == []
    assert r.data["skipped_project_ids"] == [project.id]


@pytest.mark.django_db
def test_enroll_projects_rejects_unknown_project(doctor, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {"project_ids": [999999]},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_study_project_list_includes_patient_count(doctor, patient, project):
    g = StudyGroup.objects.create(project=project, name="G", target_ratio=1)
    ProjectPatient.objects.create(project=project, patient=patient, group=g)
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.get("/api/studies/projects/")
    assert r.status_code == 200
    rows = r.data if isinstance(r.data, list) else r.data.get("results", [])
    row = next(x for x in rows if x["id"] == project.id)
    assert row["patient_count"] == 1


@pytest.mark.django_db
def test_project_patients_filter_by_patient(doctor, patient, project):
    g = StudyGroup.objects.create(project=project, name="G", target_ratio=1)
    ProjectPatient.objects.create(project=project, patient=patient, group=g)
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.get(f"/api/studies/project-patients/?patient={patient.id}")
    assert r.status_code == 200
    data = r.data
    rows = data if isinstance(data, list) else data.get("results", data)
    assert len(rows) >= 1
    assert all(row["patient"] == patient.id for row in rows)
