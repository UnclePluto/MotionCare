import pytest
from rest_framework.test import APIClient

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
def test_completed_visit_still_editable(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.status = VisitRecord.Status.COMPLETED
    visit.form_data = {"assessments": {"sppb": {"total": 8}}, "computed_assessments": {}}
    visit.save()

    r = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )
    assert r.status_code == 200, r.content
    visit.refresh_from_db()
    assert visit.form_data["assessments"]["sppb"]["total"] == 9
    assert visit.status == VisitRecord.Status.COMPLETED

