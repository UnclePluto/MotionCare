import pytest
from rest_framework.test import APIClient

from apps.visits.models import VisitRecord


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

