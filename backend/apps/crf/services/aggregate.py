from apps.patients.models import PatientBaseline
from apps.visits.models import VisitRecord


REQUIRED_VISIT_FIELDS = {
    "T0": ["visit_date"],
    "T1": ["visit_date"],
    "T2": ["visit_date"],
}

REQUIRED_PATIENT_BASELINE_FIELDS = {
    "subject_id": "patient_baseline.受试者编号",
    "demographics.education_years": "patient_baseline.教育年限",
}

REQUIRED_VISIT_ASSESSMENT_FIELDS: list[tuple[str, str]] = [
    ("assessments.sppb.total", "SPPB总分"),
    ("assessments.moca.total", "MoCA总分"),
]


def _get_nested(d, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def build_crf_preview(project_patient) -> dict:
    visits = {
        visit.visit_type: visit
        for visit in VisitRecord.objects.filter(project_patient=project_patient)
    }
    missing_fields: list[str] = []
    visit_payload: dict[str, dict] = {}

    for visit_type, fields in REQUIRED_VISIT_FIELDS.items():
        visit = visits.get(visit_type)
        if not visit:
            missing_fields.append(f"{visit_type}.访视记录")
            visit_payload[visit_type] = {}
            continue
        visit_payload[visit_type] = {
            "visit_date": visit.visit_date.isoformat() if visit.visit_date else "",
            "status": visit.status,
            "form_data": visit.form_data,
        }
        for field in fields:
            if not getattr(visit, field):
                missing_fields.append(f"{visit_type}.访视日期")

        form_data = visit.form_data or {}
        for path, label in REQUIRED_VISIT_ASSESSMENT_FIELDS:
            v = _get_nested(form_data, path)
            if _is_missing(v):
                missing_fields.append(f"{visit_type}.{label}")

    patient = project_patient.patient
    try:
        baseline = patient.baseline
    except PatientBaseline.DoesNotExist:
        baseline = None

    baseline_payload = {
        "subject_id": (baseline.subject_id or "") if baseline else "",
        "name_initials": (baseline.name_initials or "") if baseline else "",
        "demographics": (
            baseline.demographics
            if (baseline and isinstance(baseline.demographics, dict))
            else {}
        ),
        "surgery_allergy": (baseline.surgery_allergy or {}) if baseline else {},
        "comorbidities": (baseline.comorbidities or {}) if baseline else {},
        "lifestyle": (baseline.lifestyle or {}) if baseline else {},
        "baseline_medications": (baseline.baseline_medications or {}) if baseline else {},
    }

    if not baseline_payload["subject_id"]:
        missing_fields.append(REQUIRED_PATIENT_BASELINE_FIELDS["subject_id"])

    education_years = baseline_payload["demographics"].get("education_years")
    if education_years in (None, ""):
        missing_fields.append(REQUIRED_PATIENT_BASELINE_FIELDS["demographics.education_years"])

    return {
        "project_patient_id": project_patient.id,
        "patient": {
            "name": patient.name,
            "gender": patient.gender,
            "age": patient.age,
            "phone": patient.phone,
        },
        "patient_baseline": baseline_payload,
        "project": {
            "name": project_patient.project.name,
            "crf_template_version": project_patient.project.crf_template_version,
        },
        "group": {
            "name": project_patient.group.name if project_patient.group else "",
        },
        "visits": visit_payload,
        "missing_fields": missing_fields,
    }
