from rest_framework import serializers

from .models import ProjectPatient, StudyGroup, StudyProject


class StudyProjectSerializer(serializers.ModelSerializer):
    patient_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = StudyProject
        fields = [
            "id",
            "name",
            "description",
            "crf_template_version",
            "visit_plan",
            "status",
            "patient_count",
        ]
        read_only_fields = ["id", "patient_count"]


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


class ConfirmGroupingAssignmentSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(min_value=1)
    group_id = serializers.IntegerField(min_value=1)


class ConfirmGroupingRatioSerializer(serializers.Serializer):
    group_id = serializers.IntegerField(min_value=1)
    target_ratio = serializers.IntegerField(min_value=1, max_value=100)


class ConfirmGroupingSerializer(serializers.Serializer):
    group_ratios = ConfirmGroupingRatioSerializer(many=True, required=False, allow_empty=False)
    assignments = ConfirmGroupingAssignmentSerializer(many=True, required=False, allow_empty=True)

    def validate(self, attrs):
        if not attrs.get("group_ratios") and not attrs.get("assignments"):
            raise serializers.ValidationError(
                {"detail": "请提交分组占比或本轮随机患者。"}
            )
        return attrs


class ProjectPatientSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    patient_phone = serializers.CharField(source="patient.phone", read_only=True)
    group_name = serializers.SerializerMethodField()
    visit_ids = serializers.SerializerMethodField()

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
            "enrolled_at",
            "visit_ids",
        ]
        read_only_fields = [
            "id",
            "enrolled_at",
            "patient_name",
            "patient_phone",
            "group_name",
            "visit_ids",
        ]

    def get_group_name(self, obj: ProjectPatient) -> str | None:
        return obj.group.name if obj.group_id else None

    def get_visit_ids(self, obj: ProjectPatient) -> dict[str, int]:
        from apps.visits.models import VisitRecord

        ids: dict[str, int] = {}
        for v in VisitRecord.objects.filter(project_patient=obj).only("id", "visit_type"):
            ids[v.visit_type] = v.id
        return ids
