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
