from copy import deepcopy
import pytest
from apps.crf.field_rules import validate_field_value, get_observed_value
from apps.crf.field_values import merge_crf_patch, changed_crf_paths
from apps.crf.registry_loader import load_crf_registry
from apps.crf.completeness import evaluate_completeness

PATH = "visit.form_data.assessments.sppb.balance"
MARKED = {"__crf_answer__": 1, "state": "unknown", "value": 0, "reason": None}


def field():
    return next(
        f
        for f in load_crf_registry()["fields"]
        if f["storage"] == PATH and "T0" in f.get("visit_types", [])
    )


def item(values):
    p = evaluate_completeness({"fields": [field()]}, {}, {"T0": {"form_data": values}})
    return next(f for s in p["sections"] for f in s["fields"] if f["storage"] == PATH)


def test_unknown_single_field_is_handled_without_generic_reason():
    assert validate_field_value(field(), MARKED) is None
    assert (
        get_observed_value(
            {"visit": {"form_data": {"assessments": {"sppb": {"balance": MARKED}}}}}, field()
        )
        is None
    )
    assert item({"assessments": {"sppb": {"balance": MARKED}}})["state"] == "unknown"
    assert item({"assessments": {"sppb": {"balance": MARKED}}})["raw_value"] == MARKED


def test_marked_patch_is_atomic_and_does_not_leave_state_on_zero():
    old = {"score": deepcopy(MARKED)}
    new = {"score": {**MARKED, "state": "not_applicable", "reason": "原记录"}}
    assert changed_crf_paths(old, new) == {"score"}
    assert merge_crf_patch(old, new) == new
    assert merge_crf_patch(new, {"score": 0}) == {"score": 0}
    assert old == {"score": MARKED}


@pytest.mark.parametrize(
    "answer",
    [
        {**MARKED, "__crf_answer__": True},
        {**MARKED, "__crf_answer__": 2},
        {**MARKED, "state": "value"},
        {**MARKED, "reason": 9},
        {**MARKED, "value": True},
    ],
)
def test_malformed_marked_core_is_rejected(answer):
    assert validate_field_value(field(), answer)
    assert item({"assessments": {"sppb": {"balance": answer}}})["state"] == "unresolved"


def test_legacy_unknown_reason_is_optional_but_bad_parent_still_invalid():
    meta = {"_field_meta": {PATH: {"state": "unknown"}}}
    assert item({"assessments": {"sppb": {"balance": 0}}, "crf": meta})["state"] == "unknown"
    broken = item({"assessments": {"sppb": []}, "crf": meta})
    assert broken["state"] == "unresolved"
    assert broken["issues"]


@pytest.mark.django_db
def test_visit_marked_answer_round_trip_reconciles_only_edited_legacy_state(
    doctor, project_patient
):
    from rest_framework.test import APIClient
    from apps.visits.models import VisitRecord

    v = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    v.form_data = {
        "assessments": {"sppb": {"balance": 0}},
        "crf": {
            "_field_meta": {
                PATH: {"state": "unknown", "reason": "旧理由", "extra": "保留"},
                "other": {"state": "unknown", "reason": "未改"},
            }
        },
    }
    v.save(update_fields=["form_data"])
    c = APIClient()
    c.force_authenticate(doctor)
    url = f"/api/visits/{v.pk}/"
    resp = c.patch(
        url, {"form_data": {"assessments": {"sppb": {"balance": MARKED}}}}, format="json"
    )
    assert resp.status_code == 200, resp.data
    v.refresh_from_db()
    assert v.form_data["assessments"]["sppb"]["balance"] == MARKED
    meta = v.form_data["crf"]["_field_meta"]
    assert meta[PATH].get("state") is None and meta[PATH].get("reason") is None
    assert meta[PATH]["extra"] == "保留" and meta["other"]["reason"] == "未改"
    resp = c.patch(url, {"form_data": {"assessments": {"sppb": {"balance": 0}}}}, format="json")
    assert resp.status_code == 200, resp.data
    assert c.get(url).data["form_data"]["assessments"]["sppb"]["balance"] == 0


@pytest.mark.django_db
def test_baseline_marked_answer_round_trip_preserves_unrelated_legacy(doctor, patient):
    from rest_framework.test import APIClient
    from apps.patients.models import PatientBaseline

    b, _ = PatientBaseline.objects.get_or_create(patient=patient)
    key = "patient_baseline.demographics.age_years"
    b.demographics = {
        "age_years": 66,
        "_crf_field_meta": {
            key: {"state": "unknown", "reason": "旧", "extra": "保留"},
            "else": {"reason": "未改"},
        },
    }
    b.save(update_fields=["demographics"])
    c = APIClient()
    c.force_authenticate(doctor)
    url = f"/api/patients/{patient.pk}/baseline/"
    answer = {**MARKED, "value": 66}
    resp = c.patch(url, {"demographics": {"age_years": answer}}, format="json")
    assert resp.status_code == 200, resp.data
    b.refresh_from_db()
    assert b.demographics["age_years"] == answer
    assert b.demographics["_crf_field_meta"][key].get("state") is None
    assert b.demographics["_crf_field_meta"][key]["extra"] == "保留"
    assert b.demographics["_crf_field_meta"]["else"]["reason"] == "未改"


def test_new_marked_answer_wins_over_malformed_old_metadata_in_preview():
    from apps.crf.completeness import evaluate_completeness
    from apps.crf.registry_loader import load_crf_registry

    marked = {"__crf_answer__": 1, "state": "unknown", "value": 0, "reason": None}
    result = evaluate_completeness(
        load_crf_registry(),
        {
            "demographics": {
                "age_years": marked,
                "_crf_field_meta": {"patient_baseline.demographics.age_years": "旧状态原文"},
            }
        },
        {},
    )
    item = next(
        f
        for section in result["sections"]
        for f in section["fields"]
        if f["field_id"] == "dm_age_years"
    )
    assert item["state"] == "unknown" and not item["issues"] and item["raw_value"] == marked
    assert any(
        f["raw_value"] == "旧状态原文"
        for section in result["sections"]
        for f in section["fields"]
        if section["supplemental"]
    )
