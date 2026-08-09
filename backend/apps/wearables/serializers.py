from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.wearables.models import WearableBinding, WearableDevice

from .services.bindings import mask_patient_name
from .services.short_codes import ShortCodeExhausted, generate_device_short_code


class WearableDeviceSerializer(serializers.ModelSerializer):
    imei = serializers.RegexField(
        r"^[0-9]{15}$",
        write_only=True,
        required=False,
        trim_whitespace=True,
        error_messages={"invalid": "IMEI 必须是 15 位数字。"},
    )
    is_bound = serializers.SerializerMethodField()
    current_patient_name = serializers.SerializerMethodField()
    last_sync_at = serializers.SerializerMethodField()

    IDENTITY_FIELDS = {
        "provider",
        "external_device_id",
        "identifier_type",
        "short_code",
        "imei",
    }
    UPDATEABLE_FIELDS = {"model", "enabled"}

    class Meta:
        model = WearableDevice
        fields = [
            "id",
            "provider",
            "external_device_id",
            "identifier_type",
            "imei",
            "model",
            "short_code",
            "enabled",
            "is_bound",
            "current_patient_name",
            "last_communication_at",
            "last_sync_at",
            "last_battery_level",
            "last_device_status",
            "last_status_checked_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "short_code",
            "is_bound",
            "current_patient_name",
            "last_communication_at",
            "last_sync_at",
            "last_battery_level",
            "last_device_status",
            "last_status_checked_at",
            "created_at",
            "updated_at",
        ]
        validators = []
        extra_kwargs = {
            "provider": {"required": False},
            "external_device_id": {"required": False},
            "identifier_type": {"required": False},
            "model": {"required": False},
        }

    def get_is_bound(self, instance):
        return bool(getattr(instance, "_is_bound", False))

    def get_current_patient_name(self, instance):
        name = getattr(instance, "_current_patient_name", None)
        return mask_patient_name(name) if name else None

    def get_last_sync_at(self, instance):
        value = getattr(instance, "_last_sync_at", None)
        return serializers.DateTimeField().to_representation(value) if value else None

    def validate(self, attrs):
        provided_fields = set(self.initial_data.keys())
        if self.instance is None:
            rejected_fields = provided_fields - {"imei"}
            if rejected_fields:
                raise serializers.ValidationError(
                    {field: "新增设备只允许提交 IMEI。" for field in rejected_fields}
                )
            if "imei" not in attrs:
                raise serializers.ValidationError({"imei": "请输入 IMEI。"})
            return attrs

        rejected_fields = provided_fields - self.UPDATEABLE_FIELDS
        if rejected_fields:
            errors = {}
            for field in rejected_fields:
                if field in self.IDENTITY_FIELDS:
                    errors[field] = "设备真实身份字段创建后不可修改。"
                else:
                    errors[field] = "该字段不可通过设备管理接口修改。"
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        imei = validated_data.pop("imei")
        if WearableDevice.objects.filter(
            identifier_type="imei",
            external_device_id=imei,
        ).exists():
            raise IntegrityError("duplicate IMEI")
        device_values = {
            "provider": "miwitracker",
            "external_device_id": imei,
            "identifier_type": "imei",
            "model": "",
            "enabled": True,
        }
        for _ in range(32):
            try:
                with transaction.atomic():
                    return WearableDevice.objects.create(
                        short_code=generate_device_short_code(),
                        **device_values,
                    )
            except IntegrityError:
                if WearableDevice.objects.filter(
                    provider="miwitracker",
                    external_device_id=imei,
                ).exists():
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
    page = serializers.IntegerField(min_value=1, default=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=500, default=200, required=False)

    def validate(self, attrs):
        if attrs["start"] > attrs["end"]:
            raise serializers.ValidationError({"end": "结束日期不能早于开始日期。"})
        if (attrs["end"] - attrs["start"]).days + 1 > 31:
            raise serializers.ValidationError({"end": "趋势查询最多 31 个自然日。"})
        return attrs


class WearableDailySummariesQuerySerializer(serializers.Serializer):
    project_patient = serializers.IntegerField(required=False, min_value=1)
    start = serializers.DateField()
    end = serializers.DateField()
    bucket = serializers.CharField(required=False)

    def validate(self, attrs):
        if attrs["start"] > attrs["end"]:
            raise serializers.ValidationError({"end": "结束日期不能早于开始日期。"})
        if (attrs["end"] - attrs["start"]).days + 1 > 366:
            raise serializers.ValidationError({"end": "汇总查询最多 366 个自然日。"})
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
        if (attrs["end"] - attrs["start"]).days + 1 > 366:
            raise serializers.ValidationError({"end": "汇总查询最多 366 个自然日。"})
        return attrs
