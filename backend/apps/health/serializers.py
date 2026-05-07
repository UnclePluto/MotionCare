from rest_framework import serializers

from .models import DailyHealthRecord


class DailyHealthRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyHealthRecord
        fields = [
            "id",
            "patient",
            "record_date",
            "steps",
            "exercise_minutes",
            "average_heart_rate",
            "max_heart_rate",
            "min_heart_rate",
            "sleep_hours",
            "note",
        ]
        read_only_fields = ["id"]

