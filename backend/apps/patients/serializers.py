from rest_framework import serializers

from .models import Patient


class EnrollProjectsSerializer(serializers.Serializer):
    project_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )


class PatientSerializer(serializers.ModelSerializer):
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
            "symptom_note",
            "is_active",
        ]
        read_only_fields = ["id"]

