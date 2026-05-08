import pytest

from apps.crf.services.aggregate import build_crf_preview
from apps.patients.models import PatientBaseline


@pytest.mark.django_db
def test_crf_preview_reports_missing_visit_fields(project_patient):
    preview = build_crf_preview(project_patient)

    assert preview["project_patient_id"] == project_patient.id
    assert "T0.访视日期" in preview["missing_fields"]
    assert "T1.访视日期" in preview["missing_fields"]
    assert "T2.访视日期" in preview["missing_fields"]


@pytest.mark.django_db
def test_crf_preview_returns_empty_patient_baseline_when_absent(project_patient):
    preview = build_crf_preview(project_patient)

    assert "patient_baseline" in preview
    assert preview["patient_baseline"]["subject_id"] == ""
    assert preview["patient_baseline"]["demographics"] == {}

    assert "patient_baseline.受试者编号" in preview["missing_fields"]
    assert "patient_baseline.教育年限" in preview["missing_fields"]


@pytest.mark.django_db
def test_crf_preview_reports_missing_patient_baseline_fields(project_patient, doctor):
    baseline, _ = PatientBaseline.objects.get_or_create(
        patient=project_patient.patient,
        defaults={"created_by": doctor, "updated_by": doctor},
    )

    preview = build_crf_preview(project_patient)
    assert "patient_baseline.受试者编号" in preview["missing_fields"]
    assert "patient_baseline.教育年限" in preview["missing_fields"]

    baseline.subject_id = "S-0001"
    baseline.demographics = {"education_years": 9}
    baseline.updated_by = doctor
    baseline.save()

    preview2 = build_crf_preview(project_patient)
    assert "patient_baseline.受试者编号" not in preview2["missing_fields"]
    assert "patient_baseline.教育年限" not in preview2["missing_fields"]


@pytest.mark.django_db
def test_crf_preview_returns_empty_patient_baseline_when_present_but_all_none(
    project_patient, doctor
):
    baseline, _ = PatientBaseline.objects.get_or_create(
        patient=project_patient.patient,
        defaults={"created_by": doctor, "updated_by": doctor},
    )

    # PatientBaseline 当前字段约束为 non-null + default，
    # 但聚合层仍需对历史/异常数据的 None 做归一化。
    baseline.subject_id = None
    baseline.name_initials = None
    baseline.demographics = None
    baseline.surgery_allergy = None
    baseline.comorbidities = None
    baseline.lifestyle = None
    baseline.baseline_medications = None
    project_patient.patient._state.fields_cache["baseline"] = baseline

    preview = build_crf_preview(project_patient)

    assert preview["patient_baseline"] == {
        "subject_id": "",
        "name_initials": "",
        "demographics": {},
        "surgery_allergy": {},
        "comorbidities": {},
        "lifestyle": {},
        "baseline_medications": {},
    }

    assert "patient_baseline.受试者编号" in preview["missing_fields"]
    assert "patient_baseline.教育年限" in preview["missing_fields"]
