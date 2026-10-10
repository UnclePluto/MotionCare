"""以独立原表位置验收，删除绑定、挪错格、合并字段都必须被识别。"""

import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
from crf_registry.source_slots import build_source_slots  # noqa: E402

SOURCE = ROOT / "docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx"
REGISTRY = ROOT / "specs/patient-rehab-system/crf/registry.v1.json"
BASELINE_TABLES = {0, 1, 8, 9, 10, 11, 12}


def test_source_manifest_covers_all_561_original_slots():
    manifest = build_source_slots(SOURCE)
    assert (manifest["table_count"], manifest["row_count"], len(manifest["slots"])) == (
        31,
        265,
        561,
    )
    assert (
        manifest["source_sha256"]
        == "f031dd59a1e169548fe651555d19c41306cc51e6bfcf7eb933edcee86924102a"
    )
    assert len({s["slot_id"] for s in manifest["slots"]}) == 561
    assert not any(s["table_index"] == 2 for s in manifest["slots"])
    by_id = {s["slot_id"]: s for s in manifest["slots"]}
    assert [
        (by_id[f"T10.R01.S{i:02d}"]["cell_index"], by_id[f"T10.R01.S{i:02d}"]["slot_order"])
        for i in range(5)
    ] == [(1, 0), (1, 1), (2, 0), (3, 0), (4, 0)]
    assert by_id["T12.R01.S01"]["options"] == [
        "ACEI",
        "ARB",
        "β受体阻滞剂",
        "钙通道阻滞剂",
        "利尿剂",
        "α受体阻滞剂",
        "其他",
    ]
    assert by_id["T12.R01.S02"]["options"] == []
    assert by_id["T26.R01.S00"]["cell_indices"] == [1, 2, 3, 4, 5]
    assert by_id["T26.R01.S00"]["visit_type"] == "T2"


def iter_fields(fields):
    for field in fields:
        yield field
        yield from iter_fields(field.get("children", []))


def test_baseline_source_slots_have_writable_bindings():
    manifest = build_source_slots(SOURCE)
    fields = list(iter_fields(json.loads(REGISTRY.read_text())["fields"]))
    bindings = {
        b["slot_id"]
        for f in fields
        if f.get("storage") and not f.get("read_only")
        for b in f.get("source_positions", [])
    }
    document_slots={p['slot_id'] for b in json.loads(REGISTRY.read_text()).get('document_bindings',[]) for p in b['source_positions']}
    bindings |= document_slots
    expected = {s["slot_id"] for s in manifest["slots"] if s["table_index"] in BASELINE_TABLES}
    # 独立原表给出191个基线/文档填写位，不能用当前实现字段生成期望。
    assert len(expected) == 191
    assert expected <= bindings, sorted(expected - bindings)


def baseline_manifest():
    manifest = build_source_slots(SOURCE)
    manifest["slots"] = [s for s in manifest["slots"] if s["table_index"] in BASELINE_TABLES]
    return manifest


def test_contract_detects_missing_invalid_and_ambiguous_source_positions():
    from crf_registry.schema import validate_registry_contract

    registry = baseline_registry()
    manifest = baseline_manifest()
    assert validate_registry_contract(registry, manifest) == []
    bound = [f for f in iter_fields(registry["fields"]) if f.get("source_positions")]
    assert bound, "基线必须声明原填写位绑定"
    victim = bound[0]
    removed = victim["source_positions"].pop(0)
    assert any(
        removed["slot_id"] in e and "未绑定" in e
        for e in validate_registry_contract(registry, manifest)
    )
    victim["source_positions"].insert(0, removed)
    removed["cell_index"] = 999
    assert any("位置不符" in e for e in validate_registry_contract(registry, manifest))
    removed["cell_index"] = manifest["slots"][0]["cell_index"]
    duplicate = copy.deepcopy(victim)
    duplicate["field_id"] = "ambiguous_copy"
    registry["fields"].append(duplicate)
    assert any("歧义" in e for e in validate_registry_contract(registry, manifest))


def test_baseline_structures_preserve_legacy_paths_and_original_options():
    from crf_registry.baseline_fields import build_baseline_fields

    fields = {f["field_id"]: f for f in build_baseline_fields()}
    by_path = {f["storage"]: f for f in fields.values()}
    assert "patient_baseline.surgery_allergy.surgery_records" in by_path
    assert (
        fields["sa_surgeries_note"]["storage"] == "patient_baseline.surgery_allergy.surgeries_note"
    )
    surgery = by_path["patient_baseline.surgery_allergy.surgery_records"]
    assert surgery["widget"] == "table_repeat"
    assert {f["storage"] for f in surgery["children"]} == {"name", "date", "hospital_note"}
    assert surgery["row_id_key"] == "_row_id"
    assert fields["cm_coronary_diagnosed_at"]["date_precision"] == "month"
    assert fields["cm_coronary_family_count"]["integer"] is True
    drug = by_path["patient_baseline.baseline_medications.med_antidiabetic.categories"]
    assert drug["widget"] == "multi_choice"
    assert drug["options"] == [
        "磺脲类",
        "双胍类",
        "α-葡萄糖苷酶抑制剂",
        "格列奈类",
        "噻唑烷二酮类",
        "DPP-4抑制剂",
        "SGLT2抑制剂",
        "GLP-1RA",
        "胰岛素",
        "其他",
    ]
    assert "patient_baseline.baseline_medications.med_antidiabetic.other_name" in by_path
    assert "patient_baseline.lifestyle.activity_record.vigorous.days_per_week" in by_path
    assert fields["dm_ethnicity"]["options"][0] == "汉族"
    assert len(fields["dm_ethnicity"]["options"]) == 57
    assert fields["dm_ethnicity"]["export_choice_mapping"]["壮族"] == {
        "value": "其他",
        "other_text": "壮族",
    }
    assert (
        fields["cm_coronary_family"]["metadata"]["storage"]
        == "patient_baseline.demographics._crf_field_meta"
    )
    assert (
        fields["cm_coronary_family"]["metadata"]["key"]
        == "patient_baseline.comorbidities.cm_coronary.family"
    )


def test_contract_rejects_wrong_template_identity():
    from crf_registry.schema import validate_registry_contract

    registry = baseline_registry()
    registry["source_docx_sha256"] = "0" * 64
    assert any("源哈希" in e for e in validate_registry_contract(registry, baseline_manifest()))


def test_removing_each_baseline_binding_is_detected():
    from crf_registry.schema import validate_registry_contract

    registry = baseline_registry()
    manifest = baseline_manifest()
    for f in iter_fields(registry["fields"]):
        positions = f.get("source_positions", [])
        for index in range(len(positions)):
            removed = positions.pop(index)
            assert any(
                removed["slot_id"] in e and "未绑定" in e
                for e in validate_registry_contract(registry, manifest)
            ), removed["slot_id"]
            positions.insert(index, removed)


def test_source_manifest_rejects_a_different_original_document(tmp_path):
    import pytest

    changed = tmp_path / "changed.docx"
    changed.write_bytes(SOURCE.read_bytes() + b"different original")
    with pytest.raises(ValueError, match="原表哈希"):
        build_source_slots(changed)


def test_checked_in_manifest_is_reproducible_from_original():
    manifest = json.loads(REGISTRY.with_name("source_slots.v1.json").read_text())
    assert manifest == build_source_slots(SOURCE)


def baseline_registry():
    registry = json.loads(REGISTRY.read_text())
    registry["fields"] = [
        f
        for f in registry["fields"]
        if f["storage"].startswith("patient_baseline.") and not f.get("visit_types") or f["field_id"] in {"doc_protocol_number","doc_enrolled_on","doc_investigator_name"}
    ]
    return registry


def test_unknown_choices_use_metadata_without_erasing_legacy_options():
    from crf_registry.baseline_fields import build_baseline_fields

    fields = {f["field_id"]: f for f in build_baseline_fields()}
    for fid, old_value in (
        ("cm_coronary_family", "不详"),
        ("cm_coronary_personal", "不详"),
        ("dm_income_band", "拒答/不详"),
        ("dm_income_afford", "不详"),
    ):
        value = fields[fid]
        assert old_value not in value["options"]
        assert old_value in value["legacy_options"]
        assert value.get("legacy_option_states", {}).get(old_value) == "unknown"
        assert "unknown" in value["metadata"]["states"]


def test_optional_notes_do_not_count_as_missing_but_triggered_reasons_do():
    from crf_registry.baseline_fields import build_baseline_fields

    fields = {f["field_id"]: f for f in iter_fields(build_baseline_fields())}
    disease_ids = (
        "cm_coronary",
        "cm_stroke",
        "cm_hypertension",
        "cm_diabetes",
        "cm_hyperlipidemia",
        "cm_gout",
        "cm_copd",
        "cm_asthma",
        "cm_kidney_stone",
        "cm_ckd",
        "cm_anemia",
        "cm_osteo",
        "cm_mood",
        "cm_other",
    )
    optional_ids = [f"{disease}_note" for disease in disease_ids]
    optional_ids += ["cm_other_history", "sa_surgery_records_hospital_note"]
    for fid in optional_ids:
        assert fields[fid]["include_in_completeness"] is False, fid
        assert "required_when" not in fields[fid], fid
        assert fields[fid]["source_positions"], fid
    # 这些说明在触发时必须计入缺失，不能因 text/备注等启发式一并豁免。
    expected_conditions = {
        "dm_marital_other": {
            "storage": "patient_baseline.demographics.marital_status",
            "op": "eq",
            "value": "其他",
        },
        "dm_insurance_other": {
            "storage": "patient_baseline.demographics.insurance_type",
            "op": "eq",
            "value": "其他",
        },
        "cm_gout_attack_treatment": {
            "storage": "patient_baseline.comorbidities.gout_attack_1m",
            "op": "eq",
            "value": "是",
        },
        "med_antihypertensive_other_name": {
            "all": [
                {
                    "storage": "patient_baseline.baseline_medications.med_antihypertensive.uses",
                    "op": "eq",
                    "value": "是",
                },
                {
                    "storage": "patient_baseline.baseline_medications.med_antihypertensive.categories",
                    "op": "contains",
                    "value": "其他",
                },
            ]
        },
    }
    for fid, condition in expected_conditions.items():
        assert fields[fid]["include_in_completeness"] is True, fid
        assert fields[fid]["required_when"] == condition, fid


def test_merged_surgery_date_uses_physical_xml_cell_not_expanded_grid_cell():
    from docx import Document
    from docx.table import _Cell
    from crf_registry.schema import source_position, validate_registry_contract

    manifest = build_source_slots(SOURCE)
    assert manifest.get("index_space") == "xml_tc"
    slot = next(s for s in manifest["slots"] if s["slot_id"] == "T09.R02.S01")
    position = source_position(9, 2, 1, repeat_index=0)
    assert slot.get("index_space") == position.get("index_space") == "xml_tc"
    assert slot["cell_index"] == position["cell_index"] == 1
    table = Document(SOURCE).tables[9]
    row = table.rows[2]
    # row.cells 会按 gridSpan 展开合并格；源坐标必须取 XML 的直接 tc 子节点。
    physical_date = _Cell(row._tr.tc_lst[position["cell_index"]], table)
    assert physical_date.text == "|__|__|__|__|年|__|__|月|__|__|日"
    assert row.cells[1].text == ""
    assert row.cells[2]._tc is physical_date._tc
    assert slot["source_cells"] == [physical_date.text]

    registry = baseline_registry()
    column = next(
        f for f in iter_fields(registry["fields"]) if f["field_id"] == "sa_surgery_records_date"
    )
    column["source_positions"][0]["index_space"] = "layout_grid"
    assert any(
        "index_space" in e for e in validate_registry_contract(registry, baseline_manifest())
    )


def test_document_revision_slots_are_classified_outside_patient_answers():
    from apps.crf.registry_loader import load_crf_registry,load_crf_source_slots
    from crf_registry.schema import validate_registry_contract
    registry=load_crf_registry()
    assert not any(f['field_id'].startswith('doc_revision_') for f in registry['fields'])
    documents=registry['document_bindings']
    assert {p['slot_id'] for b in documents for p in b['source_positions']}=={'T01.R01.S00','T01.R02.S00'}
    assert validate_registry_contract(registry,load_crf_source_slots())==[]
    for fid,key in [('doc_protocol_number','protocol_number'),('doc_enrolled_on','enrolled_on'),('doc_investigator_name','investigator_name')]:
        field=next(f for f in registry['fields'] if f['field_id']==fid)
        assert field['storage']=='visit.form_data.crf.cover.'+key and field['visit_types']==['T0']
