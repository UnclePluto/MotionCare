from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.wearables.models import WearableBinding, WearableDevice

from .services.short_codes import ShortCodeExhausted, generate_device_short_code


class WearableDeviceSerializer(serializers.ModelSerializer):
    IDENTITY_FIELDS = {
        "provider",
        "external_device_id",
        "identifier_type",
        "short_code",
    }
    UPDATEABLE_FIELDS = {"model", "enabled"}

    class Meta:
        model = WearableDevice
        fields = [
            "id",
            "provider",
            "external_device_id",
            "identifier_type",
            "model",
            "short_code",
            "enabled",
            "last_communication_at",
            "last_battery_level",
            "last_device_status",
            "last_status_checked_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "short_code",
            "last_communication_at",
            "last_battery_level",
            "last_device_status",
            "last_status_checked_at",
            "created_at",
            "updated_at",
        ]
        validators = []

    def validate(self, attrs):
        provided_fields = set(self.initial_data.keys())
        if self.instance is None:
            if "short_code" in provided_fields:
                raise serializers.ValidationError(
                    {"short_code": "设备固定简码由系统生成，不能提交。"}
                )
            return attrs

        rejected_fields = provided_fields - self.UPDATEABLE_FIELDS
        if rejected_fields:
            errors = {}
            for field in rejected_fields:
                if field in self.IDENTITY_FIELDS:
                    errors[field] = "设备真实身份字段创建后不可修改。"
                else:
                    errors[field] = "该字段不可通过设备台账接口修改。"
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        for _ in range(32):
            try:
                with transaction.atomic():
                    short_code = generate_device_short_code()
                    return WearableDevice.objects.create(short_code=short_code, **validated_data)
            except IntegrityError:
                external_identity_exists = WearableDevice.objects.filter(
                    provider=validated_data["provider"],
                    external_device_id=validated_data["external_device_id"],
                ).exists()
                if external_identity_exists:
                    raise
        raise ShortCodeExhausted("设备固定简码生成冲突，请重试。")


class BindDeviceSerializer(serializers.Serializer):
    short_code = serializers.RegexField(r"^\d{4}$", max_length=4)


class UnbindDeviceSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        if "unbound_at" in self.initial_data:
            raise serializers.ValidationError(
                {"unbound_at": "解绑时间由服务端记录，不能提交。"}
            )
        return attrs


class WearableBindingSerializer(serializers.ModelSerializer):
    patient_id = serializers.IntegerField(read_only=True)
    device_id = serializers.IntegerField(read_only=True)
    short_code = serializers.CharField(source="device.short_code", read_only=True)

    class Meta:
        model = WearableBinding
        fields = [
            "id",
            "patient_id",
            "device_id",
            "short_code",
            "bound_at",
            "unbound_at",
            "bound_by",
            "unbound_by",
            "unbind_reason",
        ]
        read_only_fields = fields


class WearableMeasurementsQuerySerializer(serializers.Serializer):
    project_patient = serializers.IntegerField(required=False, min_value=1)
    metric_type = serializers.ChoiceField(
        choices=["heart_rate", "blood_pressure", "blood_oxygen"]
    )
    start = serializers.DateField()
    end = serializers.DateField()
    bucket = serializers.ChoiceField(
        choices=["raw", "5m", "15m", "30m", "1h"], default="raw", required=False
    )

    def validate(self, attrs):
        if attrs["start"] > attrs["end"]:
            raise serializers.ValidationError({"end": "结束日期不能早于开始日期。"})
        return attrs


class WearableDailySummariesQuerySerializer(serializers.Serializer):
    project_patient = serializers.IntegerField(required=False, min_value=1)
    start = serializers.DateField()
    end = serializers.DateField()
    bucket = serializers.CharField(required=False)

    def validate(self, attrs):
        if attrs["start"] > attrs["end"]:
            raise serializers.ValidationError({"end": "结束日期不能早于开始日期。"})
        if attrs.get("bucket") not in (None, "raw"):
            raise serializers.ValidationError({"bucket": "步数只提供按日总量，不支持分时分桶。"})
        return attrs


class WearableProjectSummaryQuerySerializer(serializers.Serializer):
    metric_type = serializers.ChoiceField(
        choices=["heart_rate", "blood_pressure", "blood_oxygen", "steps"]
    )
    start = serializers.DateField()
    end = serializers.DateField()

    def validate(self, attrs):
        if attrs["start"] > attrs["end"]:
            raise serializers.ValidationError({"end": "结束日期不能早于开始日期。"})
        return attrs
