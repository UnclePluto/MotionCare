from apps.crf.answer_values import has_crf_answer_marker
"""Backward-compatible CRF payload validators using the shared rules engine."""

from collections.abc import Mapping

from apps.crf.field_rules import validate_field_value, validate_fields
from apps.crf.field_values import MISSING, match_crf_rows
from apps.crf.registry_loader import load_crf_registry


def validate_patient_baseline_payload(
    data: dict, *, changed_paths: set[str] | None = None
) -> dict[str, str]:
    """Validate a candidate baseline; optional changed paths are baseline-relative."""
    if not isinstance(data, Mapping):
        return {"": "payload 必须是对象"}
    prefix = "patient_baseline."
    changed = (
        None
        if changed_paths is None
        else {p if p.startswith(prefix) else prefix + p for p in changed_paths}
    )
    errors = validate_fields(
        load_crf_registry(),
        {"patient_baseline": data},
        scope="patient_baseline",
        visit_type=None,
        changed_paths=changed,
    )
    return {p.removeprefix(prefix): message for p, message in errors.items()}


def validate_visit_form_data_patch(
    form_data_patch: dict,
    visit_type: str,
    *,
    changed_paths: set[str] | None = None,
    baseline: dict | None = None,
) -> dict[str, str]:
    """Validate candidate form_data; changed paths may be relative or canonical.

    Callers merging stored data must provide actual changed paths. This wrapper
    cannot validate model visit_date; validate_fields accepts the complete visit.
    """
    if not isinstance(form_data_patch, Mapping):
        return {"": "form_data 必须是对象"}
    prefix = "visit.form_data."
    changed = (
        None
        if changed_paths is None
        else {
            p if p.startswith(("visit.", "patient_baseline.")) else prefix + p
            for p in changed_paths
        }
    )
    errors = validate_fields(
        load_crf_registry(),
        {"visit": {"form_data": form_data_patch}},
        scope="visit",
        visit_type=visit_type,
        changed_paths=changed,
        baseline=baseline,
    )
    return {p.removeprefix(prefix): message for p, message in errors.items()}


def validate_crf_structure_patch(
    current: dict, patch: dict, *, scope: str, visit_type: str | None
) -> dict[str, str]:
    """Reject silent scalar-to-structure loss before merging canonical data.

    Only controlled partial-date leaves may replace a valid historical date
    string with date components. Empty/null slots are first-entry locations;
    explicit null clearing and complete array replacement keep their contracts.
    """
    dates = {}
    answers = {"visit.form_data.crf.meta.visit_date_answer"} if scope == "visit" else set()

    def collect(field, prefix=""):
        path = prefix + field["storage"]
        if field.get("metadata") and field.get("widget") != "table_repeat":
            answers.add(path)
        if field.get("widget") == "date" and field.get("allow_partial_date"):
            dates[path] = field
        for child in field.get("children", []):
            collect(child, path + ".*.")

    for field in load_crf_registry()["fields"]:
        if field["storage"].startswith(scope + ".") and (
            not field.get("visit_types") or visit_type in field["visit_types"]
        ):
            collect(field)
    errors = {}

    def check(old, new, path):
        normalized=".".join("*" if part.isdecimal() else part for part in path.split("."))
        if normalized in answers and has_crf_answer_marker(new):
            return  # Marked answer is a controlled atomic leaf, validated by field rules.
        if isinstance(old, Mapping) and isinstance(new, Mapping):
            for key, value in new.items():
                check(old.get(key, MISSING), value, f"{path}.{key}" if path else key)
        elif isinstance(old, list) and isinstance(new, list):
            for index, old_index in match_crf_rows(old, new).items():
                check(old[old_index], new[index], f"{path}.{index}")
        elif isinstance(new, (Mapping, list)) and not isinstance(old, (Mapping, list)):
            if old is MISSING or old is None or (isinstance(old, str) and old == ""):
                return
            definition = dates.get(
                ".".join("*" if part.isdecimal() else part for part in path.split("."))
            )
            if (
                definition
                and isinstance(new, Mapping)
                and isinstance(old, str)
                and validate_field_value(definition, old) is None
            ):
                return
            errors[path] = "已有历史原文或标量，不能直接替换为结构化数据，请先核对原记录。"

    check(current, patch, "")
    return errors
