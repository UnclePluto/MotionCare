from copy import deepcopy

import pytest

from apps.crf.registry_loader import load_crf_registry
from apps.crf.registry_validate import (
    validate_patient_baseline_payload,
    validate_visit_form_data_patch,
)


def put(data, path, value):
    parts = path.split(".")
    for part in parts[:-1]:
        data = data.setdefault(part, {})
    data[parts[-1]] = value


def field(path, visit_type="T1"):
    return next(
        f
        for f in load_crf_registry()["fields"]
        if f["storage"] == path and (not f.get("visit_types") or visit_type in f["visit_types"])
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("assessments.sppb.balance", value)
        for value in [-1, 4.5, 6, True, float("nan"), float("inf")]
    ]
    + [
        ("assessments.moca.total", 31),
        ("assessments.moca.subscores.naming", 4),
        ("assessments.moca.subscores.education_bonus", 2),
        ("crf.satisfaction.items.operation.score", 0),
        ("crf.satisfaction.overall_score", 6),
        ("crf.adherence.completion_rate", 175),
        ("assessments.physical.chair.completed_count", 1.5),
        ("crf.meta.assessed_on", "2026-02-31"),
        ("crf.meta.assessed_on", "2026-13-99"),
        ("crf.adverse_events.has_events", "也许"),
        ("crf.satisfaction.items.operation.remark", 12),
    ],
)
def test_rejects_illegal_new_values(path, value):
    data = {}
    put(data, path, value)
    assert path in validate_visit_form_data_patch(data, "T1")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("assessments.sppb.balance", 0),
        ("assessments.sppb.balance", 4),
        ("assessments.moca.total", 30),
        ("crf.adherence.completion_rate", 100),
        ("crf.satisfaction.overall_score", 1),
        ("crf.satisfaction.overall_score", 5),
        ("crf.meta.assessed_on", "2024-02-29"),
    ],
)
def test_accepts_real_zero_and_boundaries(path, value):
    data = {}
    put(data, path, value)
    assert validate_visit_form_data_patch(data, "T1") == {}


def test_totals_checked_only_when_prerequisites_present():
    assert validate_visit_form_data_patch({"assessments": {"sppb": {"total": 8}}}, "T0") == {}
    data = {"assessments": {"sppb": {"balance": 0, "gait": 3, "chair_stand": 4, "total": 8}}}
    assert "assessments.sppb.total" in validate_visit_form_data_patch(data, "T0")
    data["assessments"]["sppb"]["total"] = 7
    assert validate_visit_form_data_patch(data, "T0") == {}
    del data["assessments"]["sppb"]["gait"]
    assert validate_visit_form_data_patch(data, "T0") == {}


def test_unknown_reason_is_not_a_numeric_score():
    path = "visit.form_data.assessments.sppb.balance"
    data = {
        "assessments": {"sppb": {"balance": 4, "gait": 4, "chair_stand": 4, "total": 5}},
        "crf": {"_field_meta": {path: {"state": "unknown", "reason": "无法测量"}}},
    }
    assert validate_visit_form_data_patch(data, "T0") == {}
    data["assessments"]["sppb"]["balance"] = 99
    assert "assessments.sppb.balance" in validate_visit_form_data_patch(data, "T0")


def test_month_and_partial_dates_preserve_precision():
    from apps.crf.field_values import get_field_value

    path = "patient_baseline.comorbidities.cm_hypertension.diagnosed_at"
    for value in [
        "2026-02",
        "2026-02-28",
        {"year": {"state": "value", "value": 2026}, "month": {"state": "unknown"}},
    ]:
        data = {}
        put(data, path, value)
        before = deepcopy(data)
        assert validate_patient_baseline_payload(data["patient_baseline"]) == {}
        assert get_field_value(data, field(path)) == value
        assert data == before


@pytest.mark.parametrize(
    "value",
    [
        {"year": {"state": "unknown", "value": 2026}},
        {"year": {"state": "value", "value": True}},
        {"month": {"state": "value", "value": 99}},
        {
            "year": {"state": "value", "value": 2026},
            "month": {"state": "value", "value": 2},
            "day": {"state": "value", "value": 29},
        },
        {"month": {"state": "value", "value": 2}, "day": {"state": "value", "value": 30}},
        {"year": 2026},
        {"year": {"state": "not_applicable"}},
        {"minute": 3},
    ],
)
def test_rejects_illegal_partial_components(value):
    assert "crf.meta.assessed_on" in validate_visit_form_data_patch(
        {"crf": {"meta": {"assessed_on": value}}}, "T1"
    )


def test_partial_date_unprocessed_and_leap_year_unknown():
    value = {
        "year": None,
        "month": {"state": "value", "value": 2},
        "day": {"state": "value", "value": 29},
    }
    assert validate_visit_form_data_patch({"crf": {"meta": {"assessed_on": value}}}, "T1") == {}


@pytest.mark.parametrize(
    ("rate", "state", "visible", "required"),
    [
        (100, None, False, False),
        (0, None, True, True),
        (75, None, True, True),
        (None, None, True, False),
        (100, "unknown", True, False),
        (100, "not_applicable", True, False),
        ("旧文本", None, True, False),
        (175, None, True, False),
    ],
)
def test_actual_adherence_conditions(rate, state, visible, required):
    from apps.crf.field_rules import evaluate_condition

    path = "visit.form_data.crf.adherence."
    data = {
        "visit": {
            "form_data": {
                "crf": {
                    "adherence": {"completion_rate": rate, "incomplete_reason": "其他"},
                    "_field_meta": {},
                }
            }
        }
    }
    if state:
        data["visit"]["form_data"]["crf"]["_field_meta"][path + "completion_rate"] = {
            "state": state
        }
    reason = field(path + "incomplete_reason")
    other = field(path + "incomplete_other_remark")
    assert evaluate_condition(reason["visible_when"], data) is visible
    assert evaluate_condition(reason["required_when"], data) is required
    assert evaluate_condition(other["visible_when"], data) is visible
    data["visit"]["form_data"]["crf"]["_field_meta"][path + "incomplete_reason"] = {
        "state": "unknown"
    }
    assert evaluate_condition(other["visible_when"], data) is False


def test_actual_weight_and_low_activity_conditions():
    from apps.crf.field_rules import evaluate_condition

    path = "visit.form_data.assessments.physical.frailty."
    data = {}
    put(data, path + "unintentional_weight_loss", "否")
    put(data, path + "low_activity", "是")
    for name in ["weight_loss_kg", "weight_loss_percent", "low_activity_basis"]:
        assert evaluate_condition(field(path + name)["visible_when"], data)
    assert field(path + "low_activity_basis")["include_in_completeness"] is False


def test_condition_language_and_relative_row_metadata():
    from apps.crf.field_rules import evaluate_condition

    fields = [
        {
            "storage": "choice",
            "widget": "multi_choice",
            "options": ["其他", "甲"],
            "metadata": {"storage": "_field_meta", "key": "choice"},
        }
    ]
    condition = {
        "any": [
            {
                "all": [
                    {"storage": "choice", "op": "contains", "value": "其他"},
                    {"storage": "choice", "op": "present"},
                ]
            }
        ]
    }
    assert evaluate_condition(condition, {"choice": ["其他"]}, fields=fields)
    assert not evaluate_condition(condition, {"choice": "其他说明"}, fields=fields)
    assert not evaluate_condition(
        condition,
        {"choice": ["其他"], "_field_meta": {"choice": {"state": "unknown"}}},
        fields=fields,
    )
    assert not evaluate_condition(
        {"storage": "choice", "op": "eval", "value": "1"}, {}, fields=fields
    )
    assert evaluate_condition(
        {"storage": "x", "op": "in", "value": ["是", "否"]},
        {"x": "是"},
        fields=[{"storage": "x", "widget": "single_choice", "options": ["是", "否"]}],
    )


def test_repeated_columns_validate_rows_and_literal_meta_keys():
    data = {
        "crf": {
            "adverse_events": {
                "has_events": "是",
                "entries": [
                    {"_row_id": "a", "severity": "轻"},
                    {
                        "_row_id": "b",
                        "severity": "严重",
                        "occurred_on": "2026-02-31",
                        "_field_meta": {"event_name": {"state": "invalid"}},
                    },
                ],
            }
        }
    }
    errors = validate_visit_form_data_patch(data, "T1")
    for path in [
        "crf.adverse_events.entries.1.severity",
        "crf.adverse_events.entries.1.occurred_on",
        "crf.adverse_events.entries.1._field_meta.event_name",
    ]:
        assert path in errors
    assert not any(".0." in key for key in errors)


def test_unknown_metadata_validation_and_missing_reasons_save():
    key = "visit.form_data.assessments.sppb.balance"
    for meta in [{"state": "unknown"}, {"state": "not_applicable", "reason": ""}, None]:
        assert validate_visit_form_data_patch({"crf": {"_field_meta": {key: meta}}}, "T1") == {}
    for meta in [{"state": "bad"}, {"state": "unknown", "reason": 12}, "unknown"]:
        assert "crf._field_meta." + key in validate_visit_form_data_patch(
            {"crf": {"_field_meta": {key: meta}}}, "T1"
        )


def test_changed_paths_keep_historical_errors_and_check_affected_totals():
    from apps.crf.field_rules import validate_fields

    reg = load_crf_registry()
    data = {
        "visit": {
            "form_data": {
                "assessments": {"sppb": {"balance": 99, "total": 8}},
                "crf": {"completion": "旧自由文本", "satisfaction": {"overall_score": 4}},
            }
        }
    }
    before = deepcopy(data)
    changed = {"visit.form_data.crf.satisfaction.overall_score"}
    assert validate_fields(reg, data, scope="visit", visit_type="T1", changed_paths=changed) == {}
    assert "visit.form_data.assessments.sppb.balance" in validate_fields(
        reg, data, scope="visit", visit_type="T1"
    )
    assert data == before
    data["visit"]["form_data"]["assessments"]["sppb"] = {
        "balance": 4,
        "gait": 3,
        "chair_stand": 4,
        "total": 8,
    }
    errors = validate_fields(
        reg,
        data,
        scope="visit",
        visit_type="T1",
        changed_paths={"visit.form_data.assessments.sppb.balance"},
    )
    assert set(errors) == {"visit.form_data.assessments.sppb.total"}


def test_legacy_strings_and_old_totals_are_not_guessed():
    data = {
        "assessments": {"moca": {"total": 23}},
        "crf": {"completion": "因旧记录退出", "qc": "已核查"},
    }
    before = deepcopy(data)
    assert validate_visit_form_data_patch(data, "T0") == {}
    assert data == before


def test_moca_cap_education_and_judgment():
    data = {
        "assessments": {
            "moca": {
                "subscores": dict(
                    visuospatial=5,
                    naming=3,
                    attention=6,
                    language=3,
                    abstraction=2,
                    delayed_recall=5,
                    orientation=6,
                    education_bonus=1,
                ),
                "total": 30,
                "leq22": "否",
            }
        }
    }
    assert (
        validate_visit_form_data_patch(
            data, "T0", baseline={"demographics": {"education_years": 12}}
        )
        == {}
    )
    assert "assessments.moca.subscores.education_bonus" in validate_visit_form_data_patch(
        data, "T0", baseline={"demographics": {"education_years": 13}}
    )
    data["assessments"]["moca"]["leq22"] = "是"
    assert "assessments.moca.leq22" in validate_visit_form_data_patch(data, "T0")


def test_satisfaction_and_mechanical_measurements():
    data = {
        "crf": {
            "satisfaction": {
                "items": {
                    name: {"score": 4}
                    for name in ["operation", "clarity", "reminders", "burden", "recommendation"]
                },
                "overall_score": 1,
                "total": 20,
            }
        },
        "assessments": {
            "physical": {
                "gait": {"first_seconds": 8, "second_seconds": 6, "fastest_seconds": 6},
                "grip": {"trial_1_kg": 10, "trial_2_kg": 12, "trial_3_kg": 11},
            },
            "grip_strength_kg": 12,
        },
    }
    assert validate_visit_form_data_patch(data, "T1") == {}
    data["crf"]["satisfaction"]["total"] = 21
    data["assessments"]["physical"]["gait"]["fastest_seconds"] = 8
    data["assessments"]["grip_strength_kg"] = 10
    assert set(validate_visit_form_data_patch(data, "T1")) == {
        "crf.satisfaction.total",
        "assessments.physical.gait.fastest_seconds",
        "assessments.grip_strength_kg",
    }


def test_visit_date_parts_do_not_enter_model_date():
    from apps.crf.field_rules import validate_fields
    from apps.crf.field_values import get_field_value

    reg = load_crf_registry()
    parts = {"year": {"state": "value", "value": 2026}, "month": {"state": "unknown"}, "day": None}
    data = {
        "visit": {"visit_date": None, "form_data": {"crf": {"meta": {"visit_date_parts": parts}}}}
    }
    assert validate_fields(reg, data, scope="visit", visit_type="T0") == {}
    assert get_field_value(data, field("visit.visit_date", "T0")) == parts
    data["visit"]["visit_date"] = parts
    assert "visit.visit_date" in validate_fields(reg, data, scope="visit", visit_type="T0")
    data["visit"]["visit_date"] = "2026-02-31"
    assert "visit.visit_date" in validate_fields(reg, data, scope="visit", visit_type="T0")


def test_date_patch_clears_only_alternate_representation_without_mutation():
    from apps.crf.field_values import prepare_visit_date_patch

    original = {"visit_date": "2026-10-08", "form_data": {"crf": {"meta": {"assessor_name": "甲"}}}}
    before = deepcopy(original)
    prepared = prepare_visit_date_patch(original)
    assert original == before
    assert prepared["form_data"]["crf"]["meta"] == {"assessor_name": "甲", "visit_date_parts": None, "visit_date_answer": "2026-10-08"}
    partial = {"year": {"state": "unknown"}}
    for value in [partial, None]:
        patch = {"form_data": {"crf": {"meta": {"visit_date_parts": value}}}}
        prepared_parts=prepare_visit_date_patch(patch)
        assert prepared_parts["visit_date"] == value
        assert prepared_parts["form_data"]["crf"]["meta"] == {"visit_date_parts":value,"visit_date_answer":value}
        assert patch == {"form_data":{"crf":{"meta":{"visit_date_parts":value}}}}
    assert prepare_visit_date_patch({"visit_date": None}) == {
        "visit_date": None,
        "form_data": {"crf": {"meta": {"visit_date_parts": None, "visit_date_answer":None}}},
    }
    conflicting = {
        "visit_date": "2026-10-08",
        "form_data": {"crf": {"meta": {"visit_date_parts": partial}}},
    }
    coordinated=prepare_visit_date_patch(conflicting)
    assert coordinated["visit_date"] == conflicting["visit_date"]
    assert coordinated["form_data"]["crf"]["meta"] == {"visit_date_parts":partial,"visit_date_answer":"2026-10-08"}
    assert "visit_date_answer" not in conflicting["form_data"]["crf"]["meta"]
    from apps.crf.field_rules import validate_fields

    assert "visit.form_data.crf.meta.visit_date_parts" in validate_fields(
        load_crf_registry(), {"visit": conflicting}, scope="visit", visit_type="T0"
    )


def test_model_date_object_is_allowed_only_for_native_date():
    from datetime import date
    from apps.crf.field_rules import validate_fields

    assert (
        validate_fields(
            load_crf_registry(),
            {"visit": {"visit_date": date(2026, 10, 8)}},
            scope="visit",
            visit_type="T0",
        )
        == {}
    )
    assert "crf.meta.assessed_on" in validate_visit_form_data_patch(
        {"crf": {"meta": {"assessed_on": date(2026, 10, 8)}}}, "T0"
    )


def test_changed_metadata_rechecks_dependency_and_keeps_other_history():
    path = "visit.form_data.assessments.sppb.balance"
    data = {
        "assessments": {
            "sppb": {"balance": 4, "gait": 4, "chair_stand": 4, "total": 9},
            "moca": {"total": 99},
        },
        "crf": {"_field_meta": {path: {"state": "value"}}},
    }
    errors = validate_visit_form_data_patch(data, "T1", changed_paths={"crf._field_meta." + path})
    assert set(errors) == {"assessments.sppb.total"}
    data["crf"]["_field_meta"][path]["state"] = "unknown"
    assert (
        validate_visit_form_data_patch(data, "T1", changed_paths={"crf._field_meta." + path}) == {}
    )


def test_partial_month_cannot_silently_discard_day():
    for day in [{"state": "value", "value": 1}, {"state": "unknown"}, {}]:
        value = {"year": {"state": "value", "value": 2026}, "month": None, "day": day}
        errors = validate_patient_baseline_payload(
            {"comorbidities": {"cm_hypertension": {"diagnosed_at": value}}}
        )
        assert "comorbidities.cm_hypertension.diagnosed_at" in errors


def test_invalid_date_cannot_be_hidden_by_unknown_metadata():
    path = "visit.form_data.crf.meta.assessed_on"
    data = {
        "crf": {"meta": {"assessed_on": "2026-02-31"}, "_field_meta": {path: {"state": "unknown"}}}
    }
    assert "crf.meta.assessed_on" in validate_visit_form_data_patch(data, "T1")


def test_numeric_baseline_and_text_length_constraints():
    for value in [-1, 12.5, 101, float("-inf")]:
        assert "demographics.education_years" in validate_patient_baseline_payload(
            {"demographics": {"education_years": value}}
        )
    assert "crf.satisfaction.matrix_note" in validate_visit_form_data_patch(
        {"crf": {"satisfaction": {"matrix_note": "甲" * 4001}}}, "T1"
    )


def test_legacy_unknown_option_is_preserved_but_not_observed():
    from apps.crf.field_rules import get_observed_value
    from apps.crf.field_values import get_field_value

    definition = next(f for f in load_crf_registry()["fields"] if f.get("legacy_options"))
    data = {}
    put(data, definition["storage"], definition["legacy_options"][0])
    assert get_field_value(data, definition) == definition["legacy_options"][0]
    assert get_observed_value(data, definition) is None
    assert (
        validate_patient_baseline_payload(
            data["patient_baseline"], changed_paths={"demographics.education_years"}
        )
        == {}
    )


def test_relative_rules_and_nested_repeated_validation():
    from apps.crf.field_rules import evaluate_condition, validate_fields

    child = {
        "storage": "score",
        "widget": "number",
        "min": 0,
        "max": 4,
        "metadata": {"storage": "_field_meta", "key": "score"},
    }
    reg = {
        "fields": [
            {
                "storage": "visit.form_data.rows",
                "widget": "table_repeat",
                "children": [{"storage": "nested", "widget": "table_repeat", "children": [child]}],
            }
        ]
    }
    data = {"visit": {"form_data": {"rows": [{"nested": [{"score": 4}, {"score": 99}]}]}}}
    assert set(validate_fields(reg, data, scope="visit", visit_type="T1")) == {
        "visit.form_data.rows.0.nested.1.score"
    }
    medication = field("visit.form_data.crf.medication_change.entries")
    stopped = next(f for f in medication["children"] if f["storage"] == "stopped_on")
    assert evaluate_condition(
        stopped["visible_when"], {"ongoing": "已停用"}, fields=medication["children"]
    )
    assert not evaluate_condition(
        stopped["visible_when"],
        {"ongoing": "已停用", "_field_meta": {"ongoing": {"state": "unknown"}}},
        fields=medication["children"],
    )


def test_partial_row_update_does_not_validate_unrelated_legacy_column():
    data = {
        "crf": {
            "adverse_events": {
                "entries": [{"_row_id": "a", "severity": "严重", "event_name": "新说明"}]
            }
        }
    }
    assert (
        validate_visit_form_data_patch(
            data, "T1", changed_paths={"crf.adverse_events.entries.0.event_name"}
        )
        == {}
    )
    assert "crf.adverse_events.entries.0.severity" in validate_visit_form_data_patch(
        data, "T1", changed_paths={"crf.adverse_events.entries"}
    )


def test_mechanical_result_helper_does_not_fill_missing_operands():
    from apps.crf.field_rules import calculate_expected_value

    total = field("visit.form_data.assessments.sppb.total")
    data = {"visit": {"form_data": {"assessments": {"sppb": {"balance": 0, "gait": 4}}}}}
    assert calculate_expected_value(total, data) is None
    data["visit"]["form_data"]["assessments"]["sppb"]["chair_stand"] = 0
    assert calculate_expected_value(total, data) == 4
    data["visit"]["form_data"]["assessments"]["sppb"]["balance"] = 99
    assert calculate_expected_value(total, data) is None


def test_nested_consistency_tracks_changed_operand_and_unknown_state():
    from apps.crf.field_rules import validate_fields

    children = [
        {"storage": name, "widget": "number", "metadata": {"storage": "_field_meta", "key": name}}
        for name in ["first", "second", "total"]
    ]
    children[-1]["validation"] = {
        "consistency": {"operation": "sum", "operands": ["first", "second"], "when": "all_present"}
    }
    reg = {
        "fields": [
            {"storage": "visit.form_data.rows", "widget": "table_repeat", "children": children}
        ]
    }
    data = {"visit": {"form_data": {"rows": [{"first": 2, "second": 3, "total": 4}]}}}
    assert "visit.form_data.rows.0.total" in validate_fields(
        reg, data, scope="visit", visit_type="T1", changed_paths={"visit.form_data.rows.0.first"}
    )
    data["visit"]["form_data"]["rows"][0]["_field_meta"] = {"first": {"state": "unknown"}}
    assert (
        validate_fields(
            reg,
            data,
            scope="visit",
            visit_type="T1",
            changed_paths={"visit.form_data.rows.0._field_meta.first"},
        )
        == {}
    )


def test_duplicate_row_id_compares_unchanged_rows_too():
    data = {"crf": {"adverse_events": {"entries": [{"_row_id": "a"}, {"_row_id": "a"}]}}}
    assert "crf.adverse_events.entries.1._row_id" in validate_visit_form_data_patch(
        data, "T1", changed_paths={"crf.adverse_events.entries.1._row_id"}
    )


@pytest.mark.parametrize("value", ["", "   ", 99, {"year": {"state": "unknown"}}])
def test_native_date_accepts_only_real_complete_date_or_null(value):
    from apps.crf.field_rules import validate_fields

    errors = validate_fields(
        load_crf_registry(), {"visit": {"visit_date": value}}, scope="visit", visit_type="T0"
    )
    assert "visit.visit_date" in errors


@pytest.mark.parametrize("value", ["", "2026-10-08", 99])
def test_dedicated_date_parts_accepts_only_object_or_null(value):
    errors = validate_visit_form_data_patch({"crf": {"meta": {"visit_date_parts": value}}}, "T0")
    assert "crf.meta.visit_date_parts" in errors


def test_conflicting_or_misplaced_date_is_not_an_observation():
    from apps.crf.field_rules import get_observed_value

    definition = field("visit.visit_date", "T0")
    parts = {
        name: {"state": "value", "value": value}
        for name, value in [("year", 2026), ("month", 10), ("day", 8)]
    }
    assert get_observed_value({"visit": {"visit_date": parts}}, definition) is None
    assert (
        get_observed_value(
            {
                "visit": {
                    "visit_date": "2026-10-08",
                    "form_data": {"crf": {"meta": {"visit_date_parts": parts}}},
                }
            },
            definition,
        )
        is None
    )
    assert (
        get_observed_value(
            {
                "visit": {
                    "visit_date": None,
                    "form_data": {"crf": {"meta": {"visit_date_parts": parts}}},
                }
            },
            definition,
        )
        == parts
    )


@pytest.mark.parametrize("index", [0, 1])
def test_changed_row_id_rejects_collision_in_either_direction(index):
    data = {"crf": {"adverse_events": {"entries": [{"_row_id": "a"}, {"_row_id": "a"}]}}}
    changed = f"crf.adverse_events.entries.{index}._row_id"
    assert set(validate_visit_form_data_patch(data, "T1", changed_paths={changed})) == {changed}


@pytest.mark.parametrize("index", [0, 1])
def test_editing_other_column_preserves_unchanged_historical_duplicate_ids(index):
    data = {
        "crf": {
            "adverse_events": {
                "entries": [
                    {"_row_id": "a", "event_name": "原说明"},
                    {"_row_id": "a", "event_name": "原说明"},
                ]
            }
        }
    }
    data["crf"]["adverse_events"]["entries"][index]["event_name"] = "新说明"
    assert (
        validate_visit_form_data_patch(
            data, "T1", changed_paths={f"crf.adverse_events.entries.{index}.event_name"}
        )
        == {}
    )


@pytest.mark.parametrize(
    ("changed", "error_indices"),
    [
        ({"crf.adverse_events.entries"}, [0, 1]),
        ({"crf.adverse_events.entries.0"}, [0]),
        ({"crf.adverse_events.entries.1"}, [1]),
    ],
)
def test_replacing_row_or_array_still_checks_duplicate_ids(changed, error_indices):
    data = {"crf": {"adverse_events": {"entries": [{"_row_id": "a"}, {"_row_id": "a"}]}}}
    errors = validate_visit_form_data_patch(data, "T1", changed_paths=changed)
    assert set(errors) == {f"crf.adverse_events.entries.{i}._row_id" for i in error_indices}


def test_missing_historical_row_ids_still_allow_draft():
    data = {"crf": {"adverse_events": {"entries": [{"event_name": "旧记录"}, {"_row_id": "a"}]}}}
    assert (
        validate_visit_form_data_patch(data, "T1", changed_paths={"crf.adverse_events.entries"})
        == {}
    )


def test_native_date_remains_observed_when_old_partial_parent_is_non_object():
    from apps.crf.field_rules import get_observed_value, validate_fields
    from apps.crf.field_values import get_field_value
    from apps.crf.registry_loader import load_crf_registry

    registry = load_crf_registry()
    field = next(
        f
        for f in registry["fields"]
        if f["storage"] == "visit.visit_date" and f["visit_types"] == ["T1"]
    )
    data = {
        "visit": {"visit_date": "2026-10-08", "form_data": {"crf": {"meta": "历史访视信息原文"}}}
    }
    assert get_field_value(data, field) == "2026-10-08"
    assert get_observed_value(data, field) == "2026-10-08"
    assert (
        validate_fields(
            registry, data, scope="visit", visit_type="T1", changed_paths={"visit.visit_date"}
        )
        == {}
    )


def test_partial_parent_error_and_real_date_conflict_still_rejected():
    from apps.crf.field_rules import validate_fields
    from apps.crf.registry_loader import load_crf_registry

    registry = load_crf_registry()
    data = {"visit": {"visit_date": "2026-10-08", "form_data": {"crf": "新非法父节点"}}}
    errors = validate_fields(
        registry, data, scope="visit", visit_type="T1", changed_paths={"visit.form_data.crf"}
    )
    assert "visit.form_data.crf.meta.visit_date_parts" in errors
    data["visit"]["form_data"]["crf"] = {
        "meta": {"visit_date_parts": {"year": {"state": "unknown"}}}
    }
    errors = validate_fields(
        registry, data, scope="visit", visit_type="T1", changed_paths={"visit.visit_date"}
    )
    assert "visit.form_data.crf.meta.visit_date_parts" in errors
    assert "不能同时" in errors["visit.form_data.crf.meta.visit_date_parts"]
