import math

from rest_framework import serializers

from .models import MotionAnalysisJob


ANALYSIS_FAILURE_MESSAGE = "自动分析未完成，请填写训练结果"


def skeleton_metadata_is_complete(job: MotionAnalysisJob | None) -> bool:
    if job is None or job.status != MotionAnalysisJob.Status.SUCCEEDED:
        return False
    if not all(
        isinstance(value, str) and bool(value)
        for value in (
            job.skeleton_bucket,
            job.skeleton_object_key,
            job.skeleton_object_hash,
        )
    ):
        return False
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0
        for value in (
            job.skeleton_size_bytes,
            job.skeleton_width,
            job.skeleton_height,
        )
    ):
        return False
    return all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
        for value in (job.skeleton_duration_seconds, job.skeleton_fps)
    )


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
