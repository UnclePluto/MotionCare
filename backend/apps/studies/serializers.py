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
    project_name = serializers.CharField(source="project.name", read_only=True)
    project_status = serializers.CharField(source="project.status", read_only=True)
    group_name = serializers.SerializerMethodField()
    visit_ids = serializers.SerializerMethodField()
    visit_summaries = serializers.SerializerMethodField()

    class Meta:
        model = ProjectPatient
        fields = [
            "id",
            "project",
            "project_name",
            "project_status",
            "patient",
            "patient_name",
            "patient_phone",
            "group",
            "group_name",
            "enrolled_at",
            "updated_at",
            "visit_ids",
            "visit_summaries",
        ]
        read_only_fields = [
            "id",
            "enrolled_at",
            "updated_at",
            "project_name",
            "project_status",
            "patient_name",
            "patient_phone",
            "group_name",
            "visit_ids",
            "visit_summaries",
        ]

    def get_group_name(self, obj: ProjectPatient) -> str | None:
        return obj.group.name if obj.group_id else None

    def _visits_by_type(self, obj: ProjectPatient):
        cached = getattr(obj, "_prefetched_objects_cache", {}).get("visits")
        visits = cached if cached is not None else obj.visits.all()
        return {v.visit_type: v for v in visits}

    def get_visit_ids(self, obj: ProjectPatient) -> dict[str, int]:
        return {visit_type: v.id for visit_type, v in self._visits_by_type(obj).items()}

    def get_visit_summaries(self, obj: ProjectPatient) -> dict[str, dict[str, object]]:
        out: dict[str, dict[str, object]] = {}
        visits = self._visits_by_type(obj)
        for visit_type in ("T0", "T1", "T2"):
            v = visits.get(visit_type)
            if v is None:
                continue
            out[visit_type] = {
                "id": v.id,
                "status": v.status,
                "visit_date": v.visit_date.isoformat() if v.visit_date else None,
            }
        return out
