import pytest
from rest_framework.test import APIClient

from apps.prescriptions.models import Prescription
from apps.studies.models import ProjectPatient


@pytest.mark.django_db
def test_unbind_terminates_prescriptions_and_removes_link(doctor, project_patient, active_prescription):
    project_patient.grouping_status = ProjectPatient.GroupingStatus.CONFIRMED
    project_patient.save(update_fields=["grouping_status"])

    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/project-patients/{project_patient.id}/unbind/")
    assert r.status_code == 200
    active_prescription.refresh_from_db()
    assert active_prescription.status == Prescription.Status.TERMINATED
    assert active_prescription.project_patient_id is None
    assert not ProjectPatient.objects.filter(pk=project_patient.pk).exists()


@pytest.mark.django_db
def test_unbind_rejects_when_not_confirmed(doctor, project_patient, active_prescription):
    assert project_patient.grouping_status == ProjectPatient.GroupingStatus.PENDING
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/project-patients/{project_patient.id}/unbind/")
    assert r.status_code == 400
    assert ProjectPatient.objects.filter(pk=project_patient.pk).exists()
