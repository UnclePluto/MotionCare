import math
from statistics import median

from .cycles import CycleCounter, analyze_cycles, point


class LegKickbackV1Plugin:
    source_key = "motion-resistance-leg-kickback"
    algorithm_version = "PP-TinyPose_128x96"
    rule_version = "leg-kickback-v1"
    parameter_version = "leg-kickback-v1-relaxed"
    pose_preprocessing_version = "body-crop-v1"
    preserve_missing_frames = True

    @staticmethod
    def measure(frame):
        # Hands on the support in front of the hips establish sagittal direction.
        forward = []
        for side in ("left", "right"):
            shoulder = point(frame, f"{side}_shoulder")
            wrist = point(frame, f"{side}_wrist")
            hip = point(frame, f"{side}_hip")
            if shoulder is not None and wrist is not None and hip is not None:
                scale = math.hypot(shoulder[0] - hip[0], shoulder[1] - hip[1])
                if scale > 1e-8:
                    forward.append((wrist[0] - hip[0]) / scale)
        direction = median(forward) if forward else 0
        result = dict.fromkeys(("left", "right"))
        if abs(direction) < 0.1:
            return result
        facing = 1 if direction > 0 else -1
        for side, opposite in (("left", "right"), ("right", "left")):
            support = {
                j: point(frame, f"{opposite}_{j}", minimum_score=0.25)
                for j in ("hip", "knee", "ankle")
            }
            hip = point(frame, f"{side}_hip", minimum_score=0.25)
            if hip is None or any(p is None for p in support.values()):
                continue
            leg_length = math.dist(support["hip"][:2], support["knee"][:2]) + math.dist(
                support["knee"][:2], support["ankle"][:2]
            )
            if leg_length < 1e-8:
                continue
            separation, posterior = [], []
            for joint, scale in (("knee", leg_length / 2), ("ankle", leg_length)):
                target = point(frame, f"{side}_{joint}", minimum_score=0.25)
                if target is not None:
                    separation.append(facing * (support[joint][0] - target[0]) / scale)
                    posterior.append(facing * (hip[0] - target[0]) / scale)
            if separation:
                # A stationary support leg must not become a "back kick" merely
                # because the other leg moved forwards.
                result[side] = max(separation) if max(posterior) >= 0.1 else 0.0
        return result

    def analyze(self, frames):
        return analyze_cycles(
            frames,
            plugin=self,
            channels=("left", "right"),
            measurement=self.measure,
            counter_factory=lambda: CycleCounter(
                rest=0.18,
                active=0.3,
                prominence=0.2,
                standard_peak=0.45,
                minimum_duration_ms=350,
                active_dwell_ms=50,
                return_dwell_ms=250,
                minimum_interval_ms=1000,
            ),
            aggregation="sum",
        )
