import re

from rest_framework import serializers

from .action_library import is_official_motion_action, official_action_queryset
from .models import ActionLibraryItem, Prescription, PrescriptionAction
from .doses import count_unit_for, is_counted_motion
from .motion_videos import MotionVideoResolution, resolve_motion_video_url


def parse_weekly_target_count(value):
    if not value:
        return 1
    match = re.search(r"\d+", str(value))
    if not match:
        return 1
    count = int(match.group(0))
    return count if count > 0 else 1


def resolve_motion_video_url_safely(object_key, legacy_url):
    try:
        return resolve_motion_video_url(object_key, legacy_url)
    except Exception:
        return MotionVideoResolution(url="", unavailable=True)


class ActionLibraryItemSerializer(serializers.ModelSerializer):
    video_url = serializers.SerializerMethodField()
    video_configured = serializers.SerializerMethodField()

    def get_video_url(self, action):
        return resolve_motion_video_url_safely(action.video_object_key, action.video_url).url

    def get_video_configured(self, action):
        return bool(action.video_object_key or action.video_url)

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
            "video_configured",
            "has_ai_supervision",
            "is_active",
        ]
        read_only_fields = ["id"]


class PrescriptionActionSerializer(serializers.ModelSerializer):
    video_url_snapshot = serializers.SerializerMethodField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.dose_mode == "duration":
            for key in ("sets", "repetitions", "count_unit"):
                data.pop(key, None)
        return data

    def get_video_url_snapshot(self, action):
        return resolve_motion_video_url_safely(
            action.video_object_key_snapshot,
            action.video_url_snapshot,
        ).url

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
            "dose_mode",
            "repetitions",
            "sets",
            "count_unit",
            "weekly_target_count",
            "difficulty",
            "notes",
            "sort_order",
        ]
        read_only_fields = ["id"]


class PrescriptionSerializer(serializers.ModelSerializer):
    actions = PrescriptionActionSerializer(many=True, read_only=True)
    opened_by_name = serializers.SerializerMethodField()

    def get_opened_by_name(self, prescription):
        return "系统切换" if prescription.migration_source else prescription.opened_by.name

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
            "migration_source",
        ]
        read_only_fields = fields


class ActivateNowActionSerializer(serializers.Serializer):
    repetitions = serializers.IntegerField(required=False, min_value=1, max_value=2147483647)
    sets = serializers.IntegerField(required=False, min_value=1, max_value=2147483647)
    action_library_item = serializers.PrimaryKeyRelatedField(
        queryset=official_action_queryset(ActionLibraryItem.objects.filter(is_active=True))
    )
    weekly_frequency = serializers.CharField(
        required=False, allow_blank=True, max_length=80, default=""
    )
    duration_minutes = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=2147483647
    )
    weekly_target_count = serializers.IntegerField(
        required=False, min_value=1, max_value=2147483647, default=1
    )
    difficulty = serializers.CharField(required=False, allow_blank=True, max_length=40, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    sort_order = serializers.IntegerField(
        required=False, min_value=0, max_value=2147483647, default=0
    )

    def to_internal_value(self, data):
        default_weekly = (
            isinstance(data, dict)
            and "weekly_target_count" not in data
            and not data.get("weekly_frequency")
        )
        if isinstance(data, dict) and (
            "weekly_target_count" not in data or data.get("weekly_target_count") is None
        ):
            data = data.copy()
            data["weekly_target_count"] = parse_weekly_target_count(data.get("weekly_frequency"))
        result = super().to_internal_value(data)
        if default_weekly and is_counted_motion(result["action_library_item"].source_key):
            result["weekly_target_count"] = 3
        return result

    def validate(self, attrs):
        action = attrs["action_library_item"]
        if is_counted_motion(action.source_key):
            attrs.update(
                dose_mode="sets",
                count_unit=count_unit_for(action.source_key),
                duration_minutes=None,
            )
            attrs.setdefault("repetitions", 10)
            attrs.setdefault("sets", 3)
            return attrs
        if "sets" in attrs or "repetitions" in attrs:
            raise serializers.ValidationError("该动作使用时长，不支持组数或个数")
        duration_minutes = attrs.get("duration_minutes")
        if duration_minutes is None:
            raise serializers.ValidationError("动作需填写时长")
        action_library_item = attrs["action_library_item"]
        if is_official_motion_action(action_library_item.source_key) and duration_minutes > 30:
            raise serializers.ValidationError("运动动作时长不能超过 30 分钟")
        return attrs


class ActivateNowPrescriptionSerializer(serializers.Serializer):
    expected_active_version = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    actions = ActivateNowActionSerializer(many=True, allow_empty=False)

    def validate_actions(self, actions):
        action_ids = [action["action_library_item"].id for action in actions]
        if len(action_ids) != len(set(action_ids)):
            raise serializers.ValidationError("重复动作，请检查后重试。")
        return actions
