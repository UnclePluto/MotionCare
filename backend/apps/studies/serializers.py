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
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    patient_phone = serializers.CharField(source="patient.phone", read_only=True)
    group_name = serializers.SerializerMethodField()

    class Meta:
        model = ProjectPatient
        fields = [
            "id",
            "project",
            "patient",
            "patient_name",
            "patient_phone",
            "group",
            "group_name",
            "grouping_batch",
            "enrolled_at",
            "grouping_status",
        ]
        read_only_fields = ["id", "enrolled_at", "patient_name", "patient_phone", "group_name"]

    def get_group_name(self, obj: ProjectPatient) -> str | None:
        return obj.group.name if obj.group_id else None

