import re
from datetime import datetime

from rest_framework import serializers

from apps.patient_app.services import BINDING_CODE_PATTERN
from apps.training.models import TrainingRecord

BINDING_CODE_ERROR = "绑定码必须是 4 位数字"
CLIENT_OFFSET_DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})$"
)


class ClientOffsetDateTimeField(serializers.DateTimeField):
    default_error_messages = {
        **serializers.DateTimeField.default_error_messages,
        "timezone_required": "训练时间必须包含手机时区。",
    }

    def to_internal_value(self, value):
        if not isinstance(value, str) or not CLIENT_OFFSET_DATETIME_PATTERN.fullmatch(value):
            self.fail("timezone_required")
        try:
            client_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            self.fail("timezone_required")
        if (
            client_datetime.tzinfo is None
            or client_datetime.utcoffset() is None
        ):
            self.fail("timezone_required")
        return super().to_internal_value(value)


def client_local_date(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


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
    training_started_at = ClientOffsetDateTimeField()

    def validate(self, attrs):
        raw_started_at = self.initial_data["training_started_at"]
        if client_local_date(raw_started_at) != attrs["training_date"]:
            raise serializers.ValidationError(
                {"training_date": "训练日期必须与手机端开始时间一致。"}
            )
        return attrs


class PatientAppTrainingVideoSegmentSerializer(serializers.Serializer):
    file = serializers.FileField()
    duration_ms = serializers.IntegerField(min_value=1)
    size_bytes = serializers.IntegerField(min_value=1)


class PatientAppTrainingVideoFinalizeSerializer(serializers.Serializer):
    segment_count = serializers.IntegerField(min_value=1)
    actual_duration_seconds = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    training_ended_at = ClientOffsetDateTimeField(required=False)
