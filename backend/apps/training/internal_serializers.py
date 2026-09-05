import re
from collections.abc import Mapping

from motion_analysis_contract import (
    PROTOCOL_VERSION,
    CompletionPayload,
    ContractValidationError,
    WorkerCapability,
)
from rest_framework import serializers

from .internal_services import FailurePayload, parse_failure_payload


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
    worker_id = StrictStringField(max_length=120)
    protocol_version = ProtocolVersionField()
    capabilities = WorkerCapabilitySerializer(
        many=True,
        allow_empty=True,
        max_length=32,
    )

    def validate_worker_id(self, value):
        if not _IDENTIFIER_PATTERN.fullmatch(value):
            raise serializers.ValidationError("worker_id 格式无效")
        return value

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


class CompletionRequestSerializer(serializers.Serializer):
    _allowed_fields = frozenset(
        {
            "protocol_version",
            "lease_token",
            "idempotency_key",
            "algorithm_version",
            "rule_version",
            "parameter_version",
            "subject_tracker_version",
            "total_count",
            "standard_count",
            "nonstandard_count",
            "quality_summary",
            "result_payload",
            "skeleton",
        }
    )

    def to_internal_value(self, data):
        if not isinstance(data, Mapping) or set(data) != self._allowed_fields:
            raise serializers.ValidationError({"non_field_errors": ["完成数据格式无效"]})
        try:
            payload = CompletionPayload.from_dict(data)
        except ContractValidationError as exc:
            raise serializers.ValidationError(
                {"non_field_errors": ["完成数据格式无效"]}
            ) from exc

        if not _LEASE_TOKEN_PATTERN.fullmatch(payload.lease_token):
            raise serializers.ValidationError({"non_field_errors": ["完成数据格式无效"]})
        if not _IDENTIFIER_PATTERN.fullmatch(payload.idempotency_key) or len(
            payload.idempotency_key
        ) > 120:
            raise serializers.ValidationError({"non_field_errors": ["完成数据格式无效"]})
        skeleton = payload.skeleton
        if (
            len(payload.algorithm_version) > 80
            or len(payload.rule_version) > 80
            or len(payload.parameter_version) > 80
            or len(payload.subject_tracker_version) > 80
            or len(skeleton.bucket) > 120
            or len(skeleton.object_key) > 500
            or len(skeleton.object_hash) > 64
            or skeleton.duration_seconds < 0
            or skeleton.fps <= 0
            or skeleton.content_type != "video/mp4"
        ):
            raise serializers.ValidationError({"non_field_errors": ["完成数据格式无效"]})
        return {"payload": payload}


class FailureRequestSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        try:
            failure = parse_failure_payload(data)
        except ValueError as exc:
            raise serializers.ValidationError(
                {"non_field_errors": ["失败数据格式无效"]}
            ) from exc
        return {"failure": failure}

    def create(self, validated_data) -> FailurePayload:
        return validated_data["failure"]
