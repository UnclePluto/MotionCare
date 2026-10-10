from __future__ import annotations

from apps.visits.crf_date_answer import CrfVisitDateAnswerField, read_visit_date_answer, project_visit_date_answer
from apps.crf.answer_values import decode_crf_answer, reconcile_answer_patch

import logging
from typing import Any, Dict

from apps.crf.field_rules import validate_fields
from apps.crf.field_values import (
    BAD_PARENT,
    MISSING,
    changed_crf_paths,
    lookup_path,
    merge_crf_patch,
    prepare_visit_date_patch,
)
from apps.crf.registry_loader import load_crf_registry
from apps.crf.registry_validate import validate_crf_structure_patch
from apps.patients.models import PatientBaseline
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


def _normalize_stored_form_data(raw: Any) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    return {"assessments": {}, "computed_assessments": {}, **data}


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


def _validate_known_assessment_types(assessments, changed_paths):
    """Retain the old assessment aliases, but hard-validate only actual edits."""

    def touched(path):
        path = "visit.form_data.assessments" + ("." + path if path else "")
        return changed_paths is None or any(
            path == p or path.startswith(p + ".") or p.startswith(path + ".") for p in changed_paths
        )

    if not isinstance(assessments, dict):
        return {"assessments": "必须是对象(object)"} if touched("") else {}
    errors = {}
    for group, numbers in [
        ("sppb", ("balance", "gait", "chair_stand", "total")),
        ("moca", ("total",)),
    ]:
        value = assessments.get(group)
        if value is None:
            continue
        if not isinstance(value, dict):
            if touched(group):
                errors["assessments." + group] = "必须是对象(object)"
            continue
        for key in (*numbers, "note"):
            raw = decode_crf_answer(value.get(key))["value"]
            path = group + "." + key
            if raw is None or not touched(path):
                continue
            if key == "note":
                if not isinstance(raw, str):
                    errors["assessments." + path] = "必须是字符串(string)"
            elif isinstance(raw, bool) or not isinstance(raw, (int, float)):
                errors["assessments." + path] = "必须是数字(number)"
    for key in ("tug_seconds", "grip_strength_kg"):
        raw = decode_crf_answer(assessments.get(key))["value"]
        if (
            raw is not None
            and touched(key)
            and (isinstance(raw, bool) or not isinstance(raw, (int, float)))
        ):
            errors["assessments." + key] = "必须是数字(number)"
    frailty = decode_crf_answer(assessments.get("frailty"))["value"]
    if (
        frailty is not None
        and touched("frailty")
        and (not isinstance(frailty, str) or frailty not in {"robust", "pre_frail", "frail"})
    ):
        errors["assessments.frailty"] = "必须是 robust | pre_frail | frail 之一"
    return errors


class VisitRecordSerializer(serializers.ModelSerializer):
    visit_date = CrfVisitDateAnswerField(required=False,allow_null=True)
    project_id = serializers.IntegerField(source="project_patient.project_id", read_only=True)
    project_name = serializers.CharField(source="project_patient.project.name", read_only=True)
    project_status = serializers.CharField(source="project_patient.project.status", read_only=True)

    class Meta:
        model = VisitRecord
        fields = [
            "id",
            "project_patient",
            "project_id",
            "project_name",
            "project_status",
            "visit_type",
            "status",
            "visit_date",
            "form_data",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        instance = self.instance
        current = (
            {
                "visit_date": read_visit_date_answer(instance.visit_date,instance.form_data),
                "form_data": instance.form_data,
            }
            if instance is not None
            else {"visit_date": None, "form_data": {}}
        )
        patch = {key: attrs[key] for key in ("visit_date", "form_data") if key in attrs}
        if "form_data" in patch:
            incoming = _normalize_incoming_form_data(patch["form_data"])
            if "__raw__" in incoming:
                raise serializers.ValidationError({"form_data": "必须是对象(object)"})
            stored_form = current["form_data"] if isinstance(current["form_data"], dict) else {}
            for key in CLIENT_WRITABLE_FORM_DATA_KEYS:
                if key in incoming and not isinstance(incoming[key], dict):
                    if key not in stored_form or changed_crf_paths(stored_form[key], incoming[key]):
                        raise serializers.ValidationError({key: "必须是对象(object)"})
            unknown_keys = set(incoming) - set(CLIENT_WRITABLE_FORM_DATA_KEYS)
            if unknown_keys:
                logger.warning("Ignored unknown visit form_data keys: %s", sorted(unknown_keys))
            patch["form_data"] = {
                key: incoming[key] for key in CLIENT_WRITABLE_FORM_DATA_KEYS if key in incoming
            }
        explicit_answer=lookup_path(patch,'form_data.crf.meta.visit_date_answer')
        if 'visit_date' in patch and explicit_answer is not MISSING and explicit_answer is not BAD_PARENT and patch['visit_date'] != explicit_answer:
            raise serializers.ValidationError({'visit_date':'同次提交的日期答案不一致'})
        partial_path = "form_data.crf.meta.visit_date_parts"
        # An automatic clear must not manufacture structure over historical text.
        # The alternate value is already absent beneath a non-object parent.
        if not (
            "visit_date" in patch
            and lookup_path(patch, partial_path) is MISSING
            and lookup_path(current, partial_path) is BAD_PARENT
        ):
            patch = prepare_visit_date_patch(patch)
        visit_type = attrs.get("visit_type", instance.visit_type if instance else None)
        structure_errors = validate_crf_structure_patch(
            {"visit": current},
            {"visit": patch},
            scope="visit",
            visit_type=visit_type,
        )
        if structure_errors:
            raise serializers.ValidationError(
                {
                    path.removeprefix("visit.form_data.").removeprefix("visit."): message
                    for path, message in structure_errors.items()
                }
            )
        patch=reconcile_answer_patch({'visit':current},{'visit':patch},load_crf_registry()['fields'])['visit']
        candidate = merge_crf_patch(current, patch)
        target = attrs.get("project_patient", instance.project_patient if instance else None)
        context_changed = (
            instance is None
            or visit_type != instance.visit_type
            or target.pk != instance.project_patient_id
        )
        changed = None if context_changed else changed_crf_paths(current, candidate, prefix="visit")
        baseline = (
            PatientBaseline.objects.filter(patient_id=target.patient_id)
            .values(
                "subject_id",
                "name_initials",
                "demographics",
                "surgery_allergy",
                "comorbidities",
                "lifestyle",
                "baseline_medications",
            )
            .first()
        )
        form_data = candidate["form_data"]
        errors = _validate_known_assessment_types(
            form_data.get("assessments", {}) if isinstance(form_data, dict) else {}, changed
        )
        registry_errors = validate_fields(
            load_crf_registry(),
            {"visit": candidate},
            scope="visit",
            visit_type=visit_type,
            changed_paths=changed,
            baseline=baseline,
        )
        errors.update(
            {
                path.removeprefix("visit.form_data.").removeprefix("visit."): message
                for path, message in registry_errors.items()
            }
        )
        if errors:
            raise serializers.ValidationError(errors)
        for key in patch:
            attrs[key] = project_visit_date_answer(candidate[key]) if key == "visit_date" else candidate[key]
        return attrs

    def to_representation(self, instance: VisitRecord) -> Dict[str, Any]:
        data = super().to_representation(instance)
        data["visit_date"] = read_visit_date_answer(instance.visit_date,instance.form_data)
        data["form_data"] = _normalize_stored_form_data(data.get("form_data"))
        return data
