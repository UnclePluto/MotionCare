from __future__ import annotations

import hashlib
import importlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean
from types import MappingProxyType
from typing import Any


PP_TINYPOSE_MODEL_NAME = "PP-TinyPose_128x96"
CAP_PROP_POS_MSEC = 0
CAP_PROP_FPS = 5
COCO_KEYPOINT_COUNT = 17
COCO_JOINT_INDEXES = MappingProxyType(
    {
        "left_shoulder": 5,
        "right_shoulder": 6,
        "left_elbow": 7,
        "right_elbow": 8,
        "left_wrist": 9,
        "right_wrist": 10,
        "left_hip": 11,
        "right_hip": 12,
    }
)


class MotionAnalysisDependencyError(RuntimeError):
    """真实视频推理依赖在部署环境中不可用。"""


class MotionAnalysisInferenceError(RuntimeError):
    """视频或 PP-TinyPose 输出不能形成可信的全帧流。"""


class InferenceDataValidationError(ValueError):
    """推理层 DTO 输入不满足严格数据契约。"""


def _finite_number(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InferenceDataValidationError(f"{field_name} 必须是数值")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise InferenceDataValidationError(f"{field_name} 必须是有限数值")
    return normalized


def _positive_dimension(value: object, *, field_name: str) -> float:
    normalized = _finite_number(value, field_name=field_name)
    if normalized <= 0:
        raise InferenceDataValidationError(f"{field_name} 必须大于 0")
    return normalized


def _freeze_named_keypoints(
    value: Mapping[str, Sequence[object]],
) -> Mapping[str, tuple[float, float, float]]:
    if set(value) != set(COCO_JOINT_INDEXES):
        raise InferenceDataValidationError("named_keypoints 必须包含肩、肘、腕、髋八个关键点")
    frozen: dict[str, tuple[float, float, float]] = {}
    for name, point in value.items():
        if not isinstance(name, str) or not name:
            raise InferenceDataValidationError("关键点名称必须是非空字符串")
        if isinstance(point, (str, bytes)) or not isinstance(point, Sequence) or len(point) != 3:
            raise InferenceDataValidationError("命名关键点必须包含 x、y、score")
        x = _finite_number(point[0], field_name=f"{name}.x")
        y = _finite_number(point[1], field_name=f"{name}.y")
        score = _finite_number(point[2], field_name=f"{name}.score")
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            raise InferenceDataValidationError(f"{name} 坐标必须位于 0 到 1")
        if not 0.0 <= score <= 1.0:
            raise InferenceDataValidationError(f"{name}.score 必须位于 0 到 1")
        frozen[name] = (x, y, score)
    return MappingProxyType(frozen)


def _fingerprint(
    raw_keypoints: tuple[tuple[float, float, float], ...],
    bbox: tuple[float, float, float, float],
) -> str:
    canonical = json.dumps(
        {
            "bbox": [round(value, 6) for value in bbox],
            "keypoints": [[round(value, 6) for value in point] for point in raw_keypoints],
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class PersonPose:
    raw_keypoints: tuple[tuple[float, float, float], ...]
    named_keypoints: Mapping[str, tuple[float, float, float]]
    bbox: tuple[float, float, float, float]
    mean_score: float
    fingerprint: str

    __hash__ = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.raw_keypoints, (str, bytes))
            or not isinstance(self.raw_keypoints, Sequence)
            or len(self.raw_keypoints) != COCO_KEYPOINT_COUNT
        ):
            raise InferenceDataValidationError("人体必须包含 17 个 COCO 关键点")
        raw: list[tuple[float, float, float]] = []
        for index, point in enumerate(self.raw_keypoints):
            if (
                isinstance(point, (str, bytes))
                or not isinstance(point, Sequence)
                or len(point) != 3
            ):
                raise InferenceDataValidationError("原始关键点必须包含 x、y、score")
            x = _finite_number(point[0], field_name=f"raw_keypoints[{index}].x")
            y = _finite_number(point[1], field_name=f"raw_keypoints[{index}].y")
            score = _finite_number(point[2], field_name=f"raw_keypoints[{index}].score")
            if not 0.0 <= score <= 1.0:
                raise InferenceDataValidationError("关键点 score 必须位于 0 到 1")
            raw.append((x, y, score))
        if not isinstance(self.named_keypoints, Mapping):
            raise InferenceDataValidationError("named_keypoints 必须是映射")
        named = _freeze_named_keypoints(self.named_keypoints)
        if (
            isinstance(self.bbox, (str, bytes))
            or not isinstance(self.bbox, Sequence)
            or len(self.bbox) != 4
        ):
            raise InferenceDataValidationError("bbox 必须包含四个值")
        bbox = tuple(_finite_number(item, field_name="bbox") for item in self.bbox)
        if not (0.0 <= bbox[0] <= bbox[2] <= 1.0 and 0.0 <= bbox[1] <= bbox[3] <= 1.0):
            raise InferenceDataValidationError("bbox 必须是有效归一化边界框")
        mean_score = _finite_number(self.mean_score, field_name="mean_score")
        if not 0.0 <= mean_score <= 1.0:
            raise InferenceDataValidationError("mean_score 必须位于 0 到 1")
        if not isinstance(self.fingerprint, str) or not self.fingerprint:
            raise InferenceDataValidationError("fingerprint 必须是非空字符串")
        object.__setattr__(self, "raw_keypoints", tuple(raw))
        object.__setattr__(self, "named_keypoints", named)
        object.__setattr__(self, "bbox", bbox)
        object.__setattr__(self, "mean_score", mean_score)

    @classmethod
    def from_coco_keypoints(
        cls,
        keypoints: object,
        *,
        frame_width: object,
        frame_height: object,
    ) -> PersonPose:
        width = _positive_dimension(frame_width, field_name="frame_width")
        height = _positive_dimension(frame_height, field_name="frame_height")
        if (
            isinstance(keypoints, (str, bytes))
            or not isinstance(keypoints, Sequence)
            or len(keypoints) != COCO_KEYPOINT_COUNT
        ):
            raise InferenceDataValidationError("人体必须包含 17 个 COCO 关键点")

        raw: list[tuple[float, float, float]] = []
        for index, point in enumerate(keypoints):
            if (
                isinstance(point, (str, bytes))
                or not isinstance(point, Sequence)
                or len(point) != 3
            ):
                raise InferenceDataValidationError("原始关键点必须包含 x、y、score")
            x = _finite_number(point[0], field_name=f"keypoints[{index}].x")
            y = _finite_number(point[1], field_name=f"keypoints[{index}].y")
            score = _finite_number(point[2], field_name=f"keypoints[{index}].score")
            if not 0.0 <= score <= 1.0:
                raise InferenceDataValidationError("关键点 score 必须位于 0 到 1")
            raw.append((x, y, score))

        normalized = {
            name: (
                max(0.0, min(1.0, raw[index][0] / width)),
                max(0.0, min(1.0, raw[index][1] / height)),
                raw[index][2],
            )
            for name, index in COCO_JOINT_INDEXES.items()
        }
        normalized_x = [max(0.0, min(1.0, point[0] / width)) for point in raw]
        normalized_y = [max(0.0, min(1.0, point[1] / height)) for point in raw]
        raw_tuple = tuple(raw)
        bbox = (min(normalized_x), min(normalized_y), max(normalized_x), max(normalized_y))
        return cls(
            raw_keypoints=raw_tuple,
            named_keypoints=normalized,
            bbox=bbox,
            mean_score=fmean(point[2] for point in raw_tuple),
            fingerprint=_fingerprint(raw_tuple, bbox),
        )


def _is_deeply_immutable(value: object) -> bool:
    if value is None or isinstance(value, (bool, int, float, complex, str, bytes)):
        return True
    if isinstance(value, tuple):
        return all(_is_deeply_immutable(item) for item in value)
    if isinstance(value, frozenset):
        return all(_is_deeply_immutable(item) for item in value)
    return False


def _freeze_image(image: object) -> object:
    if _is_deeply_immutable(image):
        return image
    copy_method = getattr(image, "copy", None)
    if not callable(copy_method):
        raise InferenceDataValidationError("image 必须可复制并冻结为只读")
    try:
        copied = copy_method()
    except Exception as exc:
        raise InferenceDataValidationError("image 无法创建独立只读副本") from exc
    if copied is image:
        raise InferenceDataValidationError("image.copy() 必须返回独立副本")
    setflags = getattr(copied, "setflags", None)
    if not callable(setflags):
        raise InferenceDataValidationError("image 副本不支持只读冻结")
    try:
        setflags(write=False)
    except Exception as exc:
        raise InferenceDataValidationError("image 副本无法冻结为只读") from exc
    flags = getattr(copied, "flags", None)
    if getattr(flags, "writeable", None) is not False:
        raise InferenceDataValidationError("image 副本未进入只读状态")
    return copied


@dataclass(frozen=True)
class InferenceFrame:
    timestamp_ms: int
    source_fps: float
    image: object
    people: tuple[PersonPose, ...]

    __hash__ = None

    def __post_init__(self) -> None:
        if isinstance(self.timestamp_ms, bool) or not isinstance(self.timestamp_ms, int):
            raise InferenceDataValidationError("timestamp_ms 必须是整数")
        if self.timestamp_ms < 0:
            raise InferenceDataValidationError("timestamp_ms 不得为负数")
        fps = _positive_dimension(self.source_fps, field_name="source_fps")
        if isinstance(self.people, (str, bytes)) or not isinstance(self.people, Sequence):
            raise InferenceDataValidationError("people 必须是人体序列")
        people = tuple(self.people)
        if any(not isinstance(person, PersonPose) for person in people):
            raise TypeError("people 只能包含 PersonPose")
        object.__setattr__(self, "source_fps", fps)
        object.__setattr__(self, "image", _freeze_image(self.image))
        object.__setattr__(self, "people", people)


def _result_payload(result: object) -> Mapping[str, object]:
    payload = getattr(result, "json", None)
    if callable(payload):
        payload = payload()
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise MotionAnalysisInferenceError("PP-TinyPose 返回了无效 JSON") from exc
    if not isinstance(payload, Mapping):
        raise MotionAnalysisInferenceError("PP-TinyPose 结果缺少 JSON 数据")
    return payload


def convert_paddlex_people(
    result: object,
    *,
    frame_width: object,
    frame_height: object,
) -> tuple[PersonPose, ...]:
    width = _positive_dimension(frame_width, field_name="frame_width")
    height = _positive_dimension(frame_height, field_name="frame_height")
    payload = _result_payload(result)
    try:
        result_data = payload["res"]
        people = result_data["kpts"]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise MotionAnalysisInferenceError("PP-TinyPose 结果结构无效") from exc
    if not isinstance(result_data, Mapping) or not isinstance(people, list):
        raise MotionAnalysisInferenceError("PP-TinyPose 人体关键点结构无效")

    valid_people: list[PersonPose] = []
    for person in people:
        if not isinstance(person, Mapping) or "keypoints" not in person:
            continue
        try:
            valid_people.append(
                PersonPose.from_coco_keypoints(
                    person["keypoints"],
                    frame_width=width,
                    frame_height=height,
                )
            )
        except InferenceDataValidationError:
            # 单个人体损坏不应丢弃同一帧中其它可用人体；根 payload 损坏仍会失败。
            continue
    return tuple(valid_people)


def load_motion_analysis_runtime() -> tuple[Any, Any]:
    try:
        cv2 = importlib.import_module("cv2")
        paddlex = importlib.import_module("paddlex")
    except ModuleNotFoundError as exc:
        raise MotionAnalysisDependencyError("动作分析推理依赖缺失") from exc
    create_model = getattr(paddlex, "create_model", None)
    if not callable(create_model):
        raise MotionAnalysisDependencyError("PaddleX 未提供 create_model")
    return cv2, create_model


def create_pose_model(*, device: str = "cpu") -> object:
    _, create_model = load_motion_analysis_runtime()
    return create_model(model_name=PP_TINYPOSE_MODEL_NAME, device=device, use_hpip=False)


def _first_prediction(model: object, frame: object) -> object:
    predict = getattr(model, "predict", None)
    if not callable(predict):
        raise MotionAnalysisInferenceError("PP-TinyPose 模型缺少 predict")
    predictions = predict(frame)
    try:
        return next(iter(predictions))
    except (StopIteration, TypeError) as exc:
        raise MotionAnalysisInferenceError("PP-TinyPose 未返回推理结果") from exc


class VideoPoseStream:
    """拥有 capture 生命周期的单遍全帧推理流；model 始终由调用方持有。"""

    def __init__(self, *, capture: object, model: object, source_fps: float):
        self.capture = capture
        self.model = model
        self._source_fps = source_fps
        self._decoded_frame_count = 0
        self._inferred_frame_count = 0
        self._inference_seconds = 0.0
        self._last_timestamp_ms = -1
        self._closed = False

    @property
    def source_fps(self) -> float:
        return self._source_fps

    @property
    def decoded_frame_count(self) -> int:
        return self._decoded_frame_count

    @property
    def inferred_frame_count(self) -> int:
        return self._inferred_frame_count

    @property
    def inference_seconds(self) -> float:
        return self._inference_seconds

    def __iter__(self) -> VideoPoseStream:
        return self

    def __next__(self) -> InferenceFrame:
        if self._closed:
            raise StopIteration
        try:
            read = getattr(self.capture, "read")
            ok, image = read()
            if not ok:
                self.close()
                if self._inferred_frame_count == 0:
                    raise MotionAnalysisInferenceError("训练视频没有可分析帧")
                raise StopIteration

            frame_index = self._decoded_frame_count
            self._decoded_frame_count += 1
            frame_height, frame_width = self._frame_size(image)
            timestamp_ms = self._timestamp(frame_index)

            started = time.monotonic()
            prediction = _first_prediction(self.model, image)
            self._inference_seconds += time.monotonic() - started
            self._inferred_frame_count += 1
            people = convert_paddlex_people(
                prediction,
                frame_width=frame_width,
                frame_height=frame_height,
            )
            return InferenceFrame(
                timestamp_ms=timestamp_ms,
                source_fps=self._source_fps,
                image=image,
                people=people,
            )
        except Exception:
            self.close()
            raise

    @staticmethod
    def _frame_size(image: object) -> tuple[float, float]:
        try:
            shape = image.shape  # type: ignore[union-attr]
            frame_height = _positive_dimension(shape[0], field_name="frame_height")
            frame_width = _positive_dimension(shape[1], field_name="frame_width")
        except (AttributeError, IndexError, TypeError, InferenceDataValidationError) as exc:
            raise MotionAnalysisInferenceError("视频帧尺寸无效") from exc
        return frame_height, frame_width

    def _timestamp(self, frame_index: int) -> int:
        period_ms = 1000.0 / self._source_fps
        fallback = frame_index * period_ms
        try:
            raw = float(self.capture.get(CAP_PROP_POS_MSEC) or 0.0)  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError, OverflowError):
            raw = math.nan
        tolerance = max(1000.0, period_ms * 2)
        reliable = math.isfinite(raw) and raw >= 0 and abs(raw - fallback) <= tolerance
        candidate = raw if reliable else fallback
        rounded = int(round(candidate))
        if rounded <= self._last_timestamp_ms:
            rounded = max(int(round(fallback)), self._last_timestamp_ms + 1)
        self._last_timestamp_ms = rounded
        return rounded

    def __enter__(self) -> VideoPoseStream:
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        release = getattr(self.capture, "release", None)
        if callable(release):
            release()


def open_full_frame_pose_stream(
    video_path: object,
    *,
    model: object | None = None,
    capture: object | None = None,
) -> VideoPoseStream:
    cv2 = None
    try:
        if model is None or capture is None:
            cv2, _ = load_motion_analysis_runtime()
        if model is None:
            model = create_pose_model()
        if capture is None:
            capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise MotionAnalysisInferenceError("训练视频无法解码")
        fps_value = capture.get(CAP_PROP_FPS)
        source_fps = _positive_dimension(fps_value, field_name="source_fps")
    except Exception as exc:
        release = getattr(capture, "release", None) if capture is not None else None
        if callable(release):
            release()
        if isinstance(exc, InferenceDataValidationError):
            raise MotionAnalysisInferenceError("训练视频帧率无效") from exc
        raise
    return VideoPoseStream(capture=capture, model=model, source_fps=source_fps)
