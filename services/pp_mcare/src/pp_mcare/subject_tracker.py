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
MINIMUM_COMMON_RELIABLE_KEYPOINTS = 4
MINIMUM_FALLBACK_IOU = 0.70
HISTORY_CLEAR_MATCH_DISTANCE = MAX_NORMALIZED_JUMP / 2
MAX_PREDICTION_INTERVALS = 3.0


class SubjectUnstable(RuntimeError):
    """主训练者无法安全建立或维持。"""


@dataclass(frozen=True)
class TrackedPoseFrame:
    frame: InferenceFrame
    primary: PersonPose | None
    ambiguous: bool = False
    observation_fingerprint: str | None = None

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
        if self.primary is None and self.observation_fingerprint is not None:
            raise ValueError("无主体帧不得包含 observation_fingerprint")
        if self.primary is not None and (
            not isinstance(self.observation_fingerprint, str) or not self.observation_fingerprint
        ):
            raise ValueError("稳定帧必须包含 observation_fingerprint")

    def to_action_frame(self) -> PoseFrame | None:
        if self.primary is None:
            return None
        if self.frame.image is None:
            return PoseFrame(self.frame.timestamp_ms, self.primary.named_keypoints)
        named = dict(self.primary.named_keypoints)
        # Tracking remains on the original eight points; only the action input
        # gains lower-body points. This preserves the deployed tracker identity.
        height, width = self.frame.image.shape[:2]
        for name, index in (
            ("left_knee", 13), ("right_knee", 14),
            ("left_ankle", 15), ("right_ankle", 16),
        ):
            x, y, score = self.primary.raw_keypoints[index]
            named[name] = (max(0, min(1, x / width)), max(0, min(1, y / height)), score)
        return PoseFrame(
            timestamp_ms=self.frame.timestamp_ms,
            named_keypoints=named,
            coordinate_aspect_ratio=width / height,
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


def _keypoint_distance(
    previous: PersonPose,
    candidate: PersonPose,
    *,
    prior: PersonPose | None,
    prediction_intervals: float,
) -> tuple[float | None, float | None, int]:
    last_distances: list[float] = []
    predicted_distances: list[float] = []
    common_names = previous.named_keypoints.keys() & candidate.named_keypoints.keys()
    for name in common_names:
        previous_point = previous.named_keypoints[name]
        candidate_point = candidate.named_keypoints[name]
        if (
            previous_point[2] >= RELIABLE_KEYPOINT_SCORE
            and candidate_point[2] >= RELIABLE_KEYPOINT_SCORE
        ):
            expected_x = previous_point[0]
            expected_y = previous_point[1]
            if prior is not None:
                prior_point = prior.named_keypoints[name]
                if prior_point[2] >= RELIABLE_KEYPOINT_SCORE:
                    expected_x += (previous_point[0] - prior_point[0]) * prediction_intervals
                    expected_y += (previous_point[1] - prior_point[1]) * prediction_intervals
            last_distances.append(
                math.hypot(
                    previous_point[0] - candidate_point[0],
                    previous_point[1] - candidate_point[1],
                )
            )
            predicted_distances.append(
                math.hypot(expected_x - candidate_point[0], expected_y - candidate_point[1])
            )
    if not last_distances:
        return None, None, 0
    return median(last_distances), median(predicted_distances), len(last_distances)


@dataclass(frozen=True)
class _CandidateMatch:
    person: PersonPose
    last_distance: float
    predicted_distance: float
    iou: float
    reliable_keypoint_count: int
    detection_index: int


class PrimarySubjectTracker:
    def __init__(self) -> None:
        self._primary: PersonPose | None = None
        self._prior_primary: PersonPose | None = None
        self._track_fingerprint: str | None = None
        self._last_primary_timestamp_ms: int | None = None
        self._prior_primary_timestamp_ms: int | None = None
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

        matches = self._matches(frame.people, frame_timestamp_ms=frame.timestamp_ms)
        if not matches:
            return self._skip(frame, ambiguous=False)
        selected = self._select_unambiguous(matches)
        if selected is None:
            return self._skip(frame, ambiguous=True)
        return self._emit(frame, selected.person)

    def finish(self) -> Mapping[str, object]:
        if self._primary is None or self._last_primary_timestamp_ms is None:
            raise SubjectUnstable("主训练者从未建立")
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
                "minimum_common_reliable_keypoints": MINIMUM_COMMON_RELIABLE_KEYPOINTS,
                "minimum_fallback_iou": MINIMUM_FALLBACK_IOU,
                "reliable_keypoint_score": RELIABLE_KEYPOINT_SCORE,
                "central_region_margin": CENTRAL_REGION_MARGIN,
                "ambiguous_distance_delta": AMBIGUOUS_DISTANCE_DELTA,
                "history_clear_match_distance": HISTORY_CLEAR_MATCH_DISTANCE,
                "max_prediction_intervals": MAX_PREDICTION_INTERVALS,
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

    def _matches(
        self,
        people: tuple[PersonPose, ...],
        *,
        frame_timestamp_ms: int,
    ) -> list[_CandidateMatch]:
        assert self._primary is not None
        prediction_intervals = self._prediction_intervals(frame_timestamp_ms)
        matches: list[_CandidateMatch] = []
        for detection_index, person in enumerate(people):
            last_distance, predicted_distance, reliable_count = _keypoint_distance(
                self._primary,
                person,
                prior=self._prior_primary,
                prediction_intervals=prediction_intervals,
            )
            iou = _bbox_iou(self._primary.bbox, person.bbox)
            if (
                last_distance is None
                or predicted_distance is None
                or reliable_count < MINIMUM_COMMON_RELIABLE_KEYPOINTS
            ):
                if iou < MINIMUM_FALLBACK_IOU:
                    continue
                last_distance = predicted_distance = 1.0 - iou
            elif last_distance > MAX_NORMALIZED_JUMP + 1e-12:
                continue
            else:
                if (
                    self._prior_primary is not None
                    and predicted_distance > HISTORY_CLEAR_MATCH_DISTANCE
                    and iou < MINIMUM_FALLBACK_IOU
                ):
                    continue
            matches.append(
                _CandidateMatch(
                    person=person,
                    last_distance=last_distance,
                    predicted_distance=predicted_distance,
                    iou=iou,
                    reliable_keypoint_count=reliable_count,
                    detection_index=detection_index,
                )
            )
        return matches

    def _prediction_intervals(self, frame_timestamp_ms: int) -> float:
        if (
            self._prior_primary is None
            or self._prior_primary_timestamp_ms is None
            or self._last_primary_timestamp_ms is None
        ):
            return 0.0
        historical_interval_ms = self._last_primary_timestamp_ms - self._prior_primary_timestamp_ms
        if historical_interval_ms <= 0:
            return 0.0
        elapsed_ms = frame_timestamp_ms - self._last_primary_timestamp_ms
        return min(MAX_PREDICTION_INTERVALS, elapsed_ms / historical_interval_ms)

    @staticmethod
    def _select_unambiguous(matches: list[_CandidateMatch]) -> _CandidateMatch | None:
        last_ranked = sorted(
            matches,
            key=lambda match: (match.last_distance, -match.iou, match.detection_index),
        )
        predicted_ranked = sorted(
            matches,
            key=lambda match: (match.predicted_distance, -match.iou, match.detection_index),
        )
        if last_ranked[0].detection_index != predicted_ranked[0].detection_index:
            return None
        if len(matches) > 1 and (
            last_ranked[1].last_distance - last_ranked[0].last_distance <= AMBIGUOUS_DISTANCE_DELTA
            or predicted_ranked[1].predicted_distance - predicted_ranked[0].predicted_distance
            <= AMBIGUOUS_DISTANCE_DELTA
        ):
            return None
        return last_ranked[0]

    def _emit(self, frame: InferenceFrame, person: PersonPose) -> TrackedPoseFrame:
        observation_fingerprint = person.fingerprint
        if self._track_fingerprint is None:
            self._track_fingerprint = person.fingerprint
        elif person.fingerprint != self._track_fingerprint:
            person = replace(person, fingerprint=self._track_fingerprint)
        self._prior_primary = self._primary
        self._prior_primary_timestamp_ms = self._last_primary_timestamp_ms
        self._primary = person
        self._last_primary_timestamp_ms = frame.timestamp_ms
        self._emitted_frames += 1
        return TrackedPoseFrame(
            frame=frame,
            primary=person,
            observation_fingerprint=observation_fingerprint,
        )

    def _skip(self, frame: InferenceFrame, *, ambiguous: bool) -> TrackedPoseFrame:
        if ambiguous:
            self._ambiguous_frames += 1
        else:
            self._missing_frames += 1
        assert self._last_primary_timestamp_ms is not None
        if frame.timestamp_ms - self._last_primary_timestamp_ms >= LOST_TIMEOUT_MS:
            raise SubjectUnstable("主训练者连续失锁达到 3000ms")
        return TrackedPoseFrame(frame=frame, primary=None, ambiguous=ambiguous)
