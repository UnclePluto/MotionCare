import pytest
from rest_framework.test import APIClient

from apps.visits.models import VisitRecord


@pytest.mark.django_db
def test_get_always_includes_assessments_and_computed_keys(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.form_data = {}
    visit.save(update_fields=["form_data"])

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.get(f"/api/visits/{visit.id}/")
    assert resp.status_code == 200
    form_data = resp.json()["form_data"]
    assert "assessments" in form_data
    assert "computed_assessments" in form_data


@pytest.mark.django_db
def test_patch_drops_external_computed_assessments(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {
            "form_data": {
                "assessments": {"sppb": {"total": 9}},
                "computed_assessments": {"sppb": {"total": 123}},
            }
        },
        format="json",
    )
    assert resp.status_code == 200

    visit.refresh_from_db()
    assert visit.form_data.get("computed_assessments", {}) == {}


@pytest.mark.django_db
def test_patch_without_assessments_does_not_clear_existing(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.form_data = {"assessments": {"sppb": {"balance": 4}}, "computed_assessments": {}}
    visit.save(update_fields=["form_data"])

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {"visit_date": "2026-05-01"},
        format="json",
    )
    assert resp.status_code == 200

    visit.refresh_from_db()
    assert visit.form_data["assessments"]["sppb"]["balance"] == 4


@pytest.mark.django_db
def test_patch_assessments_deep_merge(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.form_data = {"assessments": {"sppb": {"balance": 4}}, "computed_assessments": {}}
    visit.save(update_fields=["form_data"])

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )
    assert resp.status_code == 200

    visit.refresh_from_db()
    assert visit.form_data["assessments"]["sppb"]["balance"] == 4
    assert visit.form_data["assessments"]["sppb"]["total"] == 9


@pytest.mark.django_db
def test_invalid_known_field_type_returns_400_with_path(doctor, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")

    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": "bad"}}}},
        format="json",
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "assessments.sppb.total" in body
