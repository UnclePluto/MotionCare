import math

from .cycles import CycleCounter, analyze_cycles, angle, point


class SeatedRowV1Plugin:
    source_key = "motion-resistance-row"
    algorithm_version = "PP-TinyPose_128x96"
    rule_version = "seated-row-v1"
    parameter_version = "seated-row-v1-relaxed"
    pose_preprocessing_version = "full-image-v1"
    preserve_missing_frames = True

    @staticmethod
    def measure(frame):
        result = {}
        for side in ("left", "right"):
            points = [point(frame, f"{side}_{joint}") for joint in ("shoulder", "elbow", "wrist")]
            result[side] = None
            if any(p is None for p in points):
                continue
            shoulder, elbow, wrist = points
            arm_length = math.dist(shoulder[:2], elbow[:2]) + math.dist(elbow[:2], wrist[:2])
            if arm_length > 1e-8:
                # Side-view reach measures attempts even when elbow flexion is small.
                result[side] = 1 - abs(wrist[0] - shoulder[0]) / arm_length
        return result

    def analyze(self, frames):
        return analyze_cycles(
            frames,
            plugin=self,
            channels=("left", "right"),
            measurement=self.measure,
            counter_factory=lambda: CycleCounter(
                rest=0.35, active=0.55, prominence=0.3, standard_peak=0.7
            ),
            aggregation="maximum",
            eligibility=self.eligibility,
        )

    @staticmethod
    def eligibility(frame):
        result = {}
        for side in ("left", "right"):
            points = [point(frame, f"{side}_{j}") for j in ("shoulder", "elbow", "wrist")]
            elbow = None if any(p is None for p in points) else angle(*points)
            result[side] = (elbow is not None and elbow >= 145, elbow is not None and elbow <= 130)
        return result
