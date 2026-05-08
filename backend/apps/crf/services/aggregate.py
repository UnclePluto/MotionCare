from apps.visits.models import VisitRecord


REQUIRED_VISIT_FIELDS = {
    "T0": ["visit_date"],
    "T1": ["visit_date"],
    "T2": ["visit_date"],
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
    # 0 / 0.0 / False 不视为缺失；空字符串、空容器、None 视为缺失
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
    return {
        "project_patient_id": project_patient.id,
        "patient": {
            "name": patient.name,
            "gender": patient.gender,
            "age": patient.age,
            "phone": patient.phone,
        },
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

