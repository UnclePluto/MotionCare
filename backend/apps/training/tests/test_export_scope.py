from datetime import date

import pytest
from django.http import Http404
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.training.export_scope import authorize_export, resolve_export_filter


def test_last_seven_days_are_inclusive():
    value = resolve_export_filter({"project_patient": 8, "range": "7d"}, today=date(2026, 9, 9))
    assert (value.start_date, value.end_date) == (date(2026, 9, 3), date(2026, 9, 9))


@pytest.mark.parametrize(
    "data",
    [
        {"range": "custom"},
        {"range": "custom", "start_date": "2026-09-01"},
        {"range": "30d", "start_date": "2026-09-01"},
        {"range": "all", "end_date": "2026-09-01"},
        {"range": "custom", "start_date": "bad", "end_date": "2026-09-09"},
        {"range": "custom", "start_date": "2026-09-01", "end_date": "2026-09-10"},
        {"range": "custom", "start_date": "2026-09-08", "end_date": "2026-09-07"},
        {"range": "weekly"},
        {"project_patient": 0},
        {"video": 2},
        {"device": 3},
    ],
)
def test_invalid_scope_rejected(data):
    with pytest.raises(ValidationError):
        resolve_export_filter({"project_patient": 8, **data}, today=date(2026, 9, 9))


def test_default_custom_and_all():
    assert resolve_export_filter({"project_patient": 8}, today=date(2026, 9, 9)).start_date == date(
        2026, 8, 11
    )
    assert (
        resolve_export_filter(
            {"project_patient": 8, "range": "all"}, today=date(2026, 9, 9)
        ).end_date
        is None
    )
    assert resolve_export_filter(
        {
            "project_patient": 8,
            "range": "custom",
            "start_date": "2026-09-01",
            "end_date": "2026-09-09",
        },
        today=date(2026, 9, 9),
    ).start_date == date(2026, 9, 1)


@pytest.mark.django_db
def test_authorization_completed_project_and_patient_match(project_patient, doctor):
    project_patient.project.status = "completed"
    project_patient.project.save()
    assert (
        authorize_export(
            doctor, patient_id=project_patient.patient_id, project_patient_id=project_patient.pk
        )
        == project_patient
    )
    with pytest.raises(Http404):
        authorize_export(
            doctor,
            patient_id=project_patient.patient_id + 100,
            project_patient_id=project_patient.pk,
        )


@pytest.mark.django_db
@pytest.mark.parametrize("enforce", [True, False])
def test_authorization_uses_tracking_row_scope(project_patient, settings, enforce):
    settings.TRAINING_HEALTH_ENFORCE_ROW_SCOPE = enforce
    user = User.objects.create_user(phone="13800002222", name="其他医生", role=User.Role.DOCTOR)
    if enforce:
        with pytest.raises(Http404):
            authorize_export(
                user, patient_id=project_patient.patient_id, project_patient_id=project_patient.pk
            )
    else:
        assert (
            authorize_export(
                user, patient_id=project_patient.patient_id, project_patient_id=project_patient.pk
            )
            == project_patient
        )
