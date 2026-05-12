import pytest

from apps.crf.services.aggregate import build_crf_preview
from apps.patients.models import PatientBaseline
from apps.visits.models import VisitRecord


@pytest.mark.django_db
def test_crf_preview_reports_missing_visit_fields(project_patient):
    preview = build_crf_preview(project_patient)

    assert preview["project_patient_id"] == project_patient.id
    assert "T0.访视日期" in preview["missing_fields"]
    assert "T1.访视日期" in preview["missing_fields"]
    assert "T2.访视日期" in preview["missing_fields"]


@pytest.mark.django_db
def test_crf_preview_reports_missing_visit_assessment_fields(project_patient):
    preview = build_crf_preview(project_patient)
    for vt in ("T0", "T1", "T2"):
        assert f"{vt}.SPPB总分" in preview["missing_fields"]
        assert f"{vt}.MoCA总分" in preview["missing_fields"]


@pytest.mark.django_db
def test_crf_preview_clears_assessment_missing_after_filled(project_patient):
    for vt in ("T0", "T1", "T2"):
        v = VisitRecord.objects.get(project_patient=project_patient, visit_type=vt)
        v.form_data = {
            "assessments": {"sppb": {"total": 9}, "moca": {"total": 22}},
            "computed_assessments": {},
        }
        v.save(update_fields=["form_data"])

    preview = build_crf_preview(project_patient)
    for vt in ("T0", "T1", "T2"):
        assert f"{vt}.SPPB总分" not in preview["missing_fields"]
        assert f"{vt}.MoCA总分" not in preview["missing_fields"]


@pytest.mark.django_db
def test_crf_preview_treats_zero_as_present(project_patient):
    v = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    v.form_data = {
        "assessments": {"sppb": {"total": 0}, "moca": {"total": 0}},
        "computed_assessments": {},
    }
    v.save(update_fields=["form_data"])

    preview = build_crf_preview(project_patient)
    assert "T0.SPPB总分" not in preview["missing_fields"]
    assert "T0.MoCA总分" not in preview["missing_fields"]


@pytest.mark.django_db
def test_crf_preview_returns_empty_patient_baseline_when_absent(project_patient):
    preview = build_crf_preview(project_patient)

    assert "patient_baseline" in preview
    assert preview["patient_baseline"]["subject_id"] == ""
    assert preview["patient_baseline"]["demographics"] == {}

    assert "patient_baseline.受试者编号" in preview["missing_fields"]
    assert "patient_baseline.教育年限（年）" in preview["missing_fields"]


@pytest.mark.django_db
def test_crf_preview_reports_missing_patient_baseline_fields(project_patient, doctor):
    baseline, _ = PatientBaseline.objects.get_or_create(
        patient=project_patient.patient,
        defaults={"created_by": doctor, "updated_by": doctor},
    )

    preview = build_crf_preview(project_patient)
    assert "patient_baseline.受试者编号" in preview["missing_fields"]
    assert "patient_baseline.教育年限（年）" in preview["missing_fields"]

    baseline.subject_id = "S-0001"
    baseline.demographics = {"education_years": 9}
    baseline.updated_by = doctor
    baseline.save()

    preview2 = build_crf_preview(project_patient)
    assert "patient_baseline.受试者编号" not in preview2["missing_fields"]
    assert "patient_baseline.教育年限（年）" not in preview2["missing_fields"]


@pytest.mark.django_db
def test_crf_preview_returns_empty_patient_baseline_when_present_but_all_none(
    project_patient, doctor
):
    baseline, _ = PatientBaseline.objects.get_or_create(
        patient=project_patient.patient,
        defaults={"created_by": doctor, "updated_by": doctor},
    )

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
    assert "patient_baseline.教育年限（年）" in preview["missing_fields"]


@pytest.mark.django_db
def test_crf_preview_normalizes_non_dict_demographics_to_empty_dict(
    project_patient, doctor
):
    baseline, _ = PatientBaseline.objects.get_or_create(
        patient=project_patient.patient,
        defaults={"created_by": doctor, "updated_by": doctor},
    )

    baseline.subject_id = "S-0001"
    baseline.demographics = "bad-demographics"
    project_patient.patient._state.fields_cache["baseline"] = baseline

    preview = build_crf_preview(project_patient)

    assert preview["patient_baseline"]["demographics"] == {}
    assert "patient_baseline.教育年限（年）" in preview["missing_fields"]
