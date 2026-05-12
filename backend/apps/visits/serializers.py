from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from apps.crf.registry_validate import validate_visit_form_data_patch
from rest_framework import serializers

from .models import VisitRecord

logger = logging.getLogger(__name__)


class VisitRecordListSerializer(serializers.ModelSerializer):
    """列表用：嵌套患者/项目展示字段，不含 form_data。"""

    patient_id = serializers.IntegerField(source="project_patient.patient_id", read_only=True)
    patient_name = serializers.CharField(source="project_patient.patient.name", read_only=True)
    patient_phone = serializers.CharField(source="project_patient.patient.phone", read_only=True)
    project_id = serializers.IntegerField(source="project_patient.project_id", read_only=True)
    project_name = serializers.CharField(source="project_patient.project.name", read_only=True)

    class Meta:
        model = VisitRecord
        fields = [
            "id",
            "project_patient",
            "visit_type",
            "status",
            "visit_date",
            "patient_id",
            "patient_name",
            "patient_phone",
            "project_id",
            "project_name",
        ]
        read_only_fields = fields


CLIENT_WRITABLE_FORM_DATA_KEYS = ("assessments", "crf")


def _deep_merge(base: Any, patch: Any) -> Any:
    """
    Recursively merge dict-like trees.

    - If both sides are dicts: merge keys recursively
    - Otherwise: patch wins
    """
    if not isinstance(base, dict) or not isinstance(patch, dict):
        return patch

    merged = dict(base)
    for k, v in patch.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def _normalize_stored_form_data(raw: Any) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    assessments = data.get("assessments")
    computed = data.get("computed_assessments")
    return {
        **data,
        "assessments": assessments if isinstance(assessments, dict) else {},
        "computed_assessments": computed if isinstance(computed, dict) else {},
    }


def _normalize_incoming_form_data(raw: Any) -> Dict[str, Any]:
    """
    Normalize incoming PATCH/PUT form_data payload.

    Important: we intentionally do NOT auto-fill missing keys here, so that
    partial updates keep "not provided" semantics (i.e., don't clear existing).
    """
    # Keep non-dict as-is so validate() can raise a 400 with good message.
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        return {"__raw__": raw}
    data = raw
    # Drop external computed_assessments entirely (Task 1 contract).
    data = {k: v for k, v in data.items() if k != "computed_assessments"}

    if "assessments" in data and not isinstance(data["assessments"], dict):
        # Treat non-dict assessments as invalid shape.
        return {**data, "assessments": data["assessments"]}
    return data


def _validate_known_assessment_types(assessments: Dict[str, Any]) -> Tuple[bool, str, str]:
    """
    Returns (ok, path, message). Only validates known fields when present.
    Unknown keys are allowed.
    """

    def _err(path: str, msg: str) -> Tuple[bool, str, str]:
        return False, path, msg

    if not isinstance(assessments, dict):
        return _err("assessments", "必须是对象(object)")

    def _is_number(v: Any) -> bool:
        # bool is a subclass of int; explicitly exclude it.
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    sppb = assessments.get("sppb")
    if sppb is not None:
        if not isinstance(sppb, dict):
            return _err("assessments.sppb", "必须是对象(object)")

        for k in ("balance", "gait", "chair_stand", "total"):
            if k in sppb and sppb[k] is not None and not _is_number(sppb[k]):
                return _err(f"assessments.sppb.{k}", "必须是数字(number)")

        for k in ("note",):
            if k in sppb and sppb[k] is not None and not isinstance(sppb[k], str):
                return _err(f"assessments.sppb.{k}", "必须是字符串(string)")

    moca = assessments.get("moca")
    if moca is not None:
        if not isinstance(moca, dict):
            return _err("assessments.moca", "必须是对象(object)")
        if "total" in moca and moca["total"] is not None and not _is_number(moca["total"]):
            return _err("assessments.moca.total", "必须是数字(number)")
        if "note" in moca and moca["note"] is not None and not isinstance(moca["note"], str):
            return _err("assessments.moca.note", "必须是字符串(string)")

    for k in ("tug_seconds", "grip_strength_kg"):
        if k in assessments and assessments[k] is not None and not _is_number(assessments[k]):
            return _err(f"assessments.{k}", "必须是数字(number)")

    if "frailty" in assessments and assessments["frailty"] is not None:
        frailty = assessments["frailty"]
        if not isinstance(frailty, str):
            return _err("assessments.frailty", "必须是字符串(string)")
        if frailty not in {"robust", "pre_frail", "frail"}:
            return _err("assessments.frailty", "必须是 robust | pre_frail | frail 之一")

    return True, "", ""


class VisitRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitRecord
        fields = [
            "id",
            "project_patient",
            "visit_type",
            "status",
            "visit_date",
            "form_data",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        if "form_data" not in attrs:
            return attrs

        incoming = _normalize_incoming_form_data(attrs.get("form_data"))
        if "__raw__" in incoming:
            raise serializers.ValidationError({"form_data": "必须是对象(object)"})

        errors: Dict[str, Any] = {}
        if "assessments" in incoming:
            ok, path, msg = _validate_known_assessment_types(incoming.get("assessments"))
            if not ok:
                errors[path] = msg

        instance = getattr(self, "instance", None)
        if instance is not None and any(key in incoming for key in CLIENT_WRITABLE_FORM_DATA_KEYS):
            registry_errors = validate_visit_form_data_patch(incoming, instance.visit_type)
            errors.update(registry_errors)

        if errors:
            # Make field path visible at top-level, per contract requirement.
            raise serializers.ValidationError(errors)

        attrs["form_data"] = incoming
        return attrs

    def to_representation(self, instance: VisitRecord) -> Dict[str, Any]:
        data = super().to_representation(instance)
        data["form_data"] = _normalize_stored_form_data(data.get("form_data"))
        return data

    def update(self, instance: VisitRecord, validated_data: Dict[str, Any]) -> VisitRecord:
        if "form_data" not in validated_data:
            return super().update(instance, validated_data)

        incoming = validated_data.pop("form_data") or {}
        current = _normalize_stored_form_data(instance.form_data)

        # External computed_assessments is always ignored. Keep current value.
        merged = dict(current)
        if isinstance(incoming, dict):
            for key in CLIENT_WRITABLE_FORM_DATA_KEYS:
                if key not in incoming:
                    continue
                incoming_value = incoming.get(key)
                if not isinstance(incoming_value, dict):
                    # Should have been caught by validate(), but keep defensive.
                    raise serializers.ValidationError({key: "必须是对象(object)"})
                current_value = current.get(key, {})
                if not isinstance(current_value, dict):
                    current_value = {}
                merged[key] = _deep_merge(current_value, incoming_value)

            unknown_keys = set(incoming) - set(CLIENT_WRITABLE_FORM_DATA_KEYS)
            if unknown_keys:
                logger.warning("Ignored unknown visit form_data keys: %s", sorted(unknown_keys))

        instance.form_data = _normalize_stored_form_data(merged)
        return super().update(instance, validated_data)

