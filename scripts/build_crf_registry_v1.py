#!/usr/bin/env python3
"""Generate specs/patient-rehab-system/crf/registry.v1.json from CRF docx dump.

真源：docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx
对照：specs/patient-rehab-system/crf/_docx_table_dump.txt（由 dump_crf_docx_tables.py 生成）

运行：python scripts/build_crf_registry_v1.py
输出：specs/patient-rehab-system/crf/registry.v1.json
"""

from __future__ import annotations

import json
from pathlib import Path

from crf_registry.baseline_fields import (
    TABLE_TITLES,
    BASELINE_SECTION_ORDER,
    baseline_table_layout,
    build_baseline_fields,
)
from crf_registry.visit_fields import VISIT_TABLE_TITLES, build_visit_fields
from crf_registry.source_slots import SOURCE_SHA256, build_source_slots


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "specs/patient-rehab-system/crf/registry.v1.json"


def main() -> None:
    fields = build_baseline_fields()

    fields.extend(build_visit_fields())

    document_bindings = []
    clinical = []
    for field in fields:
        if field['field_id'].startswith('doc_revision_'):
            document_bindings.append({'binding_id': field['field_id'], 'kind': 'template_static', 'source_positions': field['source_positions']})
            continue
        if field['field_id'] in {'doc_protocol_number', 'doc_enrolled_on', 'doc_investigator_name'}:
            key = field['storage'].split('.')[-1]
            field.update(storage=f'visit.form_data.crf.cover.{key}', visit_types=['T0'], table_ref='study_cover', section='study_cover')
            field.setdefault('validation', {})
            field.setdefault('visible_when', None)
            field.setdefault('required_when', None)
            field['metadata']['storage'] = 'visit.form_data.crf._field_meta'
            field['metadata']['key'] = field['storage']
        if field.get('metadata'):
            field['metadata']['reason_required_for_handled'] = False
        if field['storage'] == 'visit.visit_date':
            field['date_answer_storage'] = 'visit.form_data.crf.meta.visit_date_answer'
        if field['storage'] in {'patient_baseline.subject_id', 'patient_baseline.name_initials'}:
            field.pop('metadata', None)
        clinical.append(field)
    fields = clinical
    layout = baseline_table_layout()
    baseline_ids = {f['field_id'] for f in fields if not f.get('visit_types')}
    for block in layout.values():
        block['rows'] = [{'cells':[c for c in row['cells'] if c.get('field_id') in baseline_ids]} for row in block['rows']]
        block['rows'] = [row for row in block['rows'] if row['cells']]
    doc = {
        "template_id": "cognitive_frailty_digital_therapy_crf",
        "template_revision": "1.1",
        "schema_revision": 3,
        "source_docx_sha256": SOURCE_SHA256,
        "source_docx": "docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx",
        "table_titles": {**TABLE_TITLES, **VISIT_TABLE_TITLES, "study_cover": "研究信息", "#T0": "基本标识"},
        "document_bindings": document_bindings,
        "baseline_section_order": [k for k in BASELINE_SECTION_ORDER if k != "#T1"],
        "baseline_table_layout": {k:v for k,v in layout.items() if k != "#T1"},
        "fields": fields,
    }
    source_slots = build_source_slots(ROOT / doc["source_docx"])
    OUT.with_name("source_slots.v1.json").write_text(
        json.dumps(source_slots, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Wrote", OUT, "fields:", len(fields))


if __name__ == "__main__":
    main()
