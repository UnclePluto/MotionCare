from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

PROTOCOL_VERSION = "1"


class ContractValidationError(ValueError):
    pass


JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def _reject_invalid_protocol_version(payload: Mapping[str, object]) -> None:
    _require_protocol_version(payload.get("protocol_version"))


def _require_protocol_version(value: object) -> str:
    version = _require_str(value, "protocol_version")
    if version != PROTOCOL_VERSION:
        raise ContractValidationError("不支持的协议版本")
    return version


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

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_source_key",
            _require_str(self.action_source_key, "action_source_key"),
        )
        object.__setattr__(
            self,
            "algorithm_version",
            _require_str(self.algorithm_version, "algorithm_version"),
        )
        object.__setattr__(self, "rule_version", _require_str(self.rule_version, "rule_version"))
        object.__setattr__(
            self,
            "parameter_version",
            _require_str(self.parameter_version, "parameter_version"),
        )

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

    def __post_init__(self) -> None:
        _validate_count_values(self.total_count, self.standard_count, self.nonstandard_count)

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
    return MotionCounts(
        *_validate_count_values(
            payload.get("total_count"),
            payload.get("standard_count"),
            payload.get("nonstandard_count"),
        )
    )


def _validate_count_values(
    total_count: object, standard_count: object, nonstandard_count: object
) -> tuple[int, int, int]:
    values: list[int] = []
    for name, value in (
        ("total_count", total_count),
        ("standard_count", standard_count),
        ("nonstandard_count", nonstandard_count),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ContractValidationError(f"{name} 必须是非负整数")
        values.append(value)
    total, standard, nonstandard = values
    if total != standard + nonstandard:
        raise ContractValidationError("total_count 必须等于 standard_count + nonstandard_count")
    return total, standard, nonstandard


@dataclass(frozen=True)
class DownloadGrant:
    url: str
    bucket: str
    object_key: str
    expires_at: str
    size_bytes: int
    content_type: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "url", _require_str(self.url, "download.url"))
        object.__setattr__(self, "bucket", _require_str(self.bucket, "download.bucket"))
        object.__setattr__(self, "object_key", _require_str(self.object_key, "download.object_key"))
        object.__setattr__(self, "expires_at", _require_str(self.expires_at, "download.expires_at"))
        object.__setattr__(
            self,
            "size_bytes",
            _require_int(self.size_bytes, "download.size_bytes", minimum=0),
        )
        object.__setattr__(
            self,
            "content_type",
            _require_str(self.content_type, "download.content_type"),
        )

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

    def __post_init__(self) -> None:
        object.__setattr__(self, "bucket", _require_str(self.bucket, "upload.bucket"))
        object.__setattr__(self, "object_key", _require_str(self.object_key, "upload.object_key"))
        object.__setattr__(self, "token", _require_str(self.token, "upload.token"))
        object.__setattr__(self, "expires_at", _require_str(self.expires_at, "upload.expires_at"))

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
    content_type: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "bucket", _require_str(self.bucket, "skeleton.bucket"))
        object.__setattr__(self, "object_key", _require_str(self.object_key, "skeleton.object_key"))
        object.__setattr__(self, "object_hash", _require_str(self.object_hash, "skeleton.object_hash"))
        object.__setattr__(
            self,
            "size_bytes",
            _require_int(self.size_bytes, "skeleton.size_bytes", minimum=0),
        )
        object.__setattr__(
            self,
            "duration_seconds",
            _require_float(self.duration_seconds, "skeleton.duration_seconds"),
        )
        object.__setattr__(self, "width", _require_int(self.width, "skeleton.width", minimum=1))
        object.__setattr__(self, "height", _require_int(self.height, "skeleton.height", minimum=1))
        object.__setattr__(self, "fps", _require_float(self.fps, "skeleton.fps"))
        object.__setattr__(
            self,
            "content_type",
            _require_str(self.content_type, "skeleton.content_type"),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "SkeletonArtifact":
        return cls(
            bucket=_require_str(payload.get("bucket"), "skeleton.bucket"),
            object_key=_require_str(payload.get("object_key"), "skeleton.object_key"),
            object_hash=_require_str(payload.get("object_hash"), "skeleton.object_hash"),
            size_bytes=_require_int(payload.get("size_bytes"), "skeleton.size_bytes", minimum=0),
            duration_seconds=_require_float(
                payload.get("duration_seconds"), "skeleton.duration_seconds"
            ),
            width=_require_int(payload.get("width"), "skeleton.width", minimum=1),
            height=_require_int(payload.get("height"), "skeleton.height", minimum=1),
            fps=_require_float(payload.get("fps"), "skeleton.fps"),
            content_type=_require_str(payload.get("content_type"), "skeleton.content_type"),
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

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "protocol_version",
            _require_protocol_version(self.protocol_version),
        )
        object.__setattr__(self, "job_id", _require_int(self.job_id, "job_id", minimum=1))
        object.__setattr__(
            self,
            "action_source_key",
            _require_str(self.action_source_key, "action_source_key"),
        )
        object.__setattr__(
            self,
            "algorithm_version",
            _require_str(self.algorithm_version, "algorithm_version"),
        )
        object.__setattr__(self, "rule_version", _require_str(self.rule_version, "rule_version"))
        object.__setattr__(
            self,
            "parameter_version",
            _require_str(self.parameter_version, "parameter_version"),
        )
        object.__setattr__(
            self,
            "subject_tracker_version",
            _require_str(self.subject_tracker_version, "subject_tracker_version"),
        )
        object.__setattr__(self, "lease_token", _require_str(self.lease_token, "lease_token"))
        object.__setattr__(
            self,
            "lease_expires_at",
            _require_str(self.lease_expires_at, "lease_expires_at"),
        )
        object.__setattr__(
            self,
            "heartbeat_interval_seconds",
            _require_int(self.heartbeat_interval_seconds, "heartbeat_interval_seconds", minimum=1),
        )
        if not isinstance(self.download, DownloadGrant):
            raise ContractValidationError("download 必须是 DownloadGrant")
        if not isinstance(self.upload, UploadGrant):
            raise ContractValidationError("upload 必须是 UploadGrant")

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

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "protocol_version",
            _require_protocol_version(self.protocol_version),
        )
        object.__setattr__(self, "lease_token", _require_str(self.lease_token, "lease_token"))
        object.__setattr__(
            self,
            "idempotency_key",
            _require_str(self.idempotency_key, "idempotency_key"),
        )
        if not isinstance(self.counts, MotionCounts):
            raise ContractValidationError("counts 必须是 MotionCounts")
        if not isinstance(self.skeleton, SkeletonArtifact):
            raise ContractValidationError("skeleton 必须是 SkeletonArtifact")
        object.__setattr__(
            self,
            "quality_summary",
            _require_json_object(self.quality_summary, "quality_summary"),
        )
        object.__setattr__(
            self,
            "result_payload",
            _require_json_object(self.result_payload, "result_payload"),
        )

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
            "quality_summary": _require_json_object(self.quality_summary, "quality_summary"),
            "result_payload": _require_json_object(self.result_payload, "result_payload"),
            "skeleton": self.skeleton.to_dict(),
        }
