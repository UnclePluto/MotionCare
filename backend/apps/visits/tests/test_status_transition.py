import pytest
from rest_framework.test import APIClient

from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.visits.models import VisitRecord


@pytest.fixture
def auth_client(doctor):
    client = APIClient()
    client.force_authenticate(user=doctor)
    return client


@pytest.mark.django_db
def test_patch_status_only(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.form_data = {"assessments": {"sppb": {"total": 7}}, "computed_assessments": {}}
    visit.save(update_fields=["form_data"])

    r = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"status": VisitRecord.Status.COMPLETED},
        format="json",
    )
    assert r.status_code == 200, r.content
    visit.refresh_from_db()
    assert visit.status == VisitRecord.Status.COMPLETED
    # Status PATCH should not accidentally clear/overwrite form_data
    assert visit.form_data["assessments"]["sppb"]["total"] == 7


@pytest.mark.django_db
def test_completed_visit_rejects_form_data_patch(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.status = VisitRecord.Status.COMPLETED
    visit.form_data = {"assessments": {"sppb": {"total": 8}}, "computed_assessments": {}}
    visit.save()

    r = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )

    assert r.status_code == 400, r.content
    assert "已完成访视只读" in str(r.data)
    visit.refresh_from_db()
    assert visit.form_data["assessments"]["sppb"]["total"] == 8
    assert visit.status == VisitRecord.Status.COMPLETED


@pytest.mark.django_db
def test_completed_visit_rejects_repeated_completed_patch(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.status = VisitRecord.Status.COMPLETED
    visit.save(update_fields=["status"])

    r = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"status": VisitRecord.Status.COMPLETED},
        format="json",
    )

    assert r.status_code == 400, r.content
    assert "已完成访视只读" in str(r.data)


@pytest.mark.django_db
def test_completed_visit_rejects_put(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.status = VisitRecord.Status.COMPLETED
    visit.visit_date = "2026-05-01"
    visit.form_data = {"assessments": {"sppb": {"total": 8}}, "computed_assessments": {}}
    visit.save()

    r = auth_client.put(
        f"/api/visits/{visit.id}/",
        {
            "project_patient": project_patient.id,
            "visit_type": visit.visit_type,
            "status": VisitRecord.Status.DRAFT,
            "visit_date": "2026-05-02",
            "form_data": {"assessments": {"sppb": {"total": 9}}},
        },
        format="json",
    )

    assert r.status_code == 400, r.content
    assert "已完成访视只读" in str(r.data)
    visit.refresh_from_db()
    assert visit.status == VisitRecord.Status.COMPLETED
    assert visit.visit_date.isoformat() == "2026-05-01"
    assert visit.form_data["assessments"]["sppb"]["total"] == 8


@pytest.mark.django_db
def test_visit_detail_includes_project_status(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")

    response = auth_client.get(f"/api/visits/{visit.id}/")

    assert response.status_code == 200, response.content
    assert response.data["project_id"] == project_patient.project_id
    assert response.data["project_name"] == project_patient.project.name
    assert response.data["project_status"] == project_patient.project.status


@pytest.mark.django_db
def test_completed_project_rejects_visit_patch(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    project = project_patient.project
    project.status = "archived"
    project.save(update_fields=["status"])

    response = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    visit.refresh_from_db()
    assert visit.form_data == {}


@pytest.mark.django_db
def test_completed_project_rejects_visit_put(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    project = project_patient.project
    project.status = "archived"
    project.save(update_fields=["status"])

    response = auth_client.put(
        f"/api/visits/{visit.id}/",
        {
            "project_patient": project_patient.id,
            "visit_type": visit.visit_type,
            "status": VisitRecord.Status.COMPLETED,
            "visit_date": "2026-05-13",
            "form_data": {"assessments": {"sppb": {"total": 9}}},
        },
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    visit.refresh_from_db()
    assert visit.status == VisitRecord.Status.DRAFT
    assert visit.visit_date is None
    assert visit.form_data == {}


@pytest.mark.django_db
def test_completed_project_rejects_moving_visit_to_completed_project_patient(
    auth_client,
    doctor,
    project_patient,
    patient,
):
    completed_project = StudyProject.objects.create(
        name="已完结研究",
        status=StudyProject.Status.ARCHIVED,
        created_by=doctor,
    )
    completed_group = StudyGroup.objects.create(project=completed_project, name="历史组", target_ratio=100)
    completed_project_patient = ProjectPatient.objects.create(
        project=completed_project,
        patient=patient,
        group=completed_group,
    )
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")

    response = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"project_patient": completed_project_patient.id},
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    visit.refresh_from_db()
    assert visit.project_patient_id == project_patient.id
