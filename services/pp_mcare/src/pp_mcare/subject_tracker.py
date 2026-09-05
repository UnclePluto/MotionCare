from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from statistics import median
from types import MappingProxyType

from pp_mcare.actions.base import PoseFrame
from pp_mcare.pose_inference import InferenceFrame, PersonPose


SUBJECT_TRACKER_VERSION = "primary-subject-v1"
MAX_NORMALIZED_JUMP = 0.35
LOST_TIMEOUT_MS = 3000
MAX_AMBIGUITY_RATIO = 0.10
CENTRAL_REGION_MARGIN = 0.15
RELIABLE_KEYPOINT_SCORE = 0.5
AMBIGUOUS_DISTANCE_DELTA = 0.03


class SubjectUnstable(RuntimeError):
    """主训练者无法安全建立或维持。"""


@dataclass(frozen=True)
class TrackedPoseFrame:
    frame: InferenceFrame
    primary: PersonPose | None
    ambiguous: bool = False

    __hash__ = None

    def __post_init__(self) -> None:
        if not isinstance(self.frame, InferenceFrame):
            raise TypeError("frame 必须是 InferenceFrame")
        if self.primary is not None and not isinstance(self.primary, PersonPose):
            raise TypeError("primary 必须是 PersonPose 或 None")
        if not isinstance(self.ambiguous, bool):
            raise TypeError("ambiguous 必须是 bool")
        if self.ambiguous and self.primary is not None:
            raise ValueError("歧义帧不得输出主体")

    def to_action_frame(self) -> PoseFrame | None:
        if self.primary is None:
            return None
        return PoseFrame(
            timestamp_ms=self.frame.timestamp_ms,
            named_keypoints=self.primary.named_keypoints,
        )


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _bbox_iou(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    union = _bbox_area(left) + _bbox_area(right) - intersection
    return intersection / union if union > 0 else 0.0


def _keypoint_distance(previous: PersonPose, candidate: PersonPose) -> float | None:
    distances: list[float] = []
    common_names = previous.named_keypoints.keys() & candidate.named_keypoints.keys()
    for name in common_names:
        previous_point = previous.named_keypoints[name]
        candidate_point = candidate.named_keypoints[name]
        if (
            previous_point[2] >= RELIABLE_KEYPOINT_SCORE
            and candidate_point[2] >= RELIABLE_KEYPOINT_SCORE
        ):
            distances.append(
                math.hypot(
                    previous_point[0] - candidate_point[0],
                    previous_point[1] - candidate_point[1],
                )
            )
    return median(distances) if distances else None


@dataclass(frozen=True)
class _CandidateMatch:
    person: PersonPose
    distance: float
    iou: float


class PrimarySubjectTracker:
    def __init__(self) -> None:
        self._primary: PersonPose | None = None
        self._track_fingerprint: str | None = None
        self._last_primary_timestamp_ms: int | None = None
        self._last_observation_timestamp_ms: int | None = None
        self._total_frames = 0
        self._emitted_frames = 0
        self._missing_frames = 0
        self._ambiguous_frames = 0

    def observe(self, frame: InferenceFrame) -> TrackedPoseFrame:
        if not isinstance(frame, InferenceFrame):
            raise TypeError("frame 必须是 InferenceFrame")
        if (
            self._last_observation_timestamp_ms is not None
            and frame.timestamp_ms <= self._last_observation_timestamp_ms
        ):
            raise ValueError("追踪帧时间戳必须严格递增")
        self._last_observation_timestamp_ms = frame.timestamp_ms
        self._total_frames += 1

        if self._primary is None:
            selected = self._initialize(frame.people)
            if selected is None:
                raise SubjectUnstable("无法建立画面中心的主训练者")
            return self._emit(frame, selected)

        matches = self._matches(frame.people)
        if not matches:
            return self._skip(frame, ambiguous=False)
        if self._is_ambiguous(matches):
            return self._skip(frame, ambiguous=True)
        return self._emit(frame, matches[0].person)

    def finish(self) -> Mapping[str, object]:
        ambiguity_ratio = self._ambiguous_frames / self._total_frames if self._total_frames else 0.0
        if ambiguity_ratio > MAX_AMBIGUITY_RATIO:
            raise SubjectUnstable("主训练者歧义帧占比超过 10%")
        coverage_ratio = self._emitted_frames / self._total_frames if self._total_frames else 0.0
        return MappingProxyType(
            {
                "subject_tracker_version": SUBJECT_TRACKER_VERSION,
                "max_normalized_jump": MAX_NORMALIZED_JUMP,
                "lost_timeout_ms": LOST_TIMEOUT_MS,
                "max_ambiguity_ratio": MAX_AMBIGUITY_RATIO,
                "total_frames": self._total_frames,
                "emitted_frames": self._emitted_frames,
                "missing_frames": self._missing_frames,
                "ambiguous_frames": self._ambiguous_frames,
                "subject_coverage_ratio": coverage_ratio,
                "ambiguity_ratio": ambiguity_ratio,
            }
        )

    @staticmethod
    def _initialize(people: tuple[PersonPose, ...]) -> PersonPose | None:
        central = []
        for person in people:
            center_x, center_y = _bbox_center(person.bbox)
            if (
                CENTRAL_REGION_MARGIN <= center_x <= 1.0 - CENTRAL_REGION_MARGIN
                and CENTRAL_REGION_MARGIN <= center_y <= 1.0 - CENTRAL_REGION_MARGIN
            ):
                central.append(person)
        if not central:
            return None
        return max(central, key=lambda person: (_bbox_area(person.bbox), person.mean_score))

    def _matches(self, people: tuple[PersonPose, ...]) -> list[_CandidateMatch]:
        assert self._primary is not None
        matches: list[_CandidateMatch] = []
        for person in people:
            distance = _keypoint_distance(self._primary, person)
            iou = _bbox_iou(self._primary.bbox, person.bbox)
            if distance is None:
                if iou <= 0.0:
                    continue
                distance = 1.0 - iou
            elif distance > MAX_NORMALIZED_JUMP + 1e-12:
                continue
            matches.append(_CandidateMatch(person=person, distance=distance, iou=iou))
        matches.sort(key=lambda match: (match.distance, -match.iou, match.person.fingerprint))
        return matches

    @staticmethod
    def _is_ambiguous(matches: list[_CandidateMatch]) -> bool:
        if len(matches) < 2:
            return False
        best, second = matches[:2]
        return second.distance - best.distance <= AMBIGUOUS_DISTANCE_DELTA

    def _emit(self, frame: InferenceFrame, person: PersonPose) -> TrackedPoseFrame:
        if self._track_fingerprint is None:
            self._track_fingerprint = person.fingerprint
        elif person.fingerprint != self._track_fingerprint:
            person = replace(person, fingerprint=self._track_fingerprint)
        self._primary = person
        self._last_primary_timestamp_ms = frame.timestamp_ms
        self._emitted_frames += 1
        return TrackedPoseFrame(frame=frame, primary=person)

    def _skip(self, frame: InferenceFrame, *, ambiguous: bool) -> TrackedPoseFrame:
        if ambiguous:
            self._ambiguous_frames += 1
        else:
            self._missing_frames += 1
        assert self._last_primary_timestamp_ms is not None
        if frame.timestamp_ms - self._last_primary_timestamp_ms >= LOST_TIMEOUT_MS:
            raise SubjectUnstable("主训练者连续失锁达到 3000ms")
        return TrackedPoseFrame(frame=frame, primary=None, ambiguous=ambiguous)
