import datetime

from rest_framework import serializers

from .models import Patient


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

