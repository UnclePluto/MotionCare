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


def test_other_requires_remark_when_required(monkeypatch):
    fake = {
        "fields": [
            {
                "field_id": "t",
                "widget": "single_choice",
                "storage": "patient_baseline.demographics.ethnicity",
                "options": ["汉族", "其他"],
                "required_for_complete": True,
                "other_remark_storage": "patient_baseline.demographics.ethnicity_other_remark",
            }
        ]
    }

    def _load():
        return fake

    monkeypatch.setattr("apps.crf.registry_validate.load_crf_registry", _load)
    errors = validate_patient_baseline_payload(
        {"demographics": {"ethnicity": "其他", "ethnicity_other_remark": ""}}
    )
    assert "demographics.ethnicity_other_remark" in errors


def test_other_remark_ok_when_filled(monkeypatch):
    fake = {
        "fields": [
            {
                "field_id": "t",
                "widget": "single_choice",
                "storage": "patient_baseline.demographics.ethnicity",
                "options": ["汉族", "其他"],
                "required_for_complete": True,
                "other_remark_storage": "patient_baseline.demographics.ethnicity_other_remark",
            }
        ]
    }

    monkeypatch.setattr(
        "apps.crf.registry_validate.load_crf_registry",
        lambda: fake,
    )
    errors = validate_patient_baseline_payload(
        {"demographics": {"ethnicity": "其他", "ethnicity_other_remark": "说明文字"}}
    )
    assert "demographics.ethnicity_other_remark" not in errors


@pytest.mark.django_db
def test_validate_visit_frailty_invalid_enum():
    errors = validate_visit_form_data_patch(
        {"assessments": {"frailty": "bad"}},
        visit_type="T0",
    )

    assert errors
    assert "assessments.frailty" in errors
