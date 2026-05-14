from rest_framework import serializers

from .models import ActionLibraryItem, Prescription, PrescriptionAction


class ActionLibraryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionLibraryItem
        fields = [
            "id",
            "source_key",
            "name",
            "training_type",
            "internal_type",
            "action_type",
            "instruction_text",
            "suggested_frequency",
            "suggested_duration_minutes",
            "default_difficulty",
            "video_url",
            "has_ai_supervision",
            "is_active",
        ]
        read_only_fields = ["id"]


class PrescriptionActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionAction
        fields = [
            "id",
            "prescription",
            "action_library_item",
            "action_name_snapshot",
            "training_type_snapshot",
            "internal_type_snapshot",
            "action_type_snapshot",
            "action_instruction_snapshot",
            "video_url_snapshot",
            "has_ai_supervision_snapshot",
            "weekly_frequency",
            "duration_minutes",
            "difficulty",
            "notes",
            "sort_order",
        ]
        read_only_fields = ["id"]


class PrescriptionSerializer(serializers.ModelSerializer):
    actions = PrescriptionActionSerializer(many=True, read_only=True)
    opened_by_name = serializers.CharField(source="opened_by.name", read_only=True)

    class Meta:
        model = Prescription
        fields = [
            "id",
            "project_patient",
            "version",
            "opened_by",
            "opened_by_name",
            "opened_at",
            "effective_at",
            "archived_at",
            "status",
            "note",
            "actions",
        ]
        read_only_fields = fields


class ActivateNowActionSerializer(serializers.Serializer):
    action_library_item = serializers.PrimaryKeyRelatedField(
        queryset=ActionLibraryItem.objects.filter(is_active=True)
    )
    weekly_frequency = serializers.CharField(
        required=False, allow_blank=True, max_length=80, default=""
    )
    duration_minutes = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=2147483647
    )
    difficulty = serializers.CharField(
        required=False, allow_blank=True, max_length=40, default=""
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    sort_order = serializers.IntegerField(
        required=False, min_value=0, max_value=2147483647, default=0
    )

    def to_internal_value(self, data):
        if isinstance(data, dict) and ("sets" in data or "repetitions" in data):
            raise serializers.ValidationError("处方动作仅支持时长，不支持组数或次数")
        return super().to_internal_value(data)

    def validate(self, attrs):
        duration_minutes = attrs.get("duration_minutes")
        if duration_minutes is None:
            raise serializers.ValidationError("动作需填写时长")
        return attrs


class ActivateNowPrescriptionSerializer(serializers.Serializer):
    expected_active_version = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    actions = ActivateNowActionSerializer(many=True, allow_empty=False)

    def validate_actions(self, actions):
        action_ids = [action["action_library_item"].id for action in actions]
        if len(action_ids) != len(set(action_ids)):
            raise serializers.ValidationError("重复动作，请检查后重试。")
        return actions
