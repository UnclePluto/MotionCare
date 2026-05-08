import pytest

from apps.crf.services.aggregate import build_crf_preview
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

