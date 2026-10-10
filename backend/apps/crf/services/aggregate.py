from __future__ import annotations

from django.conf import settings
from docx import Document

from apps.crf.completeness import evaluate_completeness
from apps.crf.registry_loader import check_crf_assets, load_crf_registry
from apps.patients.models import PatientBaseline
from apps.visits.models import VisitRecord


def build_crf_preview(project_patient) -> dict:
    visits = {v.visit_type: v for v in VisitRecord.objects.filter(project_patient=project_patient)}
    visit_payload: dict[str, dict] = {}

    for visit_type in ("T0", "T1", "T2"):
        visit = visits.get(visit_type)
        if not visit:
            visit_payload[visit_type] = {}
            continue
        visit_payload[visit_type] = {
            "visit_date": visit.visit_date.isoformat() if visit.visit_date else None,
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
            baseline.demographics if baseline and baseline.demographics is not None else {}
        ),
        "surgery_allergy": baseline.surgery_allergy
        if baseline and baseline.surgery_allergy is not None
        else {},
        "comorbidities": baseline.comorbidities
        if baseline and baseline.comorbidities is not None
        else {},
        "lifestyle": baseline.lifestyle if baseline and baseline.lifestyle is not None else {},
        "baseline_medications": baseline.baseline_medications
        if baseline and baseline.baseline_medications is not None
        else {},
    }

    from apps.crf.services.project_cover import project_cover
    t0 = visit_payload['T0']
    t0['form_data'] = project_cover(project_patient, t0.get('form_data', {}), baseline_payload)
    for payload in visit_payload.values():
        if 'visit_date' in payload:
            from apps.crf.field_values import lookup_path,MISSING,BAD_PARENT
            answer=lookup_path(payload.get('form_data',{}),'crf.meta.visit_date_answer')
            if answer is not MISSING and answer is not BAD_PARENT:payload['visit_date']=answer
    reg = load_crf_registry()
    projection = evaluate_completeness(reg, baseline_payload, visit_payload)
    # Static study schedule is source content, not a patient answer or a count.
    check_crf_assets()
    table = Document(settings.CRF_TEMPLATE_PATH).tables[2]
    flow_rows = [[cell.text for cell in row.cells] for row in table.rows]
    projection["sections"].insert(
        0,
        {
            "key": "study:flow",
            "scope": "study",
            "table_ref": "#T2",
            "title": "研究流程",
            "supplemental": False,
            "fields": [],
            "counts": {"normal": 0, "unknown": 0, "not_applicable": 0, "unresolved": 0},
            "static_table": {"headers": flow_rows[0], "rows": flow_rows[1:]},
        },
    )

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
        **projection,
        "schema_revision": reg["schema_revision"],
        "template_revision": reg["template_revision"],
    }
