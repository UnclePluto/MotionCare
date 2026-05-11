import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.prescriptions.models import Prescription


@pytest.mark.django_db
def test_prescription_list_excludes_terminated(project_patient, doctor):
    Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    Prescription.objects.create(
        project_patient=project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.TERMINATED,
    )
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.get("/api/prescriptions/")
    assert r.status_code == 200
    ids = {row["id"] for row in r.data}
    active_ids = {p.id for p in Prescription.objects.exclude(status=Prescription.Status.TERMINATED)}
    assert ids == active_ids
