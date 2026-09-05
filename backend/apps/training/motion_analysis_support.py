from dataclasses import dataclass


SHOULDER_PRESS_SOURCE_KEY = "motion-resistance-shoulder-press"


@dataclass(frozen=True)
class AnalysisProfile:
    algorithm_name: str
    algorithm_version: str
    rule_version: str
    parameter_version: str
    subject_tracker_version: str


ANALYSIS_PROFILES = {
    SHOULDER_PRESS_SOURCE_KEY: AnalysisProfile(
        algorithm_name="pp-tiny-pose",
        algorithm_version="PP-TinyPose_128x96",
        rule_version="shoulder-press-v2",
        parameter_version="shoulder-press-v2-defaults",
        subject_tracker_version="primary-subject-v1",
    )
}


def get_analysis_profile(source_key: str | None) -> AnalysisProfile | None:
    return ANALYSIS_PROFILES.get(source_key)
