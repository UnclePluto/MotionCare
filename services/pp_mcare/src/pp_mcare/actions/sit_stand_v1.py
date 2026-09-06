from .cycles import CycleCounter, analyze_cycles, angle, point


class SitStandV1Plugin:
    source_key = "motion-balance-sit-stand"
    algorithm_version = "PP-TinyPose_128x96"
    rule_version = "sit-stand-v1"
    parameter_version = "sit-stand-v1-relaxed-stand-up"
    completion_phase = "standing_reached"
    pose_preprocessing_version = "body-crop-v1"
    preserve_missing_frames = True

    @staticmethod
    def measure(frame):
        result = {}
        for side in ("left", "right"):
            points = [point(frame, f"{side}_{joint}") for joint in ("hip", "knee", "ankle")]
            result[side] = None
            if any(p is None for p in points):
                continue
            result[side] = angle(*points)
        return result

    def analyze(self, frames):
        return analyze_cycles(
            frames,
            plugin=self,
            channels=("left", "right"),
            measurement=self.measure,
            counter_factory=lambda: CycleCounter(
                rest=125,
                active=150,
                prominence=30,
                standard_peak=165,
                # Only the rising phase is timed; sitting back is a separate reset.
                minimum_duration_ms=200,
                max_missing_gap_ms=1500,
                count_on_active=True,
            ),
            aggregation="maximum",
        )
