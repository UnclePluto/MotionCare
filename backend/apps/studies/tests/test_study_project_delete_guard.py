import pytest
from rest_framework.test import APIClient

from apps.studies.models import ProjectPatient, StudyGroup


@pytest.mark.django_db
def test_cannot_delete_project_with_project_patient(doctor, project, patient):
    g = StudyGroup.objects.create(project=project, name="G", target_ratio=1)
    ProjectPatient.objects.create(project=project, patient=patient, group=g)
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.delete(f"/api/studies/projects/{project.id}/")
    assert r.status_code == 400
    assert "detail" in r.data


@pytest.mark.django_db
def test_can_delete_empty_project(doctor, project):
    client = APIClient()
    client.force_authenticate(user=doctor)
    pk = project.pk
    r = client.delete(f"/api/studies/projects/{pk}/")
    assert r.status_code == 204
