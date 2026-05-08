from rest_framework import serializers

from .models import Patient, PatientBaseline


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
