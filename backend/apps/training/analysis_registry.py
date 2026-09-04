from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .analysis import analyze_shoulder_press_keypoints
from .pose_inference import PP_TINYPOSE_MODEL_NAME
from .shoulder_press_v2 import (
    SHOULDER_PRESS_RULE_VERSION,
    analyze_shoulder_press_keypoints_v2,
)


SHOULDER_PRESS_V1_RULE_VERSION = "shoulder-press-v1"


@dataclass(frozen=True)
class MotionAnalyzer:
    source_key: str
    algorithm_version: str
    rule_version: str
    analyze_keypoints: Callable[[Iterable[dict]], dict]


SHOULDER_PRESS_V1_ANALYZER = MotionAnalyzer(
    source_key="motion-resistance-shoulder-press",
    algorithm_version=PP_TINYPOSE_MODEL_NAME,
    rule_version=SHOULDER_PRESS_V1_RULE_VERSION,
    analyze_keypoints=analyze_shoulder_press_keypoints,
)
SHOULDER_PRESS_V2_ANALYZER = MotionAnalyzer(
    source_key="motion-resistance-shoulder-press",
    algorithm_version=PP_TINYPOSE_MODEL_NAME,
    rule_version=SHOULDER_PRESS_RULE_VERSION,
    analyze_keypoints=analyze_shoulder_press_keypoints_v2,
)

MOTION_ANALYZERS = {
    SHOULDER_PRESS_V2_ANALYZER.source_key: SHOULDER_PRESS_V2_ANALYZER,
}
MOTION_ANALYZERS_BY_VERSION = {
    (
        analyzer.source_key,
        analyzer.algorithm_version,
        analyzer.rule_version,
    ): analyzer
    for analyzer in (SHOULDER_PRESS_V1_ANALYZER, SHOULDER_PRESS_V2_ANALYZER)
}
# v1 任务创建时尚未固化模型版本，历史 pending 记录的该字段为空。
MOTION_ANALYZERS_BY_VERSION[
    (
        SHOULDER_PRESS_V1_ANALYZER.source_key,
        "",
        SHOULDER_PRESS_V1_ANALYZER.rule_version,
    )
] = SHOULDER_PRESS_V1_ANALYZER


def get_motion_analyzer(source_key: str | None) -> MotionAnalyzer | None:
    return MOTION_ANALYZERS.get(source_key)


def get_motion_analyzer_for_versions(
    source_key: str | None,
    algorithm_version: str,
    rule_version: str,
) -> MotionAnalyzer | None:
    return MOTION_ANALYZERS_BY_VERSION.get(
        (source_key, algorithm_version, rule_version)
    )


def analysis_available(source_key: str | None) -> bool:
    return get_motion_analyzer(source_key) is not None
