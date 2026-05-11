import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup


@pytest.mark.django_db
def test_cannot_delete_patient_with_project_link(doctor, patient, project):
    group = StudyGroup.objects.create(project=project, name="G1", target_ratio=1)
    ProjectPatient.objects.create(project=project, patient=patient, group=group)

    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.delete(f"/api/patients/{patient.id}/")
    assert r.status_code == 400
    assert "detail" in r.data
    assert Patient.objects.filter(pk=patient.pk).exists()


@pytest.mark.django_db
def test_can_delete_patient_without_project_link(doctor, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)
    pk = patient.pk
    r = client.delete(f"/api/patients/{pk}/")
    assert r.status_code == 204
    assert not Patient.objects.filter(pk=pk).exists()
