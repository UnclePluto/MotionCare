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
            "suggested_sets",
            "suggested_repetitions",
            "default_difficulty",
            "video_url",
            "has_ai_supervision",
            "is_active",
        ]
        read_only_fields = ["id"]


class PrescriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = [
            "id",
            "project_patient",
            "version",
            "opened_by",
            "opened_at",
            "effective_at",
            "status",
            "note",
        ]
        read_only_fields = ["id", "opened_at"]


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
            "sets",
            "repetitions",
            "difficulty",
            "notes",
            "sort_order",
        ]
        read_only_fields = ["id"]
