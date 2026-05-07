from rest_framework import serializers

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
        read_only_fields = ["id"]

