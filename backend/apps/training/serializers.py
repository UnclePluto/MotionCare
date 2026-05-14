from rest_framework import serializers

from apps.prescriptions.models import PrescriptionAction
from apps.studies.models import ProjectPatient

from .models import TrainingRecord


class TrainingRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingRecord
        fields = [
            "id",
            "project_patient",
            "prescription",
            "prescription_action",
            "training_date",
            "status",
            "actual_duration_minutes",
            "score",
            "form_data",
            "note",
        ]
        read_only_fields = ["id", "prescription"]


class TrainingRecordCreateSerializer(serializers.Serializer):
    project_patient = serializers.PrimaryKeyRelatedField(queryset=ProjectPatient.objects.all())
    prescription_action = serializers.PrimaryKeyRelatedField(queryset=PrescriptionAction.objects.all())
    training_date = serializers.DateField()
    status = serializers.ChoiceField(choices=TrainingRecord.Status.choices)
    actual_duration_minutes = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=2147483647
    )
    score = serializers.DecimalField(
        required=False, allow_null=True, max_digits=6, decimal_places=2
    )
    form_data = serializers.JSONField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)
