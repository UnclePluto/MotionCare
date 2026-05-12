import pytest

from apps.crf.registry_validate import validate_patient_baseline_payload


@pytest.mark.django_db
def test_comorbidity_diagnosed_at_invalid_date_key_matches_storage_path():
    """非法日期字符串时，错误键与 registry storage 去掉 patient_baseline. 前缀一致。"""
    errors = validate_patient_baseline_payload(
        {"comorbidities": {"cm_coronary": {"diagnosed_at": "not-a-date"}}}
    )

    key = "comorbidities.cm_coronary.diagnosed_at"
    assert key in errors
    assert errors[key] == "日期格式应为 YYYY-MM-DD"
