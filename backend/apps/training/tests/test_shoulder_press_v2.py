import math
import tracemalloc

import pytest

from apps.training import shoulder_press_v2
from apps.training.pose_inference import MotionAnalysisInferenceError
from apps.training.shoulder_press_v2 import (
    SideEventDetector,
    SideMeasurement,
    _below_threshold,
    analyze_shoulder_press_keypoints_v2,
)


def _frame(
    timestamp_ms,
    left_lift,
    right_lift,
    *,
    left_score=0.95,
    right_score=0.95,
    source_fps=30.0,
):
    keypoints = {}
    for side, shoulder_x, wrist_x, lift, score in (
        ("left", 0.4, 0.3, left_lift, left_score),
        ("right", 0.6, 0.7, right_lift, right_score),
    ):
        shoulder_y = 0.5
        wrist_y = shoulder_y - lift * 0.3
        keypoints[f"{side}_shoulder"] = {
            "x": shoulder_x,
            "y": shoulder_y,
            "score": score,
        }
        keypoints[f"{side}_hip"] = {"x": shoulder_x, "y": 0.8, "score": score}
        keypoints[f"{side}_wrist"] = {"x": wrist_x, "y": wrist_y, "score": score}
        keypoints[f"{side}_elbow"] = {
            "x": (shoulder_x + wrist_x) / 2,
            "y": (shoulder_y + wrist_y) / 2,
            "score": score,
        }
    return {"timestamp_ms": timestamp_ms, "source_fps": source_fps, "keypoints": keypoints}


def _triangle_sequence(*, fps, repetitions, period_seconds=3.0):
    frame_count = math.floor(fps * repetitions * period_seconds) + 1
    for index in range(frame_count):
        timestamp_ms = round(index * 1000 / fps)
        phase = (timestamp_ms / 1000 % period_seconds) / period_seconds
        lift = 1.6 * phase if phase <= 0.5 else 1.6 * (1 - phase)
        yield _frame(timestamp_ms, lift, lift, source_fps=fps)


@pytest.mark.parametrize("fps", [5.0, 10.0, 30.0, 60.0])
def test_counts_same_complete_cycles_at_different_frame_rates(fps):
    result = analyze_shoulder_press_keypoints_v2(
        _triangle_sequence(fps=fps, repetitions=3)
    )

    assert result["total_count"] == 3
    assert result["left_event_count"] == 3
    assert result["right_event_count"] == 3
    assert result["bilateral_event_count"] == 3


def test_does_not_count_leading_or_trailing_half_cycle():
    frames = (
        _frame(timestamp_ms, lift, lift)
        for timestamp_ms, lift in [
            (0, 0.8),
            (300, 0.4),
            (600, 0.0),
            (900, 0.4),
            (1200, 0.8),
        ]
    )

    result = analyze_shoulder_press_keypoints_v2(frames)

    assert result["total_count"] == 0


def test_high_fps_single_frame_drop_does_not_confirm_fall():
    frames = (
        _frame(timestamp_ms, lift, lift)
        for timestamp_ms, lift in [
            (0, 0.0),
            (50, 0.2),
            (100, 0.8),
            (150, 0.8),
            (200, 0.8),
            (250, 0.0),
        ]
    )

    result = analyze_shoulder_press_keypoints_v2(frames)

    assert result["total_count"] == 0


def test_low_amplitude_complete_cycle_counts_as_nonstandard():
    frames = (
        _frame(timestamp_ms, lift, lift)
        for timestamp_ms, lift in [(0, 0.0), (400, 0.18), (800, 0.0)]
    )
    result = analyze_shoulder_press_keypoints_v2(frames)
    assert result["total_count"] == 1
    assert result["nonstandard_count"] == 1
    assert "range_too_small" in result["rep_details"][0]["flags"]


@pytest.mark.parametrize(
    ("peak_lift", "expected_count"),
    [
        pytest.param(0.15, 1, id="equal-threshold"),
        pytest.param(0.15 - 1e-10, 0, id="below-threshold-by-1e-10"),
        pytest.param(0.149, 0, id="below-threshold"),
    ],
)
def test_event_prominence_threshold_boundary(peak_lift, expected_count):
    frames = (
        _frame(timestamp_ms, lift, lift)
        for timestamp_ms, lift in [(0, 0.0), (400, peak_lift), (800, 0.0)]
    )

    result = analyze_shoulder_press_keypoints_v2(frames)

    assert result["total_count"] == expected_count


def test_rise_hysteresis_rejects_below_threshold_and_accepts_exact_boundary():
    detector = SideEventDetector("left")
    detector.observe(
        SideMeasurement("left", 0, 0.0, 180.0, 0.95),
        opposite_valid=True,
    )

    event = detector.observe(
        SideMeasurement("left", 400, 0.08 - 1e-10, 180.0, 0.95),
        opposite_valid=True,
    )

    assert event is None
    assert detector.phase == "seeking"

    exact_threshold_event = detector.observe(
        SideMeasurement("left", 800, 0.08, 180.0, 0.95),
        opposite_valid=True,
    )

    assert exact_threshold_event is None
    assert detector.phase == "rising"


def test_fall_hysteresis_rejects_value_below_threshold_then_accepts_exact_boundary():
    detector = SideEventDetector("left")
    detector.observe(
        SideMeasurement("left", 0, 0.0, 180.0, 0.95),
        opposite_valid=True,
    )
    detector.observe(
        SideMeasurement("left", 400, 0.2, 180.0, 0.95),
        opposite_valid=True,
    )

    below_threshold_event = detector.observe(
        SideMeasurement("left", 800, 0.2 - (0.08 - 1e-10), 180.0, 0.95),
        opposite_valid=True,
    )
    exact_threshold_event = detector.observe(
        SideMeasurement("left", 1200, 0.12, 180.0, 0.95),
        opposite_valid=True,
    )

    assert below_threshold_event is None
    assert exact_threshold_event is not None


@pytest.mark.parametrize(
    ("peak_difference_ms", "expected_total", "expected_bilateral"),
    [
        pytest.param(400, 1, 1, id="equal-threshold"),
        pytest.param(401, 2, 0, id="above-threshold"),
    ],
)
def test_bilateral_match_threshold_boundary(
    peak_difference_ms, expected_total, expected_bilateral
):
    right_peak_ms = 400 + peak_difference_ms
    frames = [
        _frame(0, 0.0, 0.0),
        _frame(400, 0.8, 0.0),
        _frame(right_peak_ms, 0.0, 0.8),
        _frame(right_peak_ms + 400, 0.0, 0.0),
    ]

    result = analyze_shoulder_press_keypoints_v2(iter(frames))

    assert result["total_count"] == expected_total
    assert result["bilateral_event_count"] == expected_bilateral


@pytest.mark.parametrize(
    ("duration_ms", "expected_tempo_flag"),
    [
        pytest.param(799, True, id="below-minimum"),
        pytest.param(800, False, id="equal-minimum"),
        pytest.param(8_000, False, id="equal-maximum"),
        pytest.param(8_001, True, id="above-maximum"),
    ],
)
def test_tempo_threshold_boundaries(duration_ms, expected_tempo_flag):
    frames = [
        _frame(0, 0.0, 0.0),
        _frame(duration_ms // 2, 0.8, 0.8),
        _frame(duration_ms, 0.0, 0.0),
    ]

    result = analyze_shoulder_press_keypoints_v2(iter(frames))

    assert ("tempo_abnormal" in result["rep_details"][0]["flags"]) is (
        expected_tempo_flag
    )


def test_short_missing_gap_keeps_candidate_but_long_gap_resets_it():
    short_gap = [
        _frame(0, 0.0, 0.0),
        _frame(400, 0.8, 0.8),
        {"timestamp_ms": 500, "source_fps": 10.0, "keypoints": {}},
        _frame(650, 0.6, 0.6),
        _frame(900, 0.0, 0.0),
    ]
    long_gap = [
        *short_gap[:3],
        {"timestamp_ms": 850, "source_fps": 10.0, "keypoints": {}},
        _frame(1000, 0.0, 0.0),
    ]

    assert analyze_shoulder_press_keypoints_v2(iter(short_gap))["total_count"] == 1
    assert analyze_shoulder_press_keypoints_v2(iter(long_gap))["total_count"] == 0


def test_first_measurement_after_long_missing_gap_starts_a_new_candidate():
    frames = [
        _frame(0, 0.0, 0.0),
        _frame(400, 0.8, 0.8),
        {"timestamp_ms": 500, "source_fps": 10.0, "keypoints": {}},
        _frame(1000, 0.0, 0.0),
    ]

    result = analyze_shoulder_press_keypoints_v2(iter(frames))

    assert result["total_count"] == 0


def test_merges_synchronized_sides_and_marks_visible_unmatched_side():
    matched = [
        _frame(0, 0.0, 0.0),
        _frame(400, 0.8, 0.7),
        _frame(800, 0.0, 0.0),
    ]
    unmatched = [
        _frame(0, 0.0, 0.0),
        _frame(400, 0.8, 0.0),
        _frame(800, 0.0, 0.0),
    ]

    matched_result = analyze_shoulder_press_keypoints_v2(iter(matched))
    unmatched_result = analyze_shoulder_press_keypoints_v2(iter(unmatched))

    assert matched_result["total_count"] == 1
    assert matched_result["rep_details"][0]["source_sides"] == ["left", "right"]
    assert unmatched_result["total_count"] == 1
    assert "bilateral_mismatch" in unmatched_result["rep_details"][0]["flags"]


def test_quality_failures_do_not_remove_completed_repetition():
    bent_peak = _frame(400, 0.8, 0.8)
    bent_peak["keypoints"]["left_elbow"].update(x=0.25, y=0.4)
    bent_peak["keypoints"]["right_elbow"].update(x=0.75, y=0.4)
    bent = [_frame(0, 0.0, 0.0), bent_peak, _frame(800, 0.0, 0.0)]
    fast = [
        _frame(0, 0.0, 0.0),
        _frame(50, 0.2, 0.2),
        _frame(100, 0.8, 0.8),
        _frame(150, 0.8, 0.8),
        _frame(200, 0.8, 0.8),
        _frame(250, 0.4, 0.4),
        _frame(300, 0.0, 0.0),
        _frame(350, 0.0, 0.0),
    ]
    unreliable = [
        _frame(0, 0.0, 0.0),
        _frame(200, 0.4, 0.4, left_score=0.3, right_score=0.3),
        _frame(400, 0.8, 0.8),
        _frame(600, 0.4, 0.4, left_score=0.3, right_score=0.3),
        _frame(800, 0.0, 0.0),
    ]

    cases = [
        (bent, "elbow_not_extended"),
        (fast, "tempo_abnormal"),
        (unreliable, "low_confidence"),
    ]
    for frames, expected_flag in cases:
        result = analyze_shoulder_press_keypoints_v2(iter(frames))
        assert result["total_count"] == 1
        assert result["nonstandard_count"] == 1
        assert expected_flag in result["rep_details"][0]["flags"]


def test_quality_flags_keep_fixed_order_and_counts_keep_invariant():
    samples = [
        (0, 0.0, 0.95),
        (50, 0.05, 0.3),
        (100, 0.18, 0.3),
        (150, 0.18, 0.95),
        (200, 0.18, 0.95),
        (250, 0.05, 0.3),
        (300, 0.0, 0.95),
        (350, 0.0, 0.95),
    ]
    frames = []
    for timestamp_ms, left_lift, left_score in samples:
        frame = _frame(
            timestamp_ms,
            left_lift,
            0.0,
            left_score=left_score,
        )
        if left_lift:
            frame["keypoints"]["left_elbow"].update(x=0.25, y=0.4)
        frames.append(frame)

    result = analyze_shoulder_press_keypoints_v2(iter(frames))

    assert result["rep_details"][0]["flags"] == [
        "range_too_small",
        "elbow_not_extended",
        "tempo_abnormal",
        "low_confidence",
        "bilateral_mismatch",
    ]
    assert result["total_count"] == 1
    assert result["standard_count"] == 0
    assert result["nonstandard_count"] == 1
    assert result["total_count"] == (
        result["standard_count"] + result["nonstandard_count"]
    )


@pytest.mark.parametrize(
    ("invalid_score", "remove_score"),
    [
        pytest.param(None, True, id="missing"),
        pytest.param("not-a-number", False, id="non-numeric"),
        pytest.param(math.nan, False, id="nan"),
        pytest.param(math.inf, False, id="infinity"),
    ],
)
def test_invalid_scores_remain_measurable_but_are_unreliable(
    invalid_score, remove_score
):
    peak = _frame(400, 0.8, 0.8)
    for point in peak["keypoints"].values():
        if remove_score:
            point.pop("score")
        else:
            point["score"] = invalid_score
    frames = [_frame(0, 0.0, 0.0), peak, _frame(800, 0.0, 0.0)]

    result = analyze_shoulder_press_keypoints_v2(iter(frames))

    assert result["total_count"] == 1
    assert result["keypoint_coverage_ratio"] == pytest.approx(2 / 3)
    assert "low_confidence" in result["rep_details"][0]["flags"]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_values_never_meet_a_minimum_threshold(value):
    assert _below_threshold(value, 0.08) is True


def test_extreme_finite_coordinates_cannot_create_nonfinite_measurement_event():
    overflow_peak = _frame(400, 0.8, 0.8)
    for side in ("left", "right"):
        shoulder_x = overflow_peak["keypoints"][f"{side}_shoulder"]["x"]
        overflow_peak["keypoints"][f"{side}_shoulder"].update(
            x=shoulder_x, y=1e308
        )
        overflow_peak["keypoints"][f"{side}_hip"].update(x=shoulder_x, y=0.0)
        overflow_peak["keypoints"][f"{side}_elbow"].update(x=shoulder_x, y=0.0)
        overflow_peak["keypoints"][f"{side}_wrist"].update(
            x=shoulder_x, y=-1e308
        )
    frames = [_frame(0, 0.0, 0.0), overflow_peak, _frame(800, 0.0, 0.0)]

    result = analyze_shoulder_press_keypoints_v2(iter(frames))

    assert result["total_count"] == 0
    assert result["keypoint_coverage_ratio"] == pytest.approx(2 / 3)


class OneShotFrames:
    def __init__(self, frames):
        self.frames = frames
        self.iterated = False

    def __iter__(self):
        if self.iterated:
            raise AssertionError("关键点流被重复迭代")
        self.iterated = True
        return iter(self.frames)


def test_consumes_input_once_and_reports_confidence_metrics():
    source = OneShotFrames(list(_triangle_sequence(fps=10.0, repetitions=2)))
    result = analyze_shoulder_press_keypoints_v2(source)
    assert source.iterated is True
    assert result["total_count"] == 2
    assert result["keypoint_coverage_ratio"] == 1.0
    assert result["bilateral_agreement_ratio"] == 1.0
    assert result["confidence_level"] == "high"


def test_reports_analysis_wall_clock_elapsed_time(monkeypatch):
    clock = iter([10.0, 10.25])
    monkeypatch.setattr(
        shoulder_press_v2, "_monotonic", lambda: next(clock), raising=False
    )

    result = analyze_shoulder_press_keypoints_v2(
        iter([_frame(0, 0.0, 0.0), _frame(800, 0.0, 0.0)])
    )

    assert result["analysis_elapsed_ms"] == 250


def test_stationary_sixty_minute_stream_has_bounded_python_memory():
    def frames():
        for index in range(108_000):
            yield _frame(round(index * 1000 / 30), 0.0, 0.0)

    tracemalloc.start()
    result = analyze_shoulder_press_keypoints_v2(frames())
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert result["processed_frames"] == 108_000
    assert result["total_count"] == 0
    assert peak_bytes < 8 * 1024 * 1024


def test_rejects_stream_without_any_measurable_person():
    frames = ({"timestamp_ms": index * 100, "keypoints": {}} for index in range(5))
    with pytest.raises(MotionAnalysisInferenceError, match="没有可用的人体关键点"):
        analyze_shoulder_press_keypoints_v2(frames)


def test_rejects_decreasing_timestamps():
    frames = [_frame(100, 0.0, 0.0), _frame(50, 0.4, 0.4)]
    with pytest.raises(ValueError, match="时间戳"):
        analyze_shoulder_press_keypoints_v2(iter(frames))
