from apps.crf.answer_values import reconcile_answer_patch
from apps.crf.registry_loader import load_crf_registry
import datetime

from rest_framework import serializers

from apps.crf.field_values import changed_crf_paths, merge_crf_patch
from apps.crf.registry_validate import (
    validate_crf_structure_patch,
    validate_patient_baseline_payload,
)

from .models import Patient, PatientBaseline

_BASELINE_REGISTRY_FIELD_NAMES = frozenset(
    {
        "subject_id",
        "name_initials",
        "demographics",
        "surgery_allergy",
        "comorbidities",
        "lifestyle",
        "baseline_medications",
    }
)


class EnrollmentItemSerializer(serializers.Serializer):
    project_id = serializers.IntegerField(min_value=1)
    group_id = serializers.IntegerField(min_value=1)


class EnrollProjectsSerializer(serializers.Serializer):
    enrollments = EnrollmentItemSerializer(many=True, allow_empty=False)


class PatientSerializer(serializers.ModelSerializer):
    primary_doctor_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Patient
        fields = [
            "id",
            "name",
            "gender",
            "birth_date",
            "age",
            "phone",
            "primary_doctor",
            "primary_doctor_name",
            "symptom_note",
            "is_active",
        ]
        read_only_fields = ["id", "primary_doctor_name"]

    def get_primary_doctor_name(self, obj: Patient) -> str | None:
        if obj.primary_doctor_id:
            return obj.primary_doctor.name
        return None

    @staticmethod
    def _age_from_birth(birth: datetime.date) -> int:
        today = datetime.date.today()
        years = today.year - birth.year
        if (today.month, today.day) < (birth.month, birth.day):
            years -= 1
        return years

    def validate(self, attrs: dict) -> dict:
        if "birth_date" not in attrs:
            return attrs
        bd = attrs.get("birth_date")
        if bd is None:
            attrs["age"] = None
        else:
            attrs["age"] = self._age_from_birth(bd)
        return attrs


class PatientBaselineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientBaseline
        fields = [
            "id",
            "patient",
            "subject_id",
            "name_initials",
            "demographics",
            "surgery_allergy",
            "comorbidities",
            "lifestyle",
            "baseline_medications",
        ]
        read_only_fields = ["id", "patient"]

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        if not any(k in attrs for k in _BASELINE_REGISTRY_FIELD_NAMES):
            return attrs
        current = (
            {key: getattr(self.instance, key) for key in _BASELINE_REGISTRY_FIELD_NAMES}
            if self.instance is not None
            else {}
        )
        structure_errors = validate_crf_structure_patch(
            {"patient_baseline": current},
            {"patient_baseline": attrs},
            scope="patient_baseline",
            visit_type=None,
        )
        if structure_errors:
            raise serializers.ValidationError(
                {
                    path.removeprefix("patient_baseline."): message
                    for path, message in structure_errors.items()
                }
            )
        canonical=reconcile_answer_patch({'patient_baseline':current},{'patient_baseline':attrs},load_crf_registry()['fields'])
        attrs=canonical['patient_baseline']
        candidate = merge_crf_patch(current, attrs)
        errors = validate_patient_baseline_payload(
            candidate,
            changed_paths=changed_crf_paths(current, candidate)
            if self.instance is not None
            else None,
        )
        if errors:
            raise serializers.ValidationError(errors)
        return {key: candidate[key] for key in attrs}
