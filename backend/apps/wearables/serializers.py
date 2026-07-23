from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.wearables.models import WearableBinding, WearableDevice

from .services.short_codes import ShortCodeExhausted, generate_device_short_code


class WearableDeviceSerializer(serializers.ModelSerializer):
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
