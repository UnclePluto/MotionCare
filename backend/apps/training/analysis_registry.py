from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .pose_inference import PP_TINYPOSE_MODEL_NAME
from .shoulder_press_v2 import (
    SHOULDER_PRESS_RULE_VERSION,
    analyze_shoulder_press_keypoints_v2,
)


@dataclass(frozen=True)
class MotionAnalyzer:
    source_key: str
    algorithm_version: str
    rule_version: str
    analyze_keypoints: Callable[[Iterable[dict]], dict]


MOTION_ANALYZERS = {
    "motion-resistance-shoulder-press": MotionAnalyzer(
        source_key="motion-resistance-shoulder-press",
        algorithm_version=PP_TINYPOSE_MODEL_NAME,
        rule_version=SHOULDER_PRESS_RULE_VERSION,
        analyze_keypoints=analyze_shoulder_press_keypoints_v2,
    )
}


def get_motion_analyzer(source_key: str | None) -> MotionAnalyzer | None:
    return MOTION_ANALYZERS.get(source_key)


def analysis_available(source_key: str | None) -> bool:
    return get_motion_analyzer(source_key) is not None
