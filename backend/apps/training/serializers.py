from collections.abc import Mapping

from rest_framework import serializers

from apps.prescriptions.models import PrescriptionAction
from apps.studies.models import ProjectPatient

from .models import TrainingRecord


MAX_MOTION_QUALITY_NOTE_LENGTH = 2000


class StrictNonNegativeIntegerField(serializers.IntegerField):
    def __init__(self, **kwargs):
        kwargs.setdefault("min_value", 0)
        kwargs.setdefault("max_value", 2_147_483_647)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class StrictCharField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class MotionResultUpdateSerializer(serializers.Serializer):
    _allowed_fields = frozenset(
        {"total_count", "standard_count", "nonstandard_count", "quality_note"}
    )

    total_count = StrictNonNegativeIntegerField()
    standard_count = StrictNonNegativeIntegerField()
    nonstandard_count = StrictNonNegativeIntegerField()
    quality_note = StrictCharField(
        required=False,
        allow_blank=True,
        max_length=MAX_MOTION_QUALITY_NOTE_LENGTH,
    )

    def to_internal_value(self, data):
        if not isinstance(data, Mapping) or not set(data).issubset(self._allowed_fields):
            raise serializers.ValidationError({"non_field_errors": ["动作结果格式无效"]})
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs["total_count"] != attrs["standard_count"] + attrs["nonstandard_count"]:
            raise serializers.ValidationError("总次数必须等于标准次数与非标准次数之和")
        return attrs


class TrainingRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingRecord
        fields = [
            "id",
            "project_patient",
            "prescription",
            "prescription_action",
            "training_date",
            "status",
            "actual_duration_minutes",
            "score",
            "form_data",
            "note",
            "motion_total_count",
            "motion_standard_count",
            "motion_nonstandard_count",
            "motion_quality_data",
            "motion_result_source",
            "motion_result_updated_by",
            "motion_result_updated_at",
        ]
        read_only_fields = [
            "id",
            "prescription",
            "motion_total_count",
            "motion_standard_count",
            "motion_nonstandard_count",
            "motion_quality_data",
            "motion_result_source",
            "motion_result_updated_by",
            "motion_result_updated_at",
        ]


class TrainingRecordCreateSerializer(serializers.Serializer):
    project_patient = serializers.PrimaryKeyRelatedField(queryset=ProjectPatient.objects.all())
    prescription_action = serializers.PrimaryKeyRelatedField(
        queryset=PrescriptionAction.objects.all()
    )
    training_date = serializers.DateField()
    status = serializers.ChoiceField(choices=TrainingRecord.Status.choices)
    actual_duration_minutes = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=2147483647
    )
    score = serializers.DecimalField(
        required=False, allow_null=True, max_digits=6, decimal_places=2
    )
    form_data = serializers.JSONField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)
