from rest_framework import serializers

from apps.patient_app.services import BINDING_CODE_PATTERN
from apps.training.models import TrainingRecord

BINDING_CODE_ERROR = "绑定码必须是 4 位数字"


class BindingCodeField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(
            max_length=4,
            min_length=4,
            trim_whitespace=False,
            error_messages={
                "required": BINDING_CODE_ERROR,
                "null": BINDING_CODE_ERROR,
                "blank": BINDING_CODE_ERROR,
                "invalid": BINDING_CODE_ERROR,
                "max_length": BINDING_CODE_ERROR,
                "min_length": BINDING_CODE_ERROR,
            },
            **kwargs,
        )

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError(BINDING_CODE_ERROR)
        value = super().to_internal_value(data)
        if not BINDING_CODE_PATTERN.fullmatch(value):
            raise serializers.ValidationError(BINDING_CODE_ERROR)
        return value


class PatientAppBindSerializer(serializers.Serializer):
    code = BindingCodeField()
    wx_openid = serializers.CharField(max_length=128)


class PatientAppTrainingRecordCreateSerializer(serializers.Serializer):
    prescription_action = serializers.IntegerField(min_value=1)
    training_date = serializers.DateField()
    status = serializers.ChoiceField(choices=TrainingRecord.Status.choices)
    actual_duration_minutes = serializers.IntegerField(
        min_value=0,
        max_value=2147483647,
        required=False,
        allow_null=True,
    )
    score = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    form_data = serializers.JSONField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)


class PatientAppTrainingVideoSessionSerializer(serializers.Serializer):
    client_session_id = serializers.UUIDField()
    prescription_action = serializers.IntegerField(min_value=1)
    training_date = serializers.DateField()
    expected_duration_seconds = serializers.IntegerField(min_value=1)


class PatientAppTrainingVideoSegmentSerializer(serializers.Serializer):
    file = serializers.FileField()
    duration_ms = serializers.IntegerField(min_value=1)
    size_bytes = serializers.IntegerField(min_value=1)


class PatientAppTrainingVideoFinalizeSerializer(serializers.Serializer):
    segment_count = serializers.IntegerField(min_value=1)
    actual_duration_seconds = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, default="")
