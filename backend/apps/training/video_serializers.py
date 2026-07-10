from rest_framework import serializers

from .models import MotionAnalysisJob


class MotionAnalysisJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = MotionAnalysisJob
        fields = [
            "id",
            "training_video",
            "training_record",
            "status",
            "algorithm_name",
            "algorithm_version",
            "rule_version",
            "total_count",
            "standard_count",
            "nonstandard_count",
            "result_payload",
            "failure_reason",
            "started_at",
            "finished_at",
            "created_at",
        ]
        read_only_fields = fields
