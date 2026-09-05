from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from motion_analysis_contract import ContractValidationError, MotionCounts, validate_counts


class ActionAnalysisError(RuntimeError):
    """动作关键点流无法产出可信分析结果。"""


class ActionDataValidationError(ValueError):
    """动作层 DTO 或结果负载不符合稳定数据契约。"""


JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def _freeze_mapping(value: Mapping[str, object], *, field_name: str) -> Mapping[str, object]:
    frozen: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ActionDataValidationError(f"{field_name} 的键必须是非空字符串")
        frozen[key] = _freeze_value(item, field_name=field_name)
    return MappingProxyType(frozen)


def _freeze_value(value: object, *, field_name: str) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value, field_name=field_name)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item, field_name=field_name) for item in value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ActionDataValidationError(f"{field_name} 必须是有限数字")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise ActionDataValidationError(f"{field_name} 只能包含 JSON 基础类型")


def _to_json_value(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _to_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ActionDataValidationError("冻结结果包含无法导出的值")


@dataclass(frozen=True)
class PoseFrame:
    timestamp_ms: int
    named_keypoints: Mapping[str, tuple[float, float, float]]

    __hash__ = None

    def __post_init__(self) -> None:
        if isinstance(self.timestamp_ms, bool) or not isinstance(self.timestamp_ms, int):
            raise ActionDataValidationError("timestamp_ms 必须是整数")
        if not isinstance(self.named_keypoints, Mapping):
            raise ActionDataValidationError("named_keypoints 必须是映射")
        normalized: dict[str, tuple[float, float, float]] = {}
        for name, point in self.named_keypoints.items():
            if not isinstance(name, str) or not name:
                raise ActionDataValidationError("named_keypoints 的键必须是非空字符串")
            if (
                not isinstance(point, Sequence)
                or isinstance(point, (str, bytes))
                or len(point) != 3
            ):
                raise ActionDataValidationError("每个关键点必须包含 x、y、score")
            try:
                normalized[name] = (float(point[0]), float(point[1]), float(point[2]))
            except (TypeError, ValueError, OverflowError) as exc:
                raise ActionDataValidationError("关键点坐标和分数必须是数值") from exc
        object.__setattr__(self, "named_keypoints", MappingProxyType(normalized))


@dataclass(frozen=True)
class AnalysisResult:
    counts: MotionCounts
    payload: Mapping[str, object]

    __hash__ = None

    def __post_init__(self) -> None:
        if not isinstance(self.counts, MotionCounts):
            raise TypeError("counts 必须是 MotionCounts")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload 必须是映射")
        if validate_counts(self.payload) != self.counts:
            raise ContractValidationError("counts 与 payload 中的计数必须一致")
        object.__setattr__(
            self,
            "payload",
            _freeze_mapping(self.payload, field_name="payload"),
        )

    def to_json_dict(self) -> dict[str, JsonValue]:
        """导出可直接进入共享完成协议、且不共享内部引用的 JSON 对象。"""
        exported = _to_json_value(self.payload)
        if not isinstance(exported, dict):
            raise ActionDataValidationError("冻结结果根节点必须是对象")
        return exported


@runtime_checkable
class ActionPlugin(Protocol):
    source_key: str
    algorithm_version: str
    rule_version: str
    parameter_version: str

    def analyze(self, frames: Iterable[PoseFrame]) -> AnalysisResult: ...
