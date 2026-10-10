"""独立原位验收与访视存储兼容合约。"""

import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
from crf_registry.schema import validate_registry_contract  # noqa: E402
from crf_registry.source_slots import build_source_slots  # noqa: E402


def registry():
    return json.loads((ROOT / "specs/patient-rehab-system/crf/registry.v1.json").read_text())


def manifest():
    return build_source_slots(ROOT / "docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx")


def walk(fields):
    for field in fields:
        yield field
        yield from walk(field.get("children", []))


def test_every_original_slot_has_a_renderable_and_exportable_binding():
    assert validate_registry_contract(registry(), manifest()) == []


def test_t1_t2_bindings_target_their_own_tables():
    fields = {f["field_id"]: f for f in registry()["fields"]}
    for vt, dt, pt, mt in [("T0", 3, 13, 14), ("T1", 15, 17, 18), ("T2", 22, 24, 25)]:
        for fid, table, row in [
            (f"vd_{vt}_visit_date", dt, 1),
            (f"as_{vt}_sppb_gait", pt, 3),
            (f"as_{vt}_moca_total", mt, 9),
        ]:
            field = fields[fid]
            assert field["doc_table_index"] == table
            assert [
                (p["table_index"], p["row_index"], p["visit_type"])
                for p in field["source_positions"]
            ] == [(table, row, vt)]


def test_old_assessment_paths_and_text_are_preserved():
    fields = {f["field_id"]: f for f in registry()["fields"]}
    for vt in ["T0", "T1", "T2"]:
        for suffix, path in [
            ("sppb_balance", "sppb.balance"),
            ("sppb_gait", "sppb.gait"),
            ("sppb_chair", "sppb.chair_stand"),
            ("sppb_total", "sppb.total"),
            ("tug", "tug_seconds"),
            ("grip", "grip_strength_kg"),
            ("frailty", "frailty"),
            ("moca_total", "moca.total"),
            ("moca_naming", "moca.subscores.naming"),
        ]:
            assert fields[f"as_{vt}_{suffix}"]["storage"] == "visit.form_data.assessments." + path
    for fid, path in [
        ("scr_t0_icf", "screening.icf"),
        ("scr_t0_inclusion", "screening.inclusion"),
        ("scr_t0_exclusion", "screening.exclusion"),
        ("scr_t0_enrollment", "screening.enrollment"),
        ("crf_completion", "completion"),
        ("crf_qc", "qc"),
        ("crf_med_change_note_t1", "medication_change.note"),
        ("crf_ae_note_t2", "adverse_events.note"),
        ("sat_T1_matrix_note", "satisfaction.matrix_note"),
        ("adh_T1_planned", "adherence.planned"),
    ]:
        field = fields[fid]
        assert field["storage"] == "visit.form_data.crf." + path
        assert field.get("legacy") is True
        assert field["include_in_completeness"] is False
        assert field["source_positions"] == []


def test_scores_have_precise_domains_and_explicit_cross_field_rules():
    fields = {f["field_id"]: f for f in registry()["fields"]}
    for vt in ["T0", "T1", "T2"]:
        for suffix, maximum in [
            ("sppb_balance", 4),
            ("sppb_gait", 4),
            ("sppb_chair", 4),
            ("sppb_total", 12),
            ("moca_visuospatial", 5),
            ("moca_naming", 3),
            ("moca_attention", 6),
            ("moca_language", 3),
            ("moca_abstraction", 2),
            ("moca_delayed_recall", 5),
            ("moca_orientation", 6),
            ("moca_education_bonus", 1),
            ("moca_total", 30),
        ]:
            validation = fields[f"as_{vt}_{suffix}"].get("validation", {})
            assert (validation.get("min"), validation.get("max"), validation.get("integer")) == (
                0,
                maximum,
                True,
            )
        assert fields[f"as_{vt}_sppb_total"]["validation"]["consistency"]["operation"] == "sum"
        assert fields[f"as_{vt}_moca_total"]["validation"]["consistency"]["cap"] == 30
    for vt in ["T1", "T2"]:
        sat = {f["storage"]: f for f in fields.values() if f.get("visit_types") == [vt]}
        total = sat["visit.form_data.crf.satisfaction.total"]
        assert (total["validation"]["min"], total["validation"]["max"]) == (5, 25)
        assert len(total["validation"]["consistency"]["operands"]) == 5
        assert (
            "visit.form_data.crf.satisfaction.overall_score"
            not in total["validation"]["consistency"]["operands"]
        )
        for item in ["operation", "clarity", "reminders", "burden", "recommendation"]:
            score = sat[f"visit.form_data.crf.satisfaction.items.{item}.score"]
            assert (score["validation"]["min"], score["validation"]["max"]) == (1, 5)
            assert (
                sat[f"visit.form_data.crf.satisfaction.items.{item}.remark"][
                    "include_in_completeness"
                ]
                is False
            )


def test_repeat_children_have_relative_paths_and_explicit_combined_output():
    data = registry()
    fields = {f["storage"]: f for f in data["fields"] if f.get("visit_types") == ["T1"]}
    for path in ["medication_change", "adverse_events"]:
        parent = fields[f"visit.form_data.crf.{path}.entries"]
        assert parent["widget"] == "table_repeat"
        assert parent["row_id_key"] == "_row_id"
        assert parent["row_metadata_key"] == "_field_meta"
        assert "max_items" not in parent.get("validation", {})
        for child in parent["children"]:
            assert "." not in child["storage"]
            assert child["metadata"]["storage"] == "_field_meta"
            assert child["metadata"]["key"] == child["storage"]
    ae = fields["visit.form_data.crf.adverse_events.entries"]
    columns = {f["storage"]: f for f in ae["children"]}
    assert columns["severity"]["options"] == ["轻", "中", "重"]
    assert columns["is_sae"]["options"] == ["否", "是"]
    assert columns["relatedness"]["options"] == ["无关", "可能", "很可能"]
    for key in ["management_note", "outcome_note"]:
        assert columns[key]["source_positions"][0]["slot_id"] == "T21.R02.S05"
    assert validate_registry_contract(data, manifest()) == []
    broken = copy.deepcopy(data)
    for field in walk(broken["fields"]):
        field.pop("source_combination", None)
    assert any("歧义" in error for error in validate_registry_contract(broken, manifest()))


def test_structured_screening_completion_and_state_contracts():
    visit = [f for f in registry()["fields"] if f["storage"].startswith("visit.")]
    paths = {f["storage"]: f for f in visit}
    for prefix in [
        "screening.icf_record.",
        "screening.inclusion_items.",
        "screening.exclusion_items.",
        "screening.enrollment_record.",
        "meta.",
        "completion_record.",
        "qc_record.",
    ]:
        assert any(path.startswith("visit.form_data.crf." + prefix) for path in paths)
    for field in visit:
        assert {
            "source_positions",
            "section",
            "ui_label",
            "widget",
            "storage",
            "visit_types",
            "validation",
            "visible_when",
            "required_when",
        } <= set(field), field["field_id"]
        if not field.get("legacy"):
            assert field["metadata"]["storage"] == "visit.form_data.crf._field_meta"
    completion = paths["visit.form_data.crf.completion_record.status"]
    assert completion["visit_types"] == ["T0", "T1", "T2"]
    assert completion["export_visit_selection"] == "latest_recorded_with_conflict_check"
    assert (
        paths["visit.visit_date"]["partial_date_storage"]
        == "visit.form_data.crf.meta.visit_date_parts"
    )


def test_conditional_reasons_and_optional_notes_are_distinguished():
    fields = {f["storage"]: f for f in registry()["fields"] if f.get("visit_types") == ["T1"]}
    for path, parent, value in [
        ("meta.out_of_window_reason", "meta.in_window", "否"),
        ("adherence.decline_reason", "adherence.accept_continue", "否"),
        ("adherence.incomplete_other_remark", "adherence.incomplete_reason", "其他"),
        ("adherence.investigator_other_remark", "adherence.investigator_action", "其他"),
    ]:
        field = fields["visit.form_data.crf." + path]
        assert field["include_in_completeness"] is True
        trigger = field["required_when"]
        if path == "adherence.incomplete_other_remark":
            trigger = trigger["all"][1]
        assert trigger == {
            "storage": "visit.form_data.crf." + parent,
            "op": "eq",
            "value": value,
        }
    for field in walk(registry()["fields"]):
        if field.get("widget") == "number" and field["storage"].startswith("visit."):
            assert field["validation"]["min"] >= 0
            assert field["validation"]["finite"] is True


def test_every_source_binding_is_individually_required_including_combination_members():
    data, source = registry(), manifest()
    count = 0
    for field in walk(data["fields"]):
        positions = field.get("source_positions", [])
        for index in range(len(positions)):
            removed = positions.pop(index)
            assert any(
                removed["slot_id"] in error for error in validate_registry_contract(data, source)
            ), removed["slot_id"]
            positions.insert(index, removed)
            count += 1
    for binding in data['document_bindings']:
        removed=binding['source_positions'].pop()
        assert any(removed['slot_id'] in error for error in validate_registry_contract(data,source))
        binding['source_positions'].append(removed)
        count+=1
    assert count == 567


def test_shared_subject_identifier_is_not_a_second_editable_visit_value():
    from crf_registry.baseline_fields import build_baseline_fields

    data = registry()
    fields = {f["field_id"]: f for f in data["fields"]}
    for vt in ["T0", "T1", "T2"]:
        alias = fields[f"vd_{vt}_subject_id"]
        assert alias["storage"] == alias["canonical_storage"] == "patient_baseline.subject_id"
        assert alias["edit_scope"] == "patient_baseline"
        assert "metadata" not in alias
    old_ids={f['field_id'] for f in build_baseline_fields() if not f['field_id'].startswith('doc_')}
    assert {f['field_id'] for f in data['fields'] if not f.get('visit_types')} == old_ids


def test_legacy_t0_rate_remains_numeric_and_legacy_labels_remain_original():
    fields = {f["field_id"]: f for f in registry()["fields"]}
    assert fields["adh_T0_completion_rate"]["widget"] == "number"
    assert fields["as_T1_moca_naming"]["label_zh"] == "MoCA 命名（原始分）"
    assert fields["as_T1_moca_naming"]["ui_label"] == "命名"


def test_invalid_combination_order_is_not_silently_accepted():
    data = registry()
    member = next(f for f in walk(data["fields"]) if f.get("source_combination"))
    member["source_combination"]["order"] = 99
    assert any("歧义" in error for error in validate_registry_contract(data, manifest()))


def test_completed_adherence_does_not_activate_stale_incomplete_reasons():
    fields = {f["field_id"]: f for f in registry()["fields"]}
    # ne 100 在真实值100时为假，仍保留明确已完成时隐藏旧原因的回归。
    expected = {
        "storage": "visit.form_data.crf.adherence.completion_rate",
        "op": "ne",
        "value": 100,
    }
    assert fields["adh_T1_incomplete_reason"]["visible_when"] == expected
    assert fields["adh_T2_incomplete_other_remark"]["visible_when"]["all"][0] == expected


def test_contract_rejects_nonrenderable_or_wrong_visit_binding():
    data = registry()
    bound = next(f for f in data["fields"] if f["field_id"] == "as_T1_sppb_gait")
    bound["widget"] = "opaque_blob"
    assert any("不可渲染" in error for error in validate_registry_contract(data, manifest()))
    bound["widget"] = "number"
    bound["visit_types"] = ["T0"]
    assert any("访视不符" in error for error in validate_registry_contract(data, manifest()))
    bound["visit_types"] = ["T1"]
    bound["doc_table_index"] = 13
    assert any("表号不符" in error for error in validate_registry_contract(data, manifest()))


def test_negative_weight_loss_judgment_does_not_hide_actual_measurements():
    fields = {f["field_id"]: f for f in registry()["fields"]}
    # 阈值阴性（例如2kg、3%）不改变原始测量的适用性，三次访视均一样。
    for vt in ["T0", "T1", "T2"]:
        for key in ["weight_loss_kg", "weight_loss_percent"]:
            field = fields[f"as_{vt}_physical_frailty_{key}"]
            assert field["visible_when"] is None
            assert field["required_when"] is None
            assert field["source_positions"]


def test_missing_or_unknown_rate_allows_known_reason_without_requiring_a_guess():
    fields = {f["field_id"]: f for f in registry()["fields"]}
    rate = "visit.form_data.crf.adherence.completion_rate"
    for vt in ["T1", "T2"]:
        reason = fields[f"adh_{vt}_incomplete_reason"]
        # Task4将缺失/unknown/not_applicable父值正规化为不可用值；ne100仍可见，present为假。
        assert reason["visible_when"] == {"storage": rate, "op": "ne", "value": 100}
        assert reason["required_when"] == {
            "all": [
                {"storage": rate, "op": "present", "value": None},
                {"storage": rate, "op": "ne", "value": 100},
            ]
        }
        other = fields[f"adh_{vt}_incomplete_other_remark"]
        expected = {
            "all": [
                {"storage": rate, "op": "ne", "value": 100},
                {
                    "storage": "visit.form_data.crf.adherence.incomplete_reason",
                    "op": "eq",
                    "value": "其他",
                },
            ]
        }
        assert other["visible_when"] == other["required_when"] == expected
        assert other["include_in_completeness"] is True


def test_low_activity_printed_standard_does_not_require_an_other_basis():
    fields = {f["field_id"]: f for f in registry()["fields"]}
    for vt in ["T0", "T1", "T2"]:
        # 已按男性<2.5h/周等原标准判阳性，不需要编造其他依据；阴性时仍允许补充。
        field = fields[f"as_{vt}_physical_frailty_low_activity_basis"]
        assert field["include_in_completeness"] is False
        assert field["visible_when"] is None
        assert field["required_when"] is None
        assert field["ui_label"] == "低体力活动其他依据"
        assert field["source_positions"][0]["row_index"] == 11


def test_cesd_label_keeps_the_original_one_week_observation_window():
    fields = {f["field_id"]: f for f in registry()["fields"]}
    for vt in ["T0", "T1", "T2"]:
        assert "近1周" in fields[f"as_{vt}_physical_frailty_cesd_frequency"]["ui_label"]
