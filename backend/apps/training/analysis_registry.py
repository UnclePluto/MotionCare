from collections.abc import Callable
from dataclasses import dataclass

from .analysis import analyze_shoulder_press_keypoints
from .pose_inference import PP_TINYPOSE_MODEL_NAME


@dataclass(frozen=True)
class MotionAnalyzer:
    source_key: str
    algorithm_version: str
    analyze_keypoints: Callable[[list], dict]


MOTION_ANALYZERS = {
    "motion-resistance-shoulder-press": MotionAnalyzer(
        source_key="motion-resistance-shoulder-press",
        algorithm_version=PP_TINYPOSE_MODEL_NAME,
        analyze_keypoints=analyze_shoulder_press_keypoints,
    )
}


def get_motion_analyzer(source_key: str | None) -> MotionAnalyzer | None:
    return MOTION_ANALYZERS.get(source_key)


def analysis_available(source_key: str | None) -> bool:
    return get_motion_analyzer(source_key) is not None
