import pytest
from rest_framework.test import APIClient

from apps.studies.models import ProjectPatient, StudyGroup, StudyProject


@pytest.mark.django_db
def test_enroll_projects_confirms_into_chosen_group(doctor, patient, project):
    g1 = StudyGroup.objects.create(project=project, name="A", target_ratio=1)
    p2 = StudyProject.objects.create(name="第二项研究", created_by=doctor)
    g2 = StudyGroup.objects.create(project=p2, name="B", target_ratio=1)
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {
            "enrollments": [
                {"project_id": project.id, "group_id": g1.id},
                {"project_id": p2.id, "group_id": g2.id},
            ]
        },
        format="json",
    )
    assert r.status_code == 200, r.data
    assert len(r.data["created"]) == 2
    pp1 = ProjectPatient.objects.get(project=project, patient=patient)
    pp2 = ProjectPatient.objects.get(project=p2, patient=patient)
    assert pp1.group_id == g1.id
    assert pp2.group_id == g2.id


@pytest.mark.django_db
def test_enroll_projects_rejects_existing_link(doctor, patient, project):
    g = StudyGroup.objects.create(project=project, name="A", target_ratio=1)
    ProjectPatient.objects.create(project=project, patient=patient, group=g)
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {"enrollments": [{"project_id": project.id, "group_id": g.id}]},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_enroll_projects_rejects_group_not_in_project(doctor, patient, project):
    other = StudyProject.objects.create(name="他项目", created_by=doctor)
    g_other = StudyGroup.objects.create(project=other, name="X", target_ratio=1)
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {"enrollments": [{"project_id": project.id, "group_id": g_other.id}]},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_enroll_projects_rejects_inactive_group(doctor, patient, project):
    group = StudyGroup.objects.create(
        project=project,
        name="停用组",
        target_ratio=1,
        is_active=False,
    )
    client = APIClient()
    client.force_authenticate(user=doctor)

    r = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {"enrollments": [{"project_id": project.id, "group_id": group.id}]},
        format="json",
    )

    assert r.status_code == 400
    assert "分组已停用" in str(r.data)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()


@pytest.mark.django_db
def test_enroll_projects_rejects_completed_project(doctor, patient, project):
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])
    group = StudyGroup.objects.create(project=project, name="A", target_ratio=100)
    client = APIClient()
    client.force_authenticate(user=doctor)

    response = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {"enrollments": [{"project_id": project.id, "group_id": group.id}]},
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()


@pytest.mark.django_db
def test_enroll_projects_rejects_duplicate_project_in_same_payload(
    doctor, patient, project
):
    g1 = StudyGroup.objects.create(project=project, name="A", target_ratio=50)
    g2 = StudyGroup.objects.create(project=project, name="B", target_ratio=50)
    client = APIClient()
    client.force_authenticate(user=doctor)

    response = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {
            "enrollments": [
                {"project_id": project.id, "group_id": g1.id},
                {"project_id": project.id, "group_id": g2.id},
            ]
        },
        format="json",
    )

    assert response.status_code == 400
    assert "重复项目" in str(response.data)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()


@pytest.mark.django_db
def test_enroll_projects_rejects_unknown_project(doctor, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {"enrollments": [{"project_id": 999999, "group_id": 1}]},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_enroll_projects_rejects_unknown_group(doctor, patient, project):
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/patients/{patient.id}/enroll-projects/",
        {"enrollments": [{"project_id": project.id, "group_id": 999999}]},
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
