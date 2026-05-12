from __future__ import annotations

from typing import Any

from apps.crf.registry_loader import load_crf_registry
from apps.patients.models import PatientBaseline
from apps.visits.models import VisitRecord


def _get_nested(d: Any, path: str) -> Any:
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def _patient_baseline_storage_value(baseline_payload: dict, storage: str) -> Any:
    path = storage.removeprefix("patient_baseline.")
    cur: Any = baseline_payload
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _visit_storage_value(visit: VisitRecord | None, storage: str) -> Any:
    if visit is None:
        return None
    if storage == "visit.visit_date":
        return visit.visit_date
    if storage.startswith("visit.form_data."):
        rel = storage.removeprefix("visit.form_data.")
        return _get_nested(visit.form_data or {}, rel)
    return None


def build_crf_preview(project_patient) -> dict:
    visits = {
        v.visit_type: v
        for v in VisitRecord.objects.filter(project_patient=project_patient)
    }
    missing_fields: list[str] = []
    visit_payload: dict[str, dict] = {}

    for visit_type in ("T0", "T1", "T2"):
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

    reg = load_crf_registry()
    for field in reg.get("fields", []):
        if not field.get("required_for_complete"):
            continue
        storage = field.get("storage")
        if not isinstance(storage, str):
            continue
        label_zh = field.get("label_zh") or field.get("field_id") or storage
        visit_types = field.get("visit_types")

        if storage.startswith("patient_baseline."):
            v = _patient_baseline_storage_value(baseline_payload, storage)
            if _is_missing(v):
                missing_fields.append(f"patient_baseline.{label_zh}")
            continue

        if storage == "visit.visit_date" or storage.startswith("visit.form_data."):
            vts = visit_types if isinstance(visit_types, list) and visit_types else []
            for vt in vts:
                visit = visits.get(vt)
                if visit is None:
                    continue
                v = _visit_storage_value(visit, storage)
                if _is_missing(v):
                    missing_fields.append(f"{vt}.{label_zh}")
            continue

    missing_fields = list(dict.fromkeys(missing_fields))

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
