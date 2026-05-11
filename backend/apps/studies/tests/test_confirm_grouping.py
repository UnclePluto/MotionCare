import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup


@pytest.mark.django_db
def test_confirm_grouping_marks_all_pending_as_confirmed(doctor, project, patient):
    g = StudyGroup.objects.create(project=project, name="A", target_ratio=1)
    pp1 = ProjectPatient.objects.create(
        project=project,
        patient=patient,
        group=g,
        grouping_status=ProjectPatient.GroupingStatus.PENDING,
    )
    other = Patient.objects.create(name="乙", phone="13900000222", primary_doctor=doctor)
    pp2 = ProjectPatient.objects.create(
        project=project,
        patient=other,
        group=g,
        grouping_status=ProjectPatient.GroupingStatus.PENDING,
    )

    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/projects/{project.id}/confirm-grouping/", {}, format="json")

    assert r.status_code == 200, r.data
    assert r.data["confirmed"] == 2
    pp1.refresh_from_db()
    pp2.refresh_from_db()
    assert pp1.grouping_status == ProjectPatient.GroupingStatus.CONFIRMED
    assert pp2.grouping_status == ProjectPatient.GroupingStatus.CONFIRMED


@pytest.mark.django_db
def test_confirm_grouping_rejects_pending_without_group(doctor, project, patient):
    ProjectPatient.objects.create(
        project=project,
        patient=patient,
        group=None,
        grouping_status=ProjectPatient.GroupingStatus.PENDING,
    )
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/projects/{project.id}/confirm-grouping/", {}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_confirm_grouping_returns_400_when_no_pending(doctor, project):
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/projects/{project.id}/confirm-grouping/", {}, format="json")
    assert r.status_code == 400
