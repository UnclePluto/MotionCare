from django.core.exceptions import ValidationError
from rest_framework import serializers

from .motion_analysis_storage import validate_published_skeleton_metadata
from .models import MotionAnalysisJob


ANALYSIS_FAILURE_MESSAGE = "自动分析未完成，请填写训练结果"


def skeleton_metadata_is_complete(job: MotionAnalysisJob | None) -> bool:
    try:
        validate_published_skeleton_metadata(job)
    except ValidationError:
        return False
    return True


class MotionAnalysisJobSerializer(serializers.ModelSerializer):
    analysis_failure_message = serializers.SerializerMethodField()
    skeleton_available = serializers.SerializerMethodField()

    class Meta:
        model = MotionAnalysisJob
        fields = [
            "id",
            "status",
            "analysis_failure_message",
            "skeleton_available",
            "started_at",
            "finished_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_analysis_failure_message(self, job):
        if job.status == MotionAnalysisJob.Status.FAILED:
            return ANALYSIS_FAILURE_MESSAGE
        return None

    def get_skeleton_available(self, job):
        return skeleton_metadata_is_complete(job)
