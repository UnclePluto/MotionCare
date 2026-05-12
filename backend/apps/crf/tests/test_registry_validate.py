import pytest

from apps.crf.registry_validate import (
    validate_patient_baseline_payload,
    validate_visit_form_data_patch,
)


@pytest.mark.django_db
def test_validate_patient_baseline_partial_ok():
    errors = validate_patient_baseline_payload({"demographics": {"education_years": 12}})

    assert errors == {}


@pytest.mark.django_db
def test_validate_patient_baseline_bad_type():
    errors = validate_patient_baseline_payload({"demographics": {"education_years": True}})

    assert errors
    assert "demographics.education_years" in errors


@pytest.mark.django_db
def test_validate_visit_frailty_invalid_enum():
    errors = validate_visit_form_data_patch(
        {"assessments": {"frailty": "bad"}},
        visit_type="T0",
    )

    assert errors
    assert "assessments.frailty" in errors
