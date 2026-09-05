from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

PROTOCOL_VERSION = "1"


class ContractValidationError(ValueError):
    pass


JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def _reject_invalid_protocol_version(payload: Mapping[str, object]) -> None:
    version = payload.get("protocol_version")
    if version != PROTOCOL_VERSION:
        raise ContractValidationError("不支持的协议版本")


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field_name} 必须是对象")
    return value


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractValidationError(f"{field_name} 必须是字符串")
    return value


def _require_int(value: object, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        if minimum == 0:
            raise ContractValidationError(f"{field_name} 必须是非负整数")
        raise ContractValidationError(f"{field_name} 必须是正整数")
    return value


def _normalize_json_value(value: object, field_name: str) -> JsonValue:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractValidationError(f"{field_name} 必须是 JSON 基础类型")
        return value
    if isinstance(value, list):
        return [_normalize_json_value(item, field_name) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractValidationError(f"{field_name} 的键必须是字符串")
            normalized[key] = _normalize_json_value(item, field_name)
        return normalized
    raise ContractValidationError(f"{field_name} 必须是 JSON 基础类型")


def _require_json_object(value: object, field_name: str) -> dict[str, JsonValue]:
    mapping = _require_mapping(value, field_name)
    normalized: dict[str, JsonValue] = {}
    for key, item in mapping.items():
        if not isinstance(key, str):
            raise ContractValidationError(f"{field_name} 的键必须是字符串")
        normalized[key] = _normalize_json_value(item, field_name)
    return normalized


@dataclass(frozen=True)
class WorkerCapability:
    action_source_key: str
    algorithm_version: str
    rule_version: str
    parameter_version: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "WorkerCapability":
        return cls(
            action_source_key=_require_str(payload.get("action_source_key"), "action_source_key"),
            algorithm_version=_require_str(payload.get("algorithm_version"), "algorithm_version"),
            rule_version=_require_str(payload.get("rule_version"), "rule_version"),
            parameter_version=_require_str(payload.get("parameter_version"), "parameter_version"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "action_source_key": self.action_source_key,
            "algorithm_version": self.algorithm_version,
            "rule_version": self.rule_version,
            "parameter_version": self.parameter_version,
        }


def capability_key(capability: WorkerCapability) -> tuple[str, str, str, str]:
    return (
        capability.action_source_key,
        capability.algorithm_version,
        capability.rule_version,
        capability.parameter_version,
    )


@dataclass(frozen=True)
class MotionCounts:
    total_count: int
    standard_count: int
    nonstandard_count: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "MotionCounts":
        return validate_counts(payload)

    def to_dict(self) -> dict[str, int]:
        return {
            "total_count": self.total_count,
            "standard_count": self.standard_count,
            "nonstandard_count": self.nonstandard_count,
        }


def validate_counts(payload: Mapping[str, object]) -> MotionCounts:
    values: list[int] = []
    for name in ("total_count", "standard_count", "nonstandard_count"):
        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ContractValidationError(f"{name} 必须是非负整数")
        values.append(value)
    total, standard, nonstandard = values
    if total != standard + nonstandard:
        raise ContractValidationError("total_count 必须等于 standard_count + nonstandard_count")
    return MotionCounts(total, standard, nonstandard)


@dataclass(frozen=True)
class DownloadGrant:
    url: str
    bucket: str
    object_key: str
    expires_at: str
    size_bytes: int
    content_type: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "DownloadGrant":
        return cls(
            url=_require_str(payload.get("url"), "download.url"),
            bucket=_require_str(payload.get("bucket"), "download.bucket"),
            object_key=_require_str(payload.get("object_key"), "download.object_key"),
            expires_at=_require_str(payload.get("expires_at"), "download.expires_at"),
            size_bytes=_require_int(payload.get("size_bytes"), "download.size_bytes", minimum=0),
            content_type=_require_str(payload.get("content_type"), "download.content_type"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "bucket": self.bucket,
            "object_key": self.object_key,
            "expires_at": self.expires_at,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
        }


@dataclass(frozen=True)
class UploadGrant:
    bucket: str
    object_key: str
    token: str
    expires_at: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "UploadGrant":
        return cls(
            bucket=_require_str(payload.get("bucket"), "upload.bucket"),
            object_key=_require_str(payload.get("object_key"), "upload.object_key"),
            token=_require_str(payload.get("token"), "upload.token"),
            expires_at=_require_str(payload.get("expires_at"), "upload.expires_at"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "bucket": self.bucket,
            "object_key": self.object_key,
            "token": self.token,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class SkeletonArtifact:
    bucket: str
    object_key: str
    object_hash: str
    size_bytes: int
    duration_seconds: float
    width: int
    height: int
    fps: float
    content_type: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "SkeletonArtifact":
        content_type = payload.get("content_type")
        if content_type is not None:
            content_type = _require_str(content_type, "skeleton.content_type")
        duration_seconds = _require_float(payload.get("duration_seconds"), "skeleton.duration_seconds")
        return cls(
            bucket=_require_str(payload.get("bucket"), "skeleton.bucket"),
            object_key=_require_str(payload.get("object_key"), "skeleton.object_key"),
            object_hash=_require_str(payload.get("object_hash"), "skeleton.object_hash"),
            size_bytes=_require_int(payload.get("size_bytes"), "skeleton.size_bytes", minimum=0),
            duration_seconds=duration_seconds,
            width=_require_int(payload.get("width"), "skeleton.width", minimum=1),
            height=_require_int(payload.get("height"), "skeleton.height", minimum=1),
            fps=_require_float(payload.get("fps"), "skeleton.fps"),
            content_type=content_type,
        )

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "bucket": self.bucket,
            "object_key": self.object_key,
            "object_hash": self.object_hash,
            "size_bytes": self.size_bytes,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "content_type": self.content_type,
        }
        return data


def _require_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractValidationError(f"{field_name} 必须是数字")
    result = float(value)
    if not math.isfinite(result):
        raise ContractValidationError(f"{field_name} 必须是有限数字")
    return result


@dataclass(frozen=True)
class ClaimedJob:
    protocol_version: str
    job_id: int
    action_source_key: str
    algorithm_version: str
    rule_version: str
    parameter_version: str
    subject_tracker_version: str
    lease_token: str
    lease_expires_at: str
    heartbeat_interval_seconds: int
    download: DownloadGrant
    upload: UploadGrant

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ClaimedJob":
        _reject_invalid_protocol_version(payload)
        download = _require_mapping(payload.get("download"), "download")
        upload = _require_mapping(payload.get("upload"), "upload")
        return cls(
            protocol_version=_require_str(payload.get("protocol_version"), "protocol_version"),
            job_id=_require_int(payload.get("job_id"), "job_id", minimum=1),
            action_source_key=_require_str(payload.get("action_source_key"), "action_source_key"),
            algorithm_version=_require_str(payload.get("algorithm_version"), "algorithm_version"),
            rule_version=_require_str(payload.get("rule_version"), "rule_version"),
            parameter_version=_require_str(payload.get("parameter_version"), "parameter_version"),
            subject_tracker_version=_require_str(
                payload.get("subject_tracker_version"), "subject_tracker_version"
            ),
            lease_token=_require_str(payload.get("lease_token"), "lease_token"),
            lease_expires_at=_require_str(payload.get("lease_expires_at"), "lease_expires_at"),
            heartbeat_interval_seconds=_require_int(
                payload.get("heartbeat_interval_seconds"), "heartbeat_interval_seconds", minimum=1
            ),
            download=DownloadGrant.from_dict(download),
            upload=UploadGrant.from_dict(upload),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "job_id": self.job_id,
            "action_source_key": self.action_source_key,
            "algorithm_version": self.algorithm_version,
            "rule_version": self.rule_version,
            "parameter_version": self.parameter_version,
            "subject_tracker_version": self.subject_tracker_version,
            "lease_token": self.lease_token,
            "lease_expires_at": self.lease_expires_at,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "download": self.download.to_dict(),
            "upload": self.upload.to_dict(),
        }


@dataclass(frozen=True)
class CompletionPayload:
    protocol_version: str
    lease_token: str
    idempotency_key: str
    counts: MotionCounts
    quality_summary: dict[str, JsonValue]
    result_payload: dict[str, JsonValue]
    skeleton: SkeletonArtifact

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CompletionPayload":
        _reject_invalid_protocol_version(payload)
        skeleton = _require_mapping(payload.get("skeleton"), "skeleton")
        counts = validate_counts(payload)
        return cls(
            protocol_version=_require_str(payload.get("protocol_version"), "protocol_version"),
            lease_token=_require_str(payload.get("lease_token"), "lease_token"),
            idempotency_key=_require_str(payload.get("idempotency_key"), "idempotency_key"),
            counts=counts,
            quality_summary=_require_json_object(payload.get("quality_summary"), "quality_summary"),
            result_payload=_require_json_object(payload.get("result_payload"), "result_payload"),
            skeleton=SkeletonArtifact.from_dict(skeleton),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "lease_token": self.lease_token,
            "idempotency_key": self.idempotency_key,
            **self.counts.to_dict(),
            "quality_summary": self.quality_summary,
            "result_payload": self.result_payload,
            "skeleton": self.skeleton.to_dict(),
        }
