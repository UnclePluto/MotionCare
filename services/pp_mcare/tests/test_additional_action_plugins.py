import math

import pytest

from pp_mcare.actions.base import PoseFrame
from pp_mcare.registry import get_action_plugin


def plugin(action):
    keys = {
        "sit-stand": "motion-balance-sit-stand",
        "seated-row": "motion-resistance-row",
        "leg-kickback": "motion-resistance-leg-kickback",
    }
    result = get_action_plugin(
        keys[action],
        "PP-TinyPose_128x96",
        action + "-v1",
        action + "-v1-relaxed" + ("-stand-up" if action == "sit-stand" else ""),
    )
    assert result is not None, "每个动作必须有独立插件"
    return result


def pose(action, timestamp, left, right=None, *, aspect=1.0, score=0.95):
    """Hand-constructed sagittal geometry. Progress 0=rest, 1=full excursion."""
    if right is None:
        right = left
    points = {}
    for side, progress in [("left", left), ("right", right)]:
        hip = (0.4, 0.45)
        shoulder = (0.4, 0.2)
        knee = (0.4, 0.68)
        ankle = (0.4, 0.91)
        elbow = (0.6, 0.2)
        wrist = (0.8, 0.2)
        if action == "sit-stand":
            # Thigh rotates from horizontal sitting to vertical standing.
            radians = math.radians(progress * 90)
            knee = (hip[0] + 0.23 * math.cos(radians), hip[1] + 0.23 * math.sin(radians))
            ankle = (knee[0], knee[1] + 0.23)
        elif action == "seated-row":
            radians = math.radians(progress * 100)
            wrist = (elbow[0] + 0.2 * math.cos(radians), elbow[1] + 0.2 * math.sin(radians))
        elif action == "leg-kickback":
            radians = math.radians(progress * 30)
            knee = (hip[0] - 0.23 * math.sin(radians), hip[1] + 0.23 * math.cos(radians))
            ankle = (knee[0] - 0.23 * math.sin(radians), knee[1] + 0.23 * math.cos(radians))
        for joint, xy in [
            ("hip", hip),
            ("shoulder", shoulder),
            ("knee", knee),
            ("ankle", ankle),
            ("elbow", elbow),
            ("wrist", wrist),
        ]:
            points[f"{side}_{joint}"] = (xy[0] / aspect, xy[1], score)
    return PoseFrame(timestamp, points, coordinate_aspect_ratio=aspect)


def sequence(action, left_reps, right_reps=None, *, fps=30, aspect=1.0):
    if right_reps is None:
        right_reps = left_reps
    total = left_reps + right_reps if action == "leg-kickback" else max(left_reps, right_reps)
    for i in range((total * 3 + 1) * fps):
        seconds = i / fps
        rep = int(seconds / 3)
        phase = seconds % 3
        progress = max(0, min(1, (phase - 0.4) / 0.7, (2.6 - phase) / 0.7))
        left = progress if rep < left_reps else 0
        right = (
            progress
            if (left_reps <= rep < total if action == "leg-kickback" else rep < right_reps)
            else 0
        )
        yield pose(action, round(seconds * 1000), left, right, aspect=aspect)


@pytest.mark.parametrize(
    "action,left,right,total",
    [
        ("sit-stand", 3, 3, 3),
        ("seated-row", 3, 2, 3),
        ("leg-kickback", 3, 2, 5),
    ],
)
def test_complete_cycles_and_action_specific_aggregation(action, left, right, total):
    result = plugin(action).analyze(sequence(action, left, right))
    assert result.counts.total_count == total
    assert result.counts.standard_count + result.counts.nonstandard_count == total
    assert len(result.to_json_dict()["rep_details"]) == total


@pytest.mark.parametrize("action", ["sit-stand", "seated-row", "leg-kickback"])
@pytest.mark.parametrize("fps,aspect", [(15, 0.5625), (60, 1.777)])
def test_counts_are_frame_rate_and_aspect_ratio_independent(action, fps, aspect):
    result = plugin(action).analyze(sequence(action, 2, fps=fps, aspect=aspect))
    assert result.counts.total_count == (4 if action == "leg-kickback" else 2)


@pytest.mark.parametrize("action", ["seated-row", "leg-kickback"])
def test_static_pose_noise_and_incomplete_return_do_not_count(action):
    frames = [pose(action, i * 50, 0.03 * (i % 2)) for i in range(30)]
    frames += [pose(action, 1500 + i * 50, min(1, i / 20)) for i in range(40)]
    assert plugin(action).analyze(frames).counts.total_count == 0


def test_sit_stand_counts_on_standing_before_any_return_to_sitting():
    frames = [f for f in sequence("sit-stand", 1) if f.timestamp_ms <= 1700]
    result = plugin("sit-stand").analyze(frames).to_json_dict()
    assert result["total_count"] == 1
    assert result["rep_details"][0]["end_ms"] <= 1700


def test_sit_stand_long_standing_and_partial_dips_do_not_rearm():
    frames = [f for f in sequence("sit-stand", 1) if f.timestamp_ms <= 1700]
    frames += [pose("sit-stand", 1750 + i * 50, 0.8 if i % 20 < 10 else 1) for i in range(200)]
    assert plugin("sit-stand").analyze(frames).counts.total_count == 1


def test_sit_stand_seated_reset_allows_next_stand_without_final_return():
    frames = [f for f in sequence("sit-stand", 2) if f.timestamp_ms <= 4700]
    assert plugin("sit-stand").analyze(frames).counts.total_count == 2


def test_sit_stand_seated_noise_and_partial_rise_do_not_count():
    frames = [pose("sit-stand", i * 50, 0.03 * (i % 2)) for i in range(30)]
    frames += [pose("sit-stand", 1500 + i * 50, min(0.5, i / 40)) for i in range(60)]
    assert plugin("sit-stand").analyze(frames).counts.total_count == 0


def test_sit_stand_fast_valid_standing_is_counted_before_prompt_sitting():
    frames = []
    for timestamp in range(0, 2101, 25):
        progress = max(0, min(1, (timestamp - 500) / 400, (1450 - timestamp) / 400))
        frames.append(pose("sit-stand", timestamp, progress))
    assert plugin("sit-stand").analyze(frames).counts.total_count == 1


@pytest.mark.parametrize("action", ["sit-stand", "seated-row", "leg-kickback"])
def test_starting_mid_cycle_is_not_a_complete_repetition(action):
    frames = [pose(action, i * 50, max(0, 1 - i / 25)) for i in range(50)]
    assert plugin(action).analyze(frames).counts.total_count == 0


@pytest.mark.parametrize("action", ["sit-stand", "seated-row", "leg-kickback"])
def test_missing_joint_gap_does_not_bridge_two_halves(action):
    frames = list(sequence(action, 1))
    frames = [
        PoseFrame(f.timestamp_ms, {}) if 900 <= f.timestamp_ms % 3000 <= 2200 else f for f in frames
    ]
    assert plugin(action).analyze(frames).counts.total_count == 0


def test_forward_leg_raise_is_not_a_kickback():
    frames = [
        pose("leg-kickback", f.timestamp_ms, -0.8 * abs(math.sin(f.timestamp_ms / 700)), 0)
        for f in sequence("leg-kickback", 3)
    ]
    assert plugin("leg-kickback").analyze(frames).counts.total_count == 0


def test_sit_stand_confidence_switching_without_motion_cannot_form_a_cycle():
    frames = []
    for i in range(200):
        timestamp = i * 50
        points = dict(pose("sit-stand", timestamp, 0, 1).named_keypoints)
        right_preferred = 600 <= timestamp % 3000 <= 2000
        for name, (x, y, _) in points.items():
            preferred = name.startswith("right") == right_preferred
            points[name] = (x, y, 0.95 if preferred else 0.85)
        frames.append(PoseFrame(timestamp, points))
    assert plugin("sit-stand").analyze(frames).counts.total_count == 0


@pytest.mark.parametrize("action", ["sit-stand", "seated-row", "leg-kickback"])
def test_low_coverage_quality_matches_summary_and_both_detail_views(action):
    frames = [PoseFrame(i * 50, {}) for i in range(120)]
    frames += [PoseFrame(f.timestamp_ms + 6000, f.named_keypoints) for f in sequence(action, 1)]
    result = plugin(action).analyze(frames).to_json_dict()
    assert result["total_count"] > 0
    assert result["standard_count"] == 0
    assert not any(e["standard"] for e in result["rep_details"])
    assert not any(e["standard"] for events in result["side_rep_details"].values() for e in events)


def test_kickback_uses_ankle_when_lifted_knee_is_occluded_and_torso_leans():
    frames = []
    for f in sequence("leg-kickback", 2, 0):
        points = dict(f.named_keypoints)
        points["left_knee"] = (*points["left_knee"][:2], 0.05)
        for side in ("left", "right"):
            points[side + "_shoulder"] = (0.55, 0.2, 0.9)
        frames.append(PoseFrame(f.timestamp_ms, points))
    assert plugin("leg-kickback").analyze(frames).counts.total_count == 2


def test_row_counts_reach_and_return_even_when_elbow_bend_is_small():
    frames = []
    for f in sequence("seated-row", 2):
        phase = (f.timestamp_ms / 1000) % 3
        progress = max(0, min(1, (phase - 0.4) / 0.7, (2.6 - phase) / 0.7))
        radians = progress * math.pi / 2
        points = dict(f.named_keypoints)
        for side in ("left", "right"):
            points[f"{side}_elbow"] = (
                0.4 + 0.2 * math.cos(radians),
                0.2 + 0.2 * math.sin(radians),
                0.9,
            )
            points[f"{side}_wrist"] = (
                0.4 + 0.4 * math.cos(radians),
                0.2 + 0.4 * math.sin(radians),
                0.9,
            )
        frames.append(PoseFrame(f.timestamp_ms, points))
    result = plugin("seated-row").analyze(frames)
    assert result.counts.total_count == 2
    assert result.counts.standard_count == 0


def test_row_watch_adjustment_before_first_extension_is_not_a_rep():
    frames = []
    for i in range(60):
        # Hands in front while adjusting a watch, then lowered: no extended start.
        progress = 0.45 if i < 20 else min(1, 0.45 + (i - 20) / 20)
        frames.append(pose("seated-row", i * 50, progress))
    frames += [
        PoseFrame(f.timestamp_ms + 3000, f.named_keypoints) for f in sequence("seated-row", 1)
    ]
    assert plugin("seated-row").analyze(frames).counts.total_count == 1


def test_sit_stand_retains_observed_standing_phase_across_brief_occlusion():
    frames = []
    # Sitting, then visibly standing, a 900ms occlusion, visibly standing, sitting.
    for i in range(100):
        t = i * 50
        progress = 0 if t < 800 or t >= 3500 else 1
        frames.append(PoseFrame(t, {}) if 2000 <= t < 2900 else pose("sit-stand", t, progress))
    assert plugin("sit-stand").analyze(frames).counts.total_count == 1


def test_cycle_can_require_stable_return_to_avoid_split_kick_on_pose_jitter():
    from pp_mcare.actions.cycles import CycleCounter

    c = CycleCounter(
        rest=0.18,
        active=0.3,
        prominence=0.2,
        standard_peak=0.45,
        active_dwell_ms=50,
        return_dwell_ms=250,
        minimum_duration_ms=350,
        minimum_interval_ms=1000,
    )
    for t in range(0, 2500, 50):
        value = 0.5 if 500 <= t < 850 or 950 <= t < 1300 else 0
        c.observe(t, value)
    assert len(c.events) == 1


@pytest.mark.parametrize("action", ["sit-stand", "seated-row", "leg-kickback"])
def test_empty_or_unobservable_video_cannot_be_reported_as_confident_zero(action):
    from pp_mcare.actions.base import ActionAnalysisError

    with pytest.raises(ActionAnalysisError):
        plugin(action).analyze([PoseFrame(0, {}), PoseFrame(100, {})])


@pytest.mark.parametrize("action", ["sit-stand", "seated-row", "leg-kickback"])
def test_out_of_order_timestamps_are_rejected(action):
    with pytest.raises(ValueError):
        plugin(action).analyze([pose(action, 100, 0), pose(action, 50, 0)])
