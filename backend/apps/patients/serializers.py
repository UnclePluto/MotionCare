import datetime

from rest_framework import serializers

from apps.crf.registry_validate import validate_patient_baseline_payload

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
        payload = {k: attrs[k] for k in attrs if k in _BASELINE_REGISTRY_FIELD_NAMES}
        if not payload:
            return attrs
        errors = validate_patient_baseline_payload(payload)
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
