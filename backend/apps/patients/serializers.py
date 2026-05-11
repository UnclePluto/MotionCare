from rest_framework import serializers

from .models import Patient


class EnrollmentItemSerializer(serializers.Serializer):
    project_id = serializers.IntegerField(min_value=1)
    group_id = serializers.IntegerField(min_value=1)


class EnrollProjectsSerializer(serializers.Serializer):
    enrollments = EnrollmentItemSerializer(many=True, allow_empty=False)


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

