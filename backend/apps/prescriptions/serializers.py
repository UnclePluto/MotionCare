from rest_framework import serializers

from .models import ActionLibraryItem, Prescription, PrescriptionAction


class ActionLibraryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionLibraryItem
        fields = [
            "id",
            "name",
            "training_type",
            "internal_type",
            "action_type",
            "execution_description",
            "key_points",
            "suggested_frequency",
            "suggested_duration_minutes",
            "suggested_sets",
            "default_difficulty",
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
            "execution_description_snapshot",
            "frequency",
            "duration_minutes",
            "sets",
            "difficulty",
            "notes",
            "sort_order",
        ]
        read_only_fields = ["id"]

