import math
import time
from collections import deque
from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable

from .pose_inference import MotionAnalysisInferenceError


SHOULDER_PRESS_RULE_VERSION = "shoulder-press-v2"
RELIABLE_SCORE_THRESHOLD = 0.4
SMOOTHING_WINDOW_MS = 200
RISE_HYSTERESIS = 0.08
FALL_HYSTERESIS = 0.08
MIN_EVENT_PROMINENCE = 0.15
MIN_EVENT_INTERVAL_MS = 800
MAX_MISSING_GAP_MS = 300
BILATERAL_MATCH_WINDOW_MS = 400
STANDARD_MIN_WRIST_LIFT = 0.55
STANDARD_MIN_PROMINENCE = 0.20
STANDARD_MIN_ELBOW_ANGLE = 150.0
STANDARD_MIN_DURATION_MS = 800
STANDARD_MAX_DURATION_MS = 8_000
STANDARD_MIN_COVERAGE_RATIO = 0.8
_monotonic = time.monotonic


def _below_threshold(value: float, threshold: float) -> bool:
    if value >= threshold:
        return False
    rounding_tolerance = 4 * max(math.ulp(value), math.ulp(threshold))
    return threshold - value > rounding_tolerance


@dataclass(frozen=True)
class SideMeasurement:
    side: str
    timestamp_ms: int
    wrist_lift: float
    elbow_angle: float
    score: float


@dataclass(frozen=True)
class SideEvent:
    side: str
    start_ms: int
    peak_ms: int
    end_ms: int
    prominence: float
    peak_wrist_lift: float
    peak_elbow_angle: float
    coverage_ratio: float
    opposite_coverage_ratio: float


def _point(keypoints: dict[str, Any], name: str) -> tuple[float, float, float]:
    point = keypoints[name]
    x = float(point["x"])
    y = float(point["y"])
    if not all(math.isfinite(value) for value in (x, y)):
        raise ValueError
    try:
        score = float(point.get("score", 0.0))
    except (TypeError, ValueError, OverflowError):
        score = 0.0
    if not math.isfinite(score):
        score = 0.0
    return x, y, score


def _angle(
    first: tuple[float, float],
    vertex: tuple[float, float],
    third: tuple[float, float],
) -> float:
    first_vector = (first[0] - vertex[0], first[1] - vertex[1])
    third_vector = (third[0] - vertex[0], third[1] - vertex[1])
    denominator = math.hypot(*first_vector) * math.hypot(*third_vector)
    if denominator <= 0:
        return 0.0
    cosine = sum(a * b for a, b in zip(first_vector, third_vector, strict=True)) / denominator
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _measurement(frame: dict[str, Any], side: str) -> SideMeasurement | None:
    try:
        keypoints = frame["keypoints"]
        shoulder_x, shoulder_y, shoulder_score = _point(
            keypoints, f"{side}_shoulder"
        )
        elbow_x, elbow_y, elbow_score = _point(keypoints, f"{side}_elbow")
        wrist_x, wrist_y, wrist_score = _point(keypoints, f"{side}_wrist")
        hip_x, hip_y, hip_score = _point(keypoints, f"{side}_hip")
        torso_length = math.hypot(shoulder_x - hip_x, shoulder_y - hip_y)
        if torso_length <= 0:
            return None
        timestamp_ms = int(round(float(frame["timestamp_ms"])))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None

    return SideMeasurement(
        side=side,
        timestamp_ms=timestamp_ms,
        wrist_lift=(shoulder_y - wrist_y) / torso_length,
        elbow_angle=_angle(
            (shoulder_x, shoulder_y),
            (elbow_x, elbow_y),
            (wrist_x, wrist_y),
        ),
        score=min(shoulder_score, elbow_score, wrist_score, hip_score),
    )


class SideEventDetector:
    def __init__(self, side: str):
        self.side = side
        self.window: deque[SideMeasurement] = deque()
        self.phase = "seeking"
        self.trough: SideMeasurement | None = None
        self.trough_lift = 0.0
        self.peak: SideMeasurement | None = None
        self.peak_lift = 0.0
        self.candidate_total_frames = 0
        self.candidate_reliable_frames = 0
        self.candidate_opposite_reliable_frames = 0
        self.last_valid_ms: int | None = None
        self.missing_since_last_valid = False
        self.last_event_peak_ms: int | None = None

    def observe(
        self,
        measurement: SideMeasurement,
        *,
        opposite_valid: bool,
    ) -> SideEvent | None:
        if (
            self.missing_since_last_valid
            and self.last_valid_ms is not None
            and measurement.timestamp_ms - self.last_valid_ms > MAX_MISSING_GAP_MS
        ):
            self._clear_candidate()
        self.last_valid_ms = measurement.timestamp_ms
        self.missing_since_last_valid = False
        self.window.append(measurement)
        cutoff_ms = measurement.timestamp_ms - SMOOTHING_WINDOW_MS
        while self.window and self.window[0].timestamp_ms < cutoff_ms:
            self.window.popleft()
        smoothed_lift = median(item.wrist_lift for item in self.window)

        if self.trough is None:
            self._reset_from(measurement, smoothed_lift, opposite_valid)
            return None

        if self.phase == "seeking" and smoothed_lift <= self.trough_lift:
            self._reset_from(measurement, smoothed_lift, opposite_valid)
            return None

        self._count_candidate_frame(measurement, opposite_valid)
        if self.phase == "seeking":
            if not _below_threshold(
                smoothed_lift - self.trough_lift, RISE_HYSTERESIS
            ):
                self.phase = "rising"
                self.peak = measurement
                self.peak_lift = smoothed_lift
            return None

        if smoothed_lift > self.peak_lift:
            self.peak = measurement
            self.peak_lift = smoothed_lift

        if _below_threshold(self.peak_lift - smoothed_lift, FALL_HYSTERESIS):
            return None

        event = self._complete_event(measurement.timestamp_ms)
        self._reset_from(measurement, smoothed_lift, opposite_valid)
        return event

    def observe_missing(self, timestamp_ms: int, *, opposite_valid: bool) -> None:
        self.missing_since_last_valid = True
        if self.trough is None:
            return
        self.candidate_total_frames += 1
        self.candidate_opposite_reliable_frames += int(opposite_valid)
        if (
            self.last_valid_ms is not None
            and timestamp_ms - self.last_valid_ms > MAX_MISSING_GAP_MS
        ):
            self._clear_candidate()

    def _count_candidate_frame(
        self, measurement: SideMeasurement, opposite_valid: bool
    ) -> None:
        self.candidate_total_frames += 1
        self.candidate_reliable_frames += int(
            measurement.score >= RELIABLE_SCORE_THRESHOLD
        )
        self.candidate_opposite_reliable_frames += int(opposite_valid)

    def _reset_from(
        self,
        measurement: SideMeasurement,
        smoothed_lift: float,
        opposite_valid: bool,
    ) -> None:
        self.phase = "seeking"
        self.trough = measurement
        self.trough_lift = smoothed_lift
        self.peak = None
        self.peak_lift = smoothed_lift
        self.candidate_total_frames = 1
        self.candidate_reliable_frames = int(
            measurement.score >= RELIABLE_SCORE_THRESHOLD
        )
        self.candidate_opposite_reliable_frames = int(opposite_valid)

    def _clear_candidate(self) -> None:
        self.window.clear()
        self.phase = "seeking"
        self.trough = None
        self.trough_lift = 0.0
        self.peak = None
        self.peak_lift = 0.0
        self.candidate_total_frames = 0
        self.candidate_reliable_frames = 0
        self.candidate_opposite_reliable_frames = 0
        self.last_valid_ms = None
        self.missing_since_last_valid = False

    def _complete_event(self, end_ms: int) -> SideEvent | None:
        if self.trough is None or self.peak is None:
            return None
        prominence = self.peak_lift - self.trough_lift
        far_enough_from_previous = (
            self.last_event_peak_ms is None
            or self.peak.timestamp_ms - self.last_event_peak_ms >= MIN_EVENT_INTERVAL_MS
        )
        if _below_threshold(
            prominence, MIN_EVENT_PROMINENCE
        ) or not far_enough_from_previous:
            return None

        total_frames = max(self.candidate_total_frames, 1)
        event = SideEvent(
            side=self.side,
            start_ms=self.trough.timestamp_ms,
            peak_ms=self.peak.timestamp_ms,
            end_ms=end_ms,
            prominence=prominence,
            peak_wrist_lift=self.peak.wrist_lift,
            peak_elbow_angle=self.peak.elbow_angle,
            coverage_ratio=self.candidate_reliable_frames / total_frames,
            opposite_coverage_ratio=(
                self.candidate_opposite_reliable_frames / total_frames
            ),
        )
        self.last_event_peak_ms = event.peak_ms
        return event


def _timestamp(frame: dict[str, Any]) -> int:
    try:
        timestamp = float(frame["timestamp_ms"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("关键点帧时间戳无效") from exc
    if not math.isfinite(timestamp):
        raise ValueError("关键点帧时间戳无效")
    return int(round(timestamp))


def _event_flags(events: tuple[SideEvent, ...]) -> list[str]:
    flags = []
    if any(
        _below_threshold(event.peak_wrist_lift, STANDARD_MIN_WRIST_LIFT)
        or _below_threshold(event.prominence, STANDARD_MIN_PROMINENCE)
        for event in events
    ):
        flags.append("range_too_small")
    if any(
        _below_threshold(event.peak_elbow_angle, STANDARD_MIN_ELBOW_ANGLE)
        for event in events
    ):
        flags.append("elbow_not_extended")

    start_ms = min(event.start_ms for event in events)
    end_ms = max(event.end_ms for event in events)
    if not STANDARD_MIN_DURATION_MS <= end_ms - start_ms <= STANDARD_MAX_DURATION_MS:
        flags.append("tempo_abnormal")
    if any(event.coverage_ratio < STANDARD_MIN_COVERAGE_RATIO for event in events):
        flags.append("low_confidence")
    if len(events) == 1 and events[0].opposite_coverage_ratio >= STANDARD_MIN_COVERAGE_RATIO:
        flags.append("bilateral_mismatch")
    return flags


def _rep_detail(events: tuple[SideEvent, ...]) -> dict[str, Any]:
    start_ms = min(event.start_ms for event in events)
    peak_ms = round(sum(event.peak_ms for event in events) / len(events))
    end_ms = max(event.end_ms for event in events)
    flags = _event_flags(events)
    return {
        "start_ms": start_ms,
        "peak_ms": peak_ms,
        "end_ms": end_ms,
        "duration_ms": end_ms - start_ms,
        "source_sides": [event.side for event in events],
        "is_standard": not flags,
        "flags": flags,
    }


def _merge_events(
    left_events: list[SideEvent], right_events: list[SideEvent]
) -> tuple[list[dict[str, Any]], int]:
    details = []
    bilateral_count = 0
    left_index = 0
    right_index = 0
    while left_index < len(left_events) or right_index < len(right_events):
        if left_index >= len(left_events):
            details.append(_rep_detail((right_events[right_index],)))
            right_index += 1
            continue
        if right_index >= len(right_events):
            details.append(_rep_detail((left_events[left_index],)))
            left_index += 1
            continue

        left_event = left_events[left_index]
        right_event = right_events[right_index]
        peak_difference = left_event.peak_ms - right_event.peak_ms
        if abs(peak_difference) <= BILATERAL_MATCH_WINDOW_MS:
            details.append(_rep_detail((left_event, right_event)))
            bilateral_count += 1
            left_index += 1
            right_index += 1
        elif peak_difference < 0:
            details.append(_rep_detail((left_event,)))
            left_index += 1
        else:
            details.append(_rep_detail((right_event,)))
            right_index += 1
    return details, bilateral_count


def analyze_shoulder_press_keypoints_v2(frames: Iterable[dict]) -> dict[str, Any]:
    started = _monotonic()
    detectors = {
        "left": SideEventDetector("left"),
        "right": SideEventDetector("right"),
    }
    events: dict[str, list[SideEvent]] = {"left": [], "right": []}
    reliable_frames = {"left": 0, "right": 0}
    processed_frames = 0
    measurable_frames = 0
    any_reliable_frames = 0
    first_timestamp_ms: int | None = None
    last_timestamp_ms: int | None = None
    source_fps: float | None = None

    for frame in frames:
        timestamp_ms = _timestamp(frame)
        if last_timestamp_ms is not None and timestamp_ms < last_timestamp_ms:
            raise ValueError("关键点帧时间戳不能倒退")
        if first_timestamp_ms is None:
            first_timestamp_ms = timestamp_ms
        last_timestamp_ms = timestamp_ms
        processed_frames += 1

        if source_fps is None:
            try:
                candidate_fps = float(frame["source_fps"])
            except (KeyError, TypeError, ValueError, OverflowError):
                pass
            else:
                if math.isfinite(candidate_fps) and candidate_fps > 0:
                    source_fps = candidate_fps

        measurements = {
            side: _measurement(frame, side) for side in ("left", "right")
        }
        if any(measurements.values()):
            measurable_frames += 1
        reliable = {
            side: measurement is not None
            and measurement.score >= RELIABLE_SCORE_THRESHOLD
            for side, measurement in measurements.items()
        }
        for side in ("left", "right"):
            reliable_frames[side] += int(reliable[side])
        any_reliable_frames += int(any(reliable.values()))

        for side, opposite in (("left", "right"), ("right", "left")):
            measurement = measurements[side]
            if measurement is None:
                detectors[side].observe_missing(
                    timestamp_ms, opposite_valid=reliable[opposite]
                )
                continue
            event = detectors[side].observe(
                measurement, opposite_valid=reliable[opposite]
            )
            if event is not None:
                events[side].append(event)

    if processed_frames == 0:
        raise MotionAnalysisInferenceError("关键点流没有可分析帧")
    if measurable_frames == 0:
        raise MotionAnalysisInferenceError("全程没有可用的人体关键点")

    rep_details, bilateral_count = _merge_events(events["left"], events["right"])
    for index, detail in enumerate(rep_details, start=1):
        detail["index"] = index

    total_count = len(rep_details)
    standard_count = sum(detail["is_standard"] for detail in rep_details)
    agreement_ratio = bilateral_count / max(
        len(events["left"]), len(events["right"]), 1
    )
    agreement_ratio = max(0.0, min(1.0, agreement_ratio))
    coverage_ratio = any_reliable_frames / processed_frames
    if coverage_ratio >= 0.9 and agreement_ratio >= 0.8:
        confidence_level = "high"
    elif coverage_ratio >= 0.7 and agreement_ratio >= 0.5:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    return {
        "total_count": total_count,
        "standard_count": standard_count,
        "nonstandard_count": total_count - standard_count,
        "rule_version": SHOULDER_PRESS_RULE_VERSION,
        "processed_frames": processed_frames,
        "source_fps": source_fps,
        "analysis_elapsed_ms": round((_monotonic() - started) * 1000),
        "left_event_count": len(events["left"]),
        "right_event_count": len(events["right"]),
        "bilateral_event_count": bilateral_count,
        "bilateral_agreement_ratio": agreement_ratio,
        "left_keypoint_coverage_ratio": reliable_frames["left"] / processed_frames,
        "right_keypoint_coverage_ratio": reliable_frames["right"] / processed_frames,
        "keypoint_coverage_ratio": coverage_ratio,
        "confidence_level": confidence_level,
        "rep_details": rep_details,
        "quality_flags": ["camera_angle_unverified"],
    }
