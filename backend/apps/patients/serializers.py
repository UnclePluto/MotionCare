from rest_framework import serializers

from .models import Patient


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

