import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.visits.services import ensure_default_visits


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _patient(doctor, name="患者乙", phone="13900000222"):
    return Patient.objects.create(name=name, phone=phone, primary_doctor=doctor)


@pytest.mark.django_db
def test_complete_project_sets_archived_and_is_idempotent(doctor, project):
    client = _client(doctor)

    first = client.post(f"/api/studies/projects/{project.id}/complete/")
    assert first.status_code == 200, first.data
    assert first.data["status"] == StudyProject.Status.ARCHIVED

    project.refresh_from_db()
    assert project.status == StudyProject.Status.ARCHIVED

    second = client.post(f"/api/studies/projects/{project.id}/complete/")
    assert second.status_code == 200, second.data
    assert second.data["status"] == StudyProject.Status.ARCHIVED


@pytest.mark.django_db
def test_completed_project_rejects_confirm_grouping_without_saving_ratios(doctor, project):
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=50)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=50)
    patient = _patient(doctor)

    response = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "group_ratios": [
                {"group_id": g1.id, "target_ratio": 60},
                {"group_id": g2.id, "target_ratio": 40},
            ],
            "assignments": [{"patient_id": patient.id, "group_id": g1.id}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    g1.refresh_from_db()
    g2.refresh_from_db()
    assert (g1.target_ratio, g2.target_ratio) == (50, 50)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()


@pytest.mark.django_db
def test_completed_project_rejects_group_create_update_and_delete(doctor, project):
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=100)
    client = _client(doctor)

    create_response = client.post(
        "/api/studies/groups/",
        {
            "project": project.id,
            "name": "新增组",
            "description": "",
            "target_ratio": 100,
            "sort_order": 1,
            "is_active": True,
        },
        format="json",
    )
    assert create_response.status_code == 400
    assert "项目已完结" in str(create_response.data)
    assert not StudyGroup.objects.filter(project=project, name="新增组").exists()

    update_response = client.patch(
        f"/api/studies/groups/{group.id}/",
        {"name": "修改后"},
        format="json",
    )
    assert update_response.status_code == 400
    assert "项目已完结" in str(update_response.data)
    group.refresh_from_db()
    assert group.name == "干预组"

    delete_response = client.delete(f"/api/studies/groups/{group.id}/")
    assert delete_response.status_code == 400
    assert "项目已完结" in str(delete_response.data)
    assert StudyGroup.objects.filter(id=group.id).exists()


@pytest.mark.django_db
def test_completed_project_rejects_moving_group_into_completed_project(doctor, project):
    completed = StudyProject.objects.create(
        name="已完结项目",
        status=StudyProject.Status.ARCHIVED,
        created_by=doctor,
    )
    group = StudyGroup.objects.create(project=project, name="开放项目组", target_ratio=100)

    response = _client(doctor).patch(
        f"/api/studies/groups/{group.id}/",
        {"project": completed.id},
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    group.refresh_from_db()
    assert group.project_id == project.id


@pytest.mark.django_db
def test_completed_project_rejects_unbind_project_patient(doctor, project, patient):
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=100)
    project_patient = ProjectPatient.objects.create(project=project, patient=patient, group=group)
    ensure_default_visits(project_patient)
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])

    response = _client(doctor).post(f"/api/studies/project-patients/{project_patient.id}/unbind/")

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    assert ProjectPatient.objects.filter(id=project_patient.id).exists()


@pytest.mark.django_db
def test_completed_project_readonly_study_endpoints_still_work(doctor, project, patient):
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=100)
    project_patient = ProjectPatient.objects.create(project=project, patient=patient, group=group)
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])
    client = _client(doctor)

    detail_response = client.get(f"/api/studies/projects/{project.id}/")
    assert detail_response.status_code == 200
    assert detail_response.data["status"] == StudyProject.Status.ARCHIVED

    groups_response = client.get("/api/studies/groups/", {"project": project.id})
    assert groups_response.status_code == 200
    assert any(row["id"] == group.id for row in groups_response.data)

    project_patients_response = client.get("/api/studies/project-patients/", {"project": project.id})
    assert project_patients_response.status_code == 200
    assert any(row["id"] == project_patient.id for row in project_patients_response.data)
