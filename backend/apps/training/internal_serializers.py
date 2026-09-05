import re

from motion_analysis_contract import PROTOCOL_VERSION, WorkerCapability
from rest_framework import serializers


_IDENTIFIER_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_STAGE_PATTERN = re.compile(r"\A[a-z][a-z0-9_]{0,31}\Z")
_LEASE_TOKEN_PATTERN = re.compile(r"\A[A-Za-z0-9_-]{32,128}\Z")


class StrictStringField(serializers.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault("trim_whitespace", False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class ProtocolVersionField(StrictStringField):
    def __init__(self, **kwargs):
        super().__init__(max_length=16, **kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if value != PROTOCOL_VERSION:
            raise serializers.ValidationError("不支持的协议版本")
        return value


class WorkerCapabilitySerializer(serializers.Serializer):
    action_source_key = StrictStringField(max_length=120)
    algorithm_version = StrictStringField(max_length=80)
    rule_version = StrictStringField(max_length=80)
    parameter_version = StrictStringField(max_length=80)

    def create(self, validated_data):
        return WorkerCapability(**validated_data)


class ClaimRequestSerializer(serializers.Serializer):
    worker_id = serializers.RegexField(_IDENTIFIER_PATTERN, max_length=120)
    protocol_version = ProtocolVersionField()
    capabilities = WorkerCapabilitySerializer(many=True, allow_empty=True)

    def validate_capabilities(self, value):
        return [WorkerCapability(**item) for item in value]


class HeartbeatRequestSerializer(serializers.Serializer):
    protocol_version = ProtocolVersionField()
    lease_token = serializers.RegexField(
        _LEASE_TOKEN_PATTERN,
        min_length=32,
        max_length=128,
        trim_whitespace=False,
        write_only=True,
    )
    stage = serializers.RegexField(
        _STAGE_PATTERN,
        max_length=32,
        trim_whitespace=False,
    )
