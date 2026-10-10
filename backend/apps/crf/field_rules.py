"""Controlled CRF validation and conditions shared by saving and inspection.

validate_fields returns canonical dotted error paths (row indices included).
None changed_paths validates every present value, useful for historical review;
a set restricts hard errors to edited fields and affected consistency rules.
Missing answers/reasons are completeness concerns, never hard save errors.
"""

from apps.crf.answer_values import decode_crf_answer, has_crf_answer_marker

import calendar
import math
import re
from collections import Counter
from collections.abc import Mapping
from datetime import date

from apps.crf.field_values import (
    BAD_PARENT,
    MISSING,
    get_field_metadata,
    get_field_value,
    lookup_path,
)
from apps.crf.registry_loader import load_crf_registry


def is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _constraints(field):
    return {
        **{k: field[k] for k in ("min", "max", "integer", "max_length") if k in field},
        **field.get("validation", {}),
    }


def validate_partial_date(value: dict, *, precision="day") -> str | None:
    """Components are {state: value, value: int}, {state: unknown}, or null/absent.

    Unprocessed components may also be {} or {state: null}. Unknown components
    cannot carry residual numbers. A month-precision day must be absent or null.
    Known combinations are checked even when another component is unknown.
    """
    if not isinstance(value, Mapping) or set(value) - {"year", "month", "day"}:
        return "部分日期必须是年、月、日分量对象"
    if precision == "month" and value.get("day") is not None:
        return "月份精度不能包含日分量"
    known = {}
    for name, limit in [("year", 9999), ("month", 12), ("day", 31)]:
        part = value.get(name)
        if part is None:
            continue
        if not isinstance(part, Mapping) or set(part) - {"state", "value"}:
            return f"{name} 分量格式无效"
        state = part.get("state")
        if state not in (None, "value", "unknown"):
            return f"{name} 分量状态无效"
        number = part.get("value")
        if state == "value":
            if type(number) is not int or not 1 <= number <= limit:
                return f"{name} 已知分量超出合法范围"
            known[name] = number
        elif number is not None:
            return f"{name} 未知或未处理分量不能携带数值"
    if "month" in known and "day" in known:
        # Leap year 2000 permits Feb 29 if year is not yet known; never Feb 30.
        maximum = calendar.monthrange(known.get("year", 2000), known["month"])[1]
        if known["day"] > maximum:
            return "已知日期分量构成非法日历日期"
    return None


def _validate_date(field, value):
    if field["storage"] == "visit.visit_date" and type(value) is date:
        return None
    precision = field.get("date_precision", "day")
    if field.get("allow_partial_date") and isinstance(value, str):
        if re.fullmatch(r"\d{4}", value):
            return None if 1 <= int(value) <= 9999 else "年份无效"
        if re.fullmatch(r"\d{4}-\d{2}", value):
            try:
                date.fromisoformat(value + "-01")
                return None
            except ValueError:
                return "月份无效"
    if isinstance(value, Mapping) and field.get("allow_partial_date"):
        return validate_partial_date(value, precision=precision)
    if not isinstance(value, str):
        return "日期必须是日期字符串或明确的部分日期"
    if precision == "month" and re.fullmatch(r"\d{4}-\d{2}", value):
        try:
            date.fromisoformat(value + "-01")
            return None
        except ValueError:
            return "月份无效"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            date.fromisoformat(value)
            return None
        except ValueError:
            return "日期不是合法日历日期"
    return "日期格式应为 YYYY-MM" if precision == "month" else "日期格式应为 YYYY-MM-DD"


def validate_field_value(field: dict, value: object) -> str | None:
    """Validate raw values independently of metadata, visibility, or missingness."""
    if has_crf_answer_marker(value):
        answer = decode_crf_answer(value)
        if answer["error"]:
            return answer["error"]
        if not field.get("metadata") or answer["state"] not in field["metadata"].get("states", []):
            return "此字段不支持该答案状态"
        return validate_field_value(field, answer["value"])
    if value is BAD_PARENT:
        return "上级字段必须是对象"
    if field.get("storage") == "visit.visit_date":
        if value is MISSING or value is None:
            return None
        return _validate_date(field, value)
    if value is MISSING or is_blank(value):
        return None
    widget = field.get("widget")
    limits = _constraints(field)
    if widget == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "必须是数字"
        if isinstance(value, float) and not math.isfinite(value):
            return "必须是有限数字"
        if limits.get("integer") and value != int(value):
            return "必须是整数"
        if "min" in limits and value < limits["min"]:
            return f"不能小于 {limits['min']}"
        if "max" in limits and value > limits["max"]:
            return f"不能大于 {limits['max']}"
    elif widget == "single_choice":
        if not isinstance(value, str) or value not in field.get("options", []):
            return "不在可选项中"
    elif widget == "multi_choice":
        if not isinstance(value, list):
            return "必须是列表"
        if any(not isinstance(v, str) or v not in field.get("options", []) for v in value):
            return "包含无效选项"
        if len(set(value)) != len(value):
            return "不能重复选择同一选项"
    elif widget == "date":
        return _validate_date(field, value)
    elif widget in ("text", "textarea"):
        if not isinstance(value, str):
            return "必须是文本"
        if limits.get("max_length") is not None and len(value) > limits["max_length"]:
            return f"文字不能超过 {limits['max_length']} 字"
    elif widget == "table_repeat" and not isinstance(value, list):
        return "明细必须是列表"
    return None


def _metadata_error(meta, field):
    if meta is None:
        return None
    if not isinstance(meta, Mapping):
        return "字段状态必须是对象"
    allowed = field.get("metadata", {}).get("states", ["value", "unknown", "not_applicable"])
    if meta.get("state") is not None and meta["state"] not in allowed:
        return "字段状态无效"
    if meta.get("reason") is not None and not isinstance(meta["reason"], str):
        return "原因必须是文本"
    return None


def get_observed_value(data: dict, field: dict) -> object:
    """Return only valid known observations; None means unavailable to rules."""
    value = get_field_value(data, field)
    answer = decode_crf_answer(value, get_field_metadata(data, field))
    if answer["error"] or answer["state"] != "value":
        return None
    value_definition = field
    canonical = (
        lookup_path(data, field["date_answer_storage"])
        if field.get("date_answer_storage")
        else MISSING
    )
    if (
        field["storage"] == "visit.visit_date"
        and isinstance(lookup_path(data, field["storage"]), Mapping)
        and not has_crf_answer_marker(lookup_path(data, field["storage"]))
        and canonical in (MISSING, BAD_PARENT)
    ):
        return None
    if field.get("partial_date_storage"):
        native = lookup_path(data, field["storage"])
        partial = lookup_path(data, field["partial_date_storage"])
        if validate_field_value(field, native):
            return None
        if partial is not MISSING and partial is not BAD_PARENT and partial is not None:
            if (
                native is not MISSING
                and native is not None
                and (canonical is MISSING or canonical is BAD_PARENT or canonical != partial)
            ):
                return None
            if validate_partial_date(partial, precision=field.get("date_precision", "day")):
                return None
            value_definition = {**field, "storage": field["partial_date_storage"]}
    if is_blank(value) or validate_field_value(value_definition, value):
        return None
    if value in field.get("legacy_options", []):
        return None
    if field.get("widget") == "date" and isinstance(value, Mapping):
        names = (
            ("year", "month")
            if field.get("date_precision") == "month"
            else ("year", "month", "day")
        )
        if any(
            not isinstance(value.get(name), Mapping) or value[name].get("state") != "value"
            for name in names
        ):
            return None
    return value


def evaluate_condition(condition: dict | None, data: dict, *, fields=None) -> bool:
    """Evaluate only eq/ne/in/present/contains and recursive all/any.

    Pass fields=parent['children'] and data=row for relative repeated-row rules.
    Malformed/unsupported conditions fail closed. Unavailable values: present/eq/
    in/contains are false, ne is true (e.g. unknown completion is not known 100%).
    """
    if condition is None:
        return True
    if not isinstance(condition, Mapping):
        return False
    fields = load_crf_registry()["fields"] if fields is None else fields
    for operator, reducer in [("all", all), ("any", any)]:
        if operator in condition:
            clauses = condition[operator]
            return (
                isinstance(clauses, list)
                and bool(clauses)
                and reducer(evaluate_condition(c, data, fields=fields) for c in clauses)
            )
    matches = [f for f in fields if f["storage"] == condition.get("storage")]
    definition = next((f for f in matches if not f.get("legacy")), matches[0] if matches else None)
    observed = get_observed_value(data, definition) if definition else None
    op, expected = condition.get("op"), condition.get("value")
    if op == "present":
        return observed is not None and observed != []
    if op == "ne":
        return observed is None or observed != expected
    if observed is None:
        return False
    if op == "eq":
        return observed == expected
    if op == "in":
        return isinstance(expected, list) and observed in expected
    if op == "contains":
        return isinstance(observed, list) and expected in observed
    return False


def calculate_expected_value(field: dict, data: dict, *, fields=None) -> object:
    """Return a mechanical expected value, or None when prerequisites are absent.

    Never substitute zero for missing/unknown/invalid observations, never write.
    """
    rule = field.get("validation", {}).get("consistency")
    if not rule:
        return None
    definitions = {
        f["storage"]: f for f in (load_crf_registry()["fields"] if fields is None else fields)
    }
    values = [
        get_observed_value(data, definitions[p]) if p in definitions else None
        for p in rule["operands"]
    ]
    if not values or any(v is None for v in values):
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
        return None
    operation = rule["operation"]
    if operation == "sum":
        result = sum(values)
        return min(result, rule["cap"]) if "cap" in rule else result
    if operation == "min":
        return min(values)
    if operation == "max":
        return max(values)
    if operation == "education_bonus" and rule.get("comparison") == "leq":
        return rule["matched_value"] if values[0] <= rule["threshold"] else rule["otherwise_value"]
    if operation == "leq":
        return rule["true_value"] if values[0] <= rule["threshold"] else rule["false_value"]
    return None


def _touches(path, changed_paths):
    return changed_paths is None or any(
        path == p or path.startswith(p + ".") or p.startswith(path + ".") for p in changed_paths
    )


def _meta_path(field):
    meta = field.get("metadata")
    return f"{meta['storage']}.{meta['key']}" if meta else None


def _field_touched(field, changed_paths, prefix=""):
    return any(
        _touches(prefix + p, changed_paths)
        for p in [
            field["storage"],
            field.get("date_answer_storage"),
            field.get("partial_date_storage"),
            _meta_path(field),
        ]
        if p
    )


def validate_fields(
    registry: dict,
    data: dict,
    *,
    scope: str,
    visit_type: str | None,
    changed_paths: set[str] | None = None,
    baseline: dict | None = None,
) -> dict[str, str]:
    """Validate a merged canonical candidate without changing it.

    scope is patient_baseline or visit; changed_paths uses canonical storage paths
    including metadata-container + '.' + literal metadata key. baseline optionally
    supplies current patient-baseline context for MoCA education consistency.
    """
    if scope not in ("patient_baseline", "visit"):
        raise ValueError("scope 必须为 patient_baseline 或 visit")
    if not isinstance(data, Mapping):
        return {"": "payload 必须是对象"}
    context = {**data, **({"patient_baseline": baseline} if baseline is not None else {})}
    errors = {}
    fields = [
        f
        for f in registry.get("fields", [])
        if not f.get("visit_types") or visit_type in f["visit_types"]
    ]
    selected = [
        f
        for f in fields
        if f["storage"].startswith(scope + ".")
        and (scope != "patient_baseline" or not f.get("visit_types"))
    ]

    def check(field, row_data, path_prefix="", local_fields=None):
        path = path_prefix + field["storage"]
        raw = lookup_path(row_data, field["storage"])
        if _touches(path, changed_paths):
            error = validate_field_value(field, raw)
            canonical_value = (
                lookup_path(row_data, field["date_answer_storage"])
                if field.get("date_answer_storage")
                else MISSING
            )
            if (
                field["storage"] == "visit.visit_date"
                and isinstance(raw, Mapping)
                and not has_crf_answer_marker(raw)
                and canonical_value in (MISSING, BAD_PARENT)
            ):
                error = "部分日期必须存入日期答案字段"
            if (
                field.get("partial_date_storage")
                and field["storage"] != "visit.visit_date"
                and raw is not MISSING
                and not is_blank(raw)
            ):
                error = validate_field_value({**field, "allow_partial_date": False}, raw)
            if error:
                errors[path] = error
        canonical_path = field.get("date_answer_storage")
        canonical = lookup_path(row_data, canonical_path) if canonical_path else MISSING
        if canonical_path and _touches(canonical_path, changed_paths):
            error = validate_field_value(field, canonical)
            if error:
                errors[canonical_path] = error
        meta_path = _meta_path(field)
        if (
            meta_path
            and _touches(path_prefix + meta_path, changed_paths)
            and not has_crf_answer_marker(get_field_value(row_data, field))
        ):
            error = _metadata_error(get_field_metadata(row_data, field), field)
            if error:
                errors[path_prefix + meta_path] = error
        partial_path = field.get("partial_date_storage")
        if partial_path:
            partial = lookup_path(row_data, partial_path)
            if (
                _touches(partial_path, changed_paths)
                and partial is not MISSING
                and partial is not None
            ):
                error = validate_partial_date(partial, precision=field.get("date_precision", "day"))
                if error:
                    errors[partial_path] = error
            if (
                _field_touched(field, changed_paths)
                and (canonical is MISSING or canonical is BAD_PARENT or canonical != partial)
                and raw is not MISSING
                and not is_blank(raw)
                and partial is not MISSING
                and partial is not BAD_PARENT
                and not is_blank(partial)
            ):
                errors[partial_path] = "完整日期与部分日期不能同时填写"
        repeated = decode_crf_answer(raw)["value"]
        repeated_path = path + ".value" if has_crf_answer_marker(raw) else path
        if field.get("widget") == "table_repeat" and isinstance(repeated, list):
            row_id_key = field.get("row_id_key", "_row_id")
            row_id_counts = Counter(
                row[row_id_key]
                for row in repeated
                if isinstance(row, Mapping) and isinstance(row.get(row_id_key), str)
            )
            for index, row in enumerate(repeated):
                row_path = f"{repeated_path}.{index}"
                if not isinstance(row, Mapping):
                    if _touches(row_path, changed_paths):
                        errors[row_path] = "明细行必须是对象"
                    continue
                row_id = row.get(row_id_key)
                row_id_path = f"{row_path}.{row_id_key}"
                if row_id is not None and _touches(row_id_path, changed_paths):
                    if (
                        not isinstance(row_id, str)
                        or not row_id.strip()
                        or row_id_counts[row_id] > 1
                    ):
                        errors[row_id_path] = "明细行标识必须是非空且唯一的字符串"
                for child in field.get("children", []):
                    check(child, row, row_path + ".", field["children"])
        rule = field.get("validation", {}).get("consistency")
        if rule:
            candidates = local_fields or fields
            dependencies = [f for f in candidates if f["storage"] in rule["operands"]]
            affected = _field_touched(field, changed_paths, path_prefix) or any(
                _field_touched(f, changed_paths, path_prefix) for f in dependencies
            )
            if affected:
                observed = get_observed_value(row_data, field)
                expected = calculate_expected_value(field, row_data, fields=candidates)
                if observed is not None and expected is not None and observed != expected:
                    errors[path] = f"与已录原始值不一致，应为 {expected}"

    for definition in selected:
        check(definition, context)
    return errors
