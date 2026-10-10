import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.patients.models import PatientBaseline


@pytest.mark.django_db
def test_get_patient_baseline_creates_and_returns_empty_demographics(doctor, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.get(f"/api/patients/{patient.id}/baseline/")

    assert resp.status_code == 200
    assert resp.data["patient"] == patient.id
    assert resp.data["demographics"] == {}
    assert resp.data["surgery_allergy"] == {}
    assert resp.data["comorbidities"] == {}
    assert resp.data["lifestyle"] == {}
    assert resp.data["baseline_medications"] == {}


@pytest.mark.django_db
def test_patch_patient_baseline_updates_json_fields(doctor, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.patch(
        f"/api/patients/{patient.id}/baseline/",
        data={
            "subject_id": "SUBJ-001",
            "demographics": {"education_years": 16},
            "baseline_medications": {"notes": "ibuprofen"},
        },
        format="json",
    )

    assert resp.status_code == 200
    assert resp.data["subject_id"] == "SUBJ-001"
    assert resp.data["demographics"]["education_years"] == 16
    assert resp.data["baseline_medications"]["notes"] == "ibuprofen"

    resp2 = client.get(f"/api/patients/{patient.id}/baseline/")
    assert resp2.status_code == 200
    assert resp2.data["subject_id"] == "SUBJ-001"
    assert resp2.data["demographics"]["education_years"] == 16
    assert resp2.data["baseline_medications"]["notes"] == "ibuprofen"


@pytest.mark.django_db
def test_baseline_requires_authentication(patient):
    client = APIClient()

    resp = client.get(f"/api/patients/{patient.id}/baseline/")

    assert resp.status_code in {401, 403}


@pytest.mark.django_db
def test_baseline_forbidden_for_non_doctor_role(patient):
    other_user = User.objects.create_user(
        phone="13700002222",
        password="pass123456",
        name="非授权用户",
        role="patient",  # 不在 {super_admin, admin, doctor} 集合内
    )
    client = APIClient()
    client.force_authenticate(user=other_user)

    resp = client.get(f"/api/patients/{patient.id}/baseline/")

    assert resp.status_code == 403


@pytest.mark.django_db
def test_get_baseline_records_created_by_and_updated_by(doctor, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)

    resp = client.get(f"/api/patients/{patient.id}/baseline/")

    assert resp.status_code == 200
    baseline = PatientBaseline.objects.get(patient=patient)
    assert baseline.created_by_id == doctor.id
    assert baseline.updated_by_id == doctor.id


@pytest.mark.django_db
def test_patch_baseline_keeps_updated_by_as_request_user(doctor, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)

    client.get(f"/api/patients/{patient.id}/baseline/")
    resp = client.patch(
        f"/api/patients/{patient.id}/baseline/",
        data={"subject_id": "SUBJ-001"},
        format="json",
    )

    assert resp.status_code == 200
    baseline = PatientBaseline.objects.get(patient=patient)
    assert baseline.updated_by_id == doctor.id


@pytest.mark.django_db
def test_put_baseline_keeps_updated_by_as_request_user(doctor, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)

    client.get(f"/api/patients/{patient.id}/baseline/")
    resp = client.put(
        f"/api/patients/{patient.id}/baseline/",
        data={"subject_id": "SUBJ-001"},
        format="json",
    )

    assert resp.status_code == 200
    baseline = PatientBaseline.objects.get(patient=patient)
    assert baseline.updated_by_id == doctor.id


@pytest.mark.django_db
def test_put_baseline_does_not_clear_unspecified_fields(doctor, patient):
    """PUT 应按 partial 语义处理，不能清空未传字段（避免 CRF 录入数据被误覆盖）。"""
    client = APIClient()
    client.force_authenticate(user=doctor)

    patch_resp = client.patch(
        f"/api/patients/{patient.id}/baseline/",
        data={
            "demographics": {"education_years": 16},
            "baseline_medications": {"notes": "ibuprofen"},
        },
        format="json",
    )
    assert patch_resp.status_code == 200

    put_resp = client.put(
        f"/api/patients/{patient.id}/baseline/",
        data={"subject_id": "SUBJ-002"},
        format="json",
    )
    assert put_resp.status_code == 200
    assert put_resp.data["subject_id"] == "SUBJ-002"
    assert put_resp.data["demographics"] == {"education_years": 16}
    assert put_resp.data["baseline_medications"] == {"notes": "ibuprofen"}

    get_resp = client.get(f"/api/patients/{patient.id}/baseline/")
    assert get_resp.status_code == 200
    assert get_resp.data["subject_id"] == "SUBJ-002"
    assert get_resp.data["demographics"] == {"education_years": 16}
    assert get_resp.data["baseline_medications"] == {"notes": "ibuprofen"}


@pytest.mark.django_db
def test_patch_patient_baseline_invalid_gender_returns_400(doctor, patient):
    client = APIClient()
    client.force_authenticate(user=doctor)

    client.get(f"/api/patients/{patient.id}/baseline/")
    resp = client.patch(
        f"/api/patients/{patient.id}/baseline/",
        data={"demographics": {"gender": "not_an_option"}},
        format="json",
    )

    assert resp.status_code == 400
    assert "demographics.gender" in resp.data
    detail = resp.data["demographics.gender"]
    assert isinstance(detail, (list, str))
    assert "不在可选项" in (detail[0] if isinstance(detail, list) else detail)


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["patch", "put"])
def test_baseline_nested_patch_preserves_existing_and_legacy_values(doctor, patient, method):
    baseline = PatientBaseline.objects.create(
        patient=patient,
        demographics={"gender": "旧选项", "ethnicity": "汉族", "education_years": 12},
        surgery_allergy={"surgery_history": "原始手术文本"},
    )
    client = APIClient()
    client.force_authenticate(doctor)
    response = getattr(client, method)(
        f"/api/patients/{patient.id}/baseline/",
        {"demographics": {"education_years": 16}},
        format="json",
    )
    assert response.status_code == 200, response.data
    baseline.refresh_from_db()
    assert baseline.demographics == {"gender": "旧选项", "ethnicity": "汉族", "education_years": 16}
    assert baseline.surgery_allergy == {"surgery_history": "原始手术文本"}


@pytest.mark.django_db
def test_baseline_null_clears_value_and_literal_metadata_key_is_merged(doctor, patient):
    key = "patient_baseline.demographics.education_years"
    baseline = PatientBaseline.objects.create(
        patient=patient,
        demographics={
            "education_years": 12,
            "_crf_field_meta": {key: {"state": "unknown", "reason": "旧原因"}},
        },
    )
    client = APIClient()
    client.force_authenticate(doctor)
    response = client.patch(
        f"/api/patients/{patient.id}/baseline/",
        {"demographics": {"education_years": None, "_crf_field_meta": {key: {"reason": None}}}},
        format="json",
    )
    assert response.status_code == 200, response.data
    baseline.refresh_from_db()
    assert baseline.demographics == {
        "education_years": None,
        "_crf_field_meta": {key: {"state": "unknown", "reason": None}},
    }


@pytest.mark.django_db
def test_baseline_invalid_patch_rolls_back_other_fields(doctor, patient):
    baseline = PatientBaseline.objects.create(
        patient=patient, subject_id="原编号", demographics={"education_years": 12, "gender": "男"}
    )
    client = APIClient()
    client.force_authenticate(doctor)
    response = client.patch(
        f"/api/patients/{patient.id}/baseline/",
        {"subject_id": "新编号", "demographics": {"education_years": -1}},
        format="json",
    )
    assert response.status_code == 400
    baseline.refresh_from_db()
    assert baseline.subject_id == "原编号"
    assert baseline.demographics == {"education_years": 12, "gender": "男"}


@pytest.mark.django_db
@pytest.mark.parametrize("old", ["历史人口学原文", 7, False])
def test_baseline_structure_patch_cannot_erase_historical_scalar(doctor, patient, old):
    baseline = PatientBaseline.objects.create(
        patient=patient, demographics=old, subject_id="原编号"
    )
    client = APIClient()
    client.force_authenticate(doctor)
    response = client.patch(
        f"/api/patients/{patient.pk}/baseline/",
        {"subject_id": "新编号", "demographics": {"education_years": 12}},
        format="json",
    )
    assert response.status_code == 400, response.data
    assert "demographics" in response.data
    baseline.refresh_from_db()
    assert baseline.demographics == old
    assert baseline.subject_id == "原编号"


@pytest.mark.django_db
@pytest.mark.parametrize("old", ["", None])
def test_baseline_empty_value_allows_initial_structured_entry(doctor, patient, old):
    baseline = PatientBaseline.objects.create(patient=patient, demographics={"document": old})
    client = APIClient()
    client.force_authenticate(doctor)
    response = client.patch(
        f"/api/patients/{patient.pk}/baseline/",
        {"demographics": {"document": {"enrolled_on": "2026-10-08"}}},
        format="json",
    )
    assert response.status_code == 200, response.data
    baseline.refresh_from_db()
    assert baseline.demographics["document"] == {"enrolled_on": "2026-10-08"}


@pytest.mark.django_db
@pytest.mark.parametrize("old", ["2026-10", "2026-10-08"])
def test_baseline_controlled_date_can_switch_to_partial_components(doctor, patient, old):
    baseline = PatientBaseline.objects.create(
        patient=patient, comorbidities={"cm_coronary": {"diagnosed_at": old}}
    )
    parts = {"year": {"state": "value", "value": 2026}, "month": {"state": "unknown"}}
    client = APIClient()
    client.force_authenticate(doctor)
    response = client.patch(
        f"/api/patients/{patient.pk}/baseline/",
        {"comorbidities": {"cm_coronary": {"diagnosed_at": parts}}},
        format="json",
    )
    assert response.status_code == 200, response.data
    baseline.refresh_from_db()
    assert baseline.comorbidities["cm_coronary"]["diagnosed_at"] == parts
