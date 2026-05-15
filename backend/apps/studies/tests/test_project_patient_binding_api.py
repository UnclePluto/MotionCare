import re

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.patient_app.models import PatientAppBindingCode, PatientAppSession
from apps.patient_app.services import bind_project_patient_with_code
from apps.studies.models import StudyProject


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_generate_project_patient_binding_code_returns_plain_code_once(
    doctor,
    project_patient,
):
    response = _client(doctor).post(
        f"/api/studies/project-patients/{project_patient.id}/binding-code/"
    )

    assert response.status_code == 201, response.data
    assert re.fullmatch(r"[0-9]{4}", response.data["code"])
    binding = PatientAppBindingCode.objects.get(id=response.data["id"])
    assert binding.project_patient == project_patient
    assert binding.created_by == doctor
    assert binding.code_hash != response.data["code"]
    assert abs(
        binding.expires_at - (binding.created_at + timezone.timedelta(minutes=15))
    ) <= timezone.timedelta(seconds=2)
    assert binding.expires_at.isoformat().replace("+00:00", "Z") == response.data[
        "expires_at"
    ].replace("+00:00", "Z")


@pytest.mark.django_db
def test_regenerating_binding_code_revokes_previous_unused_code(
    doctor,
    project_patient,
):
    client = _client(doctor)
    first = client.post(f"/api/studies/project-patients/{project_patient.id}/binding-code/")
    second = client.post(f"/api/studies/project-patients/{project_patient.id}/binding-code/")

    assert first.status_code == 201, first.data
    assert second.status_code == 201, second.data
    old_binding = PatientAppBindingCode.objects.get(id=first.data["id"])
    new_binding = PatientAppBindingCode.objects.get(id=second.data["id"])
    assert old_binding.revoked_at is not None
    assert new_binding.revoked_at is None


@pytest.mark.django_db
def test_project_patient_binding_status_tracks_code_and_session(
    doctor,
    project_patient,
):
    client = _client(doctor)
    empty = client.get(f"/api/studies/project-patients/{project_patient.id}/binding-status/")

    assert empty.status_code == 200, empty.data
    assert empty.data["has_active_binding_code"] is False
    assert empty.data["has_active_session"] is False
    assert empty.data["binding_code_expires_at"] is None
    assert empty.data["active_session_expires_at"] is None

    created = client.post(f"/api/studies/project-patients/{project_patient.id}/binding-code/")
    with_code = client.get(f"/api/studies/project-patients/{project_patient.id}/binding-status/")

    assert created.status_code == 201, created.data
    assert with_code.status_code == 200, with_code.data
    assert with_code.data["has_active_binding_code"] is True
    assert with_code.data["binding_code_expires_at"] is not None
    assert with_code.data["has_active_session"] is False
    assert "code" not in with_code.data

    bind_project_patient_with_code(created.data["code"], wx_openid="openid-001")
    with_session = client.get(f"/api/studies/project-patients/{project_patient.id}/binding-status/")

    assert with_session.status_code == 200, with_session.data
    assert with_session.data["has_active_binding_code"] is False
    assert with_session.data["has_active_session"] is True
    assert with_session.data["last_bound_at"] is not None
    assert with_session.data["active_session_expires_at"] is not None


@pytest.mark.django_db
def test_revoke_project_patient_binding_deactivates_session_and_unused_code(
    doctor,
    project_patient,
):
    client = _client(doctor)
    used_code = client.post(f"/api/studies/project-patients/{project_patient.id}/binding-code/")
    _, session = bind_project_patient_with_code(used_code.data["code"], wx_openid="openid-001")
    unused_code = client.post(f"/api/studies/project-patients/{project_patient.id}/binding-code/")

    response = client.post(
        f"/api/studies/project-patients/{project_patient.id}/revoke-binding/"
    )

    assert response.status_code == 200, response.data
    session.refresh_from_db()
    used_binding = PatientAppBindingCode.objects.get(id=used_code.data["id"])
    unused_binding = PatientAppBindingCode.objects.get(id=unused_code.data["id"])
    assert session.is_active is False
    assert used_binding.revoked_at is None
    assert unused_binding.revoked_at is not None
    assert not PatientAppSession.objects.filter(
        project_patient=project_patient,
        is_active=True,
    ).exists()


@pytest.mark.django_db
def test_completed_project_rejects_binding_mutations_but_allows_status(
    doctor,
    project_patient,
):
    project_patient.project.status = StudyProject.Status.ARCHIVED
    project_patient.project.save(update_fields=["status"])
    client = _client(doctor)

    status_response = client.get(
        f"/api/studies/project-patients/{project_patient.id}/binding-status/"
    )
    create_response = client.post(
        f"/api/studies/project-patients/{project_patient.id}/binding-code/"
    )
    revoke_response = client.post(
        f"/api/studies/project-patients/{project_patient.id}/revoke-binding/"
    )

    assert status_response.status_code == 200, status_response.data
    assert create_response.status_code == 400
    assert "项目已完结" in str(create_response.data)
    assert revoke_response.status_code == 400
    assert "项目已完结" in str(revoke_response.data)
