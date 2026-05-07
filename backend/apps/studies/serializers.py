from rest_framework import serializers

from .models import GroupingBatch, ProjectPatient, StudyGroup, StudyProject


class StudyProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyProject
        fields = [
            "id",
            "name",
            "description",
            "crf_template_version",
            "visit_plan",
            "status",
        ]
        read_only_fields = ["id"]


class StudyGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyGroup
        fields = [
            "id",
            "project",
            "name",
            "description",
            "target_ratio",
            "sort_order",
            "is_active",
        ]
        read_only_fields = ["id"]


class GroupingBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupingBatch
        fields = [
            "id",
            "project",
            "status",
            "confirmed_by",
            "confirmed_at",
        ]
        read_only_fields = ["id", "confirmed_by", "confirmed_at"]


class ProjectPatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectPatient
        fields = [
            "id",
            "project",
            "patient",
            "group",
            "grouping_batch",
            "enrolled_at",
            "grouping_status",
        ]
        read_only_fields = ["id", "enrolled_at"]

