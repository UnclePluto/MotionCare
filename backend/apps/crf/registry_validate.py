"""Validate CRF payload fragments against the field registry."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from apps.crf.registry_loader import load_crf_registry

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BAD_PARENT = object()


def validate_patient_baseline_payload(data: dict) -> dict[str, str]:
    """Validate submitted PatientBaseline PATCH fields by registry metadata."""
    if not isinstance(data, Mapping):
        return {"": "payload 必须是对象"}

    errors: dict[str, str] = {}
    reg = load_crf_registry()

    for field in reg.get("fields", []):
        storage = field.get("storage")
        if not isinstance(storage, str) or not storage.startswith("patient_baseline."):
            continue

        path = storage.removeprefix("patient_baseline.")
        parts = path.split(".")
        present, value = _get_submitted_value(data, parts)
        if not present:
            continue

        error = _validate_value(field, value)
        if error:
            errors[path] = error

    errors.update(_validate_other_remarks(reg, data))
    return errors


def validate_visit_form_data_patch(form_data_patch: dict, visit_type: str) -> dict[str, str]:
    """Validate submitted visit form_data PATCH fields by registry metadata."""
    if not isinstance(form_data_patch, Mapping):
        return {"": "form_data 必须是对象"}

    errors: dict[str, str] = {}
    reg = load_crf_registry()

    for field in reg.get("fields", []):
        storage = field.get("storage")
        if not isinstance(storage, str) or not storage.startswith("visit.form_data."):
            continue

        visit_types = field.get("visit_types")
        if visit_types is not None and visit_type not in visit_types:
            continue

        path = storage.removeprefix("visit.form_data.")
        parts = path.split(".")
        present, value = _get_submitted_value(form_data_patch, parts)
        if not present:
            continue

        error = _validate_value(field, value)
        if error:
            errors[path] = error

    return errors


def _validate_other_remarks(reg: Mapping[str, Any], data: Mapping[str, Any]) -> dict[str, str]:
    """当主选项为「其他」且 registry 要求完整时，校验备注必填；校验备注类型为文本。"""
    out: dict[str, str] = {}
    for field in reg.get("fields", []):
        storage = field.get("storage")
        other_storage = field.get("other_remark_storage")
        if not isinstance(storage, str) or not storage.startswith("patient_baseline."):
            continue
        if not isinstance(other_storage, str) or not other_storage.startswith("patient_baseline."):
            continue

        parent_parts = storage.removeprefix("patient_baseline.").split(".")
        remark_parts = other_storage.removeprefix("patient_baseline.").split(".")

        present_parent, parent_val = _get_submitted_value(data, parent_parts)
        present_r, remark_val = _get_submitted_value(data, remark_parts)
        remark_key = ".".join(remark_parts)

        if present_parent and parent_val == "其他":
            if field.get("required_for_complete") and (not present_r or _is_blank(remark_val)):
                out[remark_key] = "选择「其他」时必须填写备注"

        if present_r and not _is_blank(remark_val) and not isinstance(remark_val, str):
            out[remark_key] = "必须是文本"

    return out


def _get_submitted_value(data: Mapping[str, Any], parts: list[str]) -> tuple[bool, Any]:
    current: Any = data
    for part in parts:
        if not isinstance(current, Mapping):
            return True, _BAD_PARENT
        if part not in current:
            return False, None
        current = current[part]
    return True, current


def _validate_value(field: Mapping[str, Any], value: Any) -> str | None:
    if value is _BAD_PARENT:
        return "上级字段必须是对象"

    widget = field.get("widget")
    options = field.get("options")

    if widget == "number":
        if _is_blank(value):
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "必须是数字"
        return None

    if widget == "single_choice":
        if _is_blank(value):
            return None
        if isinstance(options, list):
            if value not in options:
                return "不在可选项中"
            return None
        if not isinstance(value, str):
            return "必须是字符串"
        return None

    if widget == "multi_choice":
        if _is_blank(value):
            return None
        if not isinstance(value, list):
            return "必须是列表"
        if isinstance(options, list):
            invalid = [item for item in value if item not in options]
            if invalid:
                return "包含无效选项"
        return None

    if widget == "date":
        if _is_blank(value):
            return None
        if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
            return "日期格式应为 YYYY-MM-DD"
        return None

    if widget in {"text", "textarea"}:
        if value is None or isinstance(value, (str, int, float)):
            return None
        return "必须是文本"

    return None


def _is_blank(value: Any) -> bool:
    return value is None or value == ""
