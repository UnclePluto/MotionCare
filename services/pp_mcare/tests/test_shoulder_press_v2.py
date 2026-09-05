import math
import tracemalloc

import pytest

from motion_analysis_contract import ContractValidationError, MotionCounts
from pp_mcare.actions import shoulder_press_v2
from pp_mcare.actions.base import (
    ActionAnalysisError,
    ActionPlugin,
    AnalysisResult,
    PoseFrame,
)
from pp_mcare.actions.shoulder_press_v2 import (
    ShoulderPressV2Plugin,
    SideEvent,
    SideEventDetector,
    SideMeasurement,
    _below_threshold,
    _merge_events,
    analyze_shoulder_press_keypoints_v2,
)


def _pose_frame(frame):
    return PoseFrame(
        timestamp_ms=frame["timestamp_ms"],
        named_keypoints={
            name: (point["x"], point["y"], point.get("score", 0.0))
            for name, point in frame["keypoints"].items()
        },
    )


def test_pose_frame_copies_and_deeply_freezes_keypoints():
    keypoints = {"left_wrist": [0.25, 0.5, 0.95]}
    frame = PoseFrame(timestamp_ms=100, named_keypoints=keypoints)

    keypoints["left_wrist"][0] = 99.0
    keypoints["right_wrist"] = [0.75, 0.5, 0.95]

    assert frame.named_keypoints == {"left_wrist": (0.25, 0.5, 0.95)}
    with pytest.raises(TypeError):
        frame.named_keypoints["left_wrist"] = (1.0, 2.0, 3.0)


def test_analysis_result_copies_and_deeply_freezes_payload():
    payload = {
        "total_count": 1,
        "standard_count": 1,
        "nonstandard_count": 0,
        "quality_flags": ["camera_angle_unverified"],
        "details": {"score": 1},
    }
    result = AnalysisResult(
        counts=MotionCounts(total_count=1, standard_count=1, nonstandard_count=0),
        payload=payload,
    )

    payload["quality_flags"].append("mutated")
    payload["details"]["score"] = 0

    assert result.payload["quality_flags"] == ("camera_angle_unverified",)
    assert result.payload["details"]["score"] == 1
    with pytest.raises(TypeError):
        result.payload["details"]["score"] = 0


def test_analysis_result_rejects_payload_counts_that_disagree_with_shared_counts():
    with pytest.raises(ContractValidationError, match="counts 与 payload"):
        AnalysisResult(
            counts=MotionCounts(total_count=1, standard_count=1, nonstandard_count=0),
            payload={"total_count": 2, "standard_count": 1, "nonstandard_count": 1},
        )


def test_plugin_implements_contract_and_returns_validated_shared_counts():
    plugin = ShoulderPressV2Plugin()
    frames = (
        _pose_frame(_frame(timestamp_ms, lift, lift))
        for timestamp_ms, lift in [(0, 0.0), (400, 0.8), (800, 0.0)]
    )

    result = plugin.analyze(frames)

    assert isinstance(plugin, ActionPlugin)
    assert result.counts == MotionCounts(total_count=1, standard_count=1, nonstandard_count=0)
    assert result.payload["total_count"] == 1
    assert result.counts.total_count == (
        result.counts.standard_count + result.counts.nonstandard_count
    )


def test_plugin_preserves_ninety_repetition_regression_semantics():
    frames = (_pose_frame(frame) for frame in _triangle_sequence(fps=10.0, repetitions=90))

    result = ShoulderPressV2Plugin().analyze(frames)

    assert result.counts.total_count == 90
    assert result.payload["left_event_count"] == 90
    assert result.payload["right_event_count"] == 90


def test_plugin_processes_each_frame_before_requesting_the_next_one():
    class GuardedFrame:
        def __init__(self, frame):
            self._frame = frame
            self.consumed = False

        @property
        def timestamp_ms(self):
            return self._frame["timestamp_ms"]

        @property
        def named_keypoints(self):
            self.consumed = True
            return {
                name: (point["x"], point["y"], point.get("score", 0.0))
                for name, point in self._frame["keypoints"].items()
            }

    class StreamingGuard:
        def __iter__(self):
            previous = None
            for raw_frame in (_frame(0, 0.0, 0.0), _frame(800, 0.0, 0.0)):
                if previous is not None:
                    assert previous.consumed, "插件在消费当前帧前就请求了下一帧"
                previous = GuardedFrame(raw_frame)
                yield previous
            assert previous is not None and previous.consumed

    result = ShoulderPressV2Plugin().analyze(StreamingGuard())

    assert result.counts.total_count == 0


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


def _side_event(
    side,
    *,
    start_ms,
    peak_ms,
    end_ms,
    prominence=0.8,
    peak_wrist_lift=0.8,
    peak_elbow_angle=180.0,
    coverage_ratio=1.0,
    opposite_coverage_ratio=1.0,
):
    return SideEvent(
        side=side,
        start_ms=start_ms,
        peak_ms=peak_ms,
        end_ms=end_ms,
        prominence=prominence,
        peak_wrist_lift=peak_wrist_lift,
        peak_elbow_angle=peak_elbow_angle,
        coverage_ratio=coverage_ratio,
        opposite_coverage_ratio=opposite_coverage_ratio,
    )


def test_overlapping_events_with_600ms_peak_offset_form_two_bilateral_reps():
    left_events = [
        _side_event("left", start_ms=0, peak_ms=1_000, end_ms=2_000),
        _side_event("left", start_ms=3_000, peak_ms=4_000, end_ms=5_000),
    ]
    right_events = [
        _side_event("right", start_ms=0, peak_ms=1_600, end_ms=2_000),
        _side_event("right", start_ms=3_000, peak_ms=4_600, end_ms=5_000),
    ]

    details, bilateral_count = _merge_events(left_events, right_events)

    assert len(details) == 2
    assert bilateral_count == 2
    assert [detail["source_sides"] for detail in details] == [
        ["left", "right"],
        ["left", "right"],
    ]


def test_matched_events_keep_nonoverlapping_anchor_timeline():
    left_events = [
        _side_event("left", start_ms=0, peak_ms=1_000, end_ms=2_000),
        _side_event("left", start_ms=2_200, peak_ms=3_000, end_ms=4_000),
    ]
    right_events = [
        _side_event("right", start_ms=400, peak_ms=1_600, end_ms=2_600),
        _side_event("right", start_ms=2_600, peak_ms=3_600, end_ms=4_600),
    ]

    details, bilateral_count = _merge_events(left_events, right_events)

    assert bilateral_count == 2
    assert [
        (
            detail["start_ms"],
            detail["peak_ms"],
            detail["end_ms"],
            detail["duration_ms"],
        )
        for detail in details
    ] == [(0, 1_000, 2_000, 2_000), (2_200, 3_000, 4_000, 1_800)]
    assert details[0]["end_ms"] < details[1]["start_ms"]
    assert [detail["source_sides"] for detail in details] == [
        ["left", "right"],
        ["left", "right"],
    ]


@pytest.mark.parametrize(
    ("matched_coverage", "expected_flags"),
    [
        pytest.param(0.79, ["low_confidence"], id="unreliable-bad-side"),
        pytest.param(
            0.9,
            ["range_too_small", "elbow_not_extended"],
            id="reliable-bad-side",
        ),
        pytest.param(
            0.8,
            ["range_too_small", "elbow_not_extended"],
            id="exact-reliability-boundary",
        ),
    ],
)
def test_matched_side_quality_failures_require_reliable_coverage(matched_coverage, expected_flags):
    anchor = _side_event("left", start_ms=0, peak_ms=1_000, end_ms=2_000)
    matched = _side_event(
        "right",
        start_ms=0,
        peak_ms=1_000,
        end_ms=2_000,
        prominence=0.1,
        peak_wrist_lift=0.1,
        peak_elbow_angle=120.0,
        coverage_ratio=matched_coverage,
    )

    details, bilateral_count = _merge_events([anchor], [matched])

    assert bilateral_count == 1
    assert details[0]["source_sides"] == ["left", "right"]
    assert details[0]["flags"] == expected_flags


def test_more_populous_side_anchors_total_without_extra_unmatched_other_side():
    left_events = [
        _side_event("left", start_ms=0, peak_ms=1_000, end_ms=2_000),
        _side_event("left", start_ms=6_000, peak_ms=7_000, end_ms=8_000),
    ]
    right_events = [
        _side_event("right", start_ms=0, peak_ms=1_000, end_ms=2_000),
        _side_event("right", start_ms=2_000, peak_ms=3_000, end_ms=4_000),
        _side_event("right", start_ms=4_000, peak_ms=5_000, end_ms=6_000),
    ]

    details, bilateral_count = _merge_events(left_events, right_events)

    assert len(details) == 3
    assert bilateral_count == 1
    assert [detail["peak_ms"] for detail in details] == [1_000, 3_000, 5_000]


def test_equal_counts_use_side_with_higher_average_coverage_as_anchor():
    left_events = [
        _side_event(
            "left",
            start_ms=0,
            peak_ms=1_000,
            end_ms=2_000,
            coverage_ratio=0.8,
            opposite_coverage_ratio=0.0,
        ),
        _side_event(
            "left",
            start_ms=2_000,
            peak_ms=3_000,
            end_ms=4_000,
            coverage_ratio=0.8,
            opposite_coverage_ratio=0.0,
        ),
    ]
    right_events = [
        _side_event(
            "right",
            start_ms=9_000,
            peak_ms=10_000,
            end_ms=11_000,
            coverage_ratio=0.9,
            opposite_coverage_ratio=0.0,
        ),
        _side_event(
            "right",
            start_ms=11_000,
            peak_ms=12_000,
            end_ms=13_000,
            coverage_ratio=0.9,
            opposite_coverage_ratio=0.0,
        ),
    ]

    details, bilateral_count = _merge_events(left_events, right_events)

    assert bilateral_count == 0
    assert [detail["peak_ms"] for detail in details] == [10_000, 12_000]


def test_equal_counts_and_coverage_choose_left_as_deterministic_anchor():
    left_events = [
        _side_event(
            "left",
            start_ms=0,
            peak_ms=1_000,
            end_ms=2_000,
            opposite_coverage_ratio=0.0,
        )
    ]
    right_events = [
        _side_event(
            "right",
            start_ms=9_000,
            peak_ms=10_000,
            end_ms=11_000,
            opposite_coverage_ratio=0.0,
        )
    ]

    details, bilateral_count = _merge_events(left_events, right_events)

    assert bilateral_count == 0
    assert len(details) == 1
    assert details[0]["peak_ms"] == 1_000
    assert details[0]["source_sides"] == ["left"]


@pytest.mark.parametrize(
    (
        "right_start_ms",
        "right_peak_ms",
        "right_end_ms",
        "expected_bilateral_count",
    ),
    [
        pytest.param(1_000, 1_800, 3_000, 1, id="800ms-and-exactly-half-overlap"),
        pytest.param(0, 1_801, 2_000, 0, id="801ms-despite-full-overlap"),
        pytest.param(1_001, 1_800, 3_001, 0, id="just-below-half-overlap"),
    ],
)
def test_extended_bilateral_match_boundaries(
    right_start_ms,
    right_peak_ms,
    right_end_ms,
    expected_bilateral_count,
):
    left_events = [_side_event("left", start_ms=0, peak_ms=1_000, end_ms=2_000)]
    right_events = [
        _side_event(
            "right",
            start_ms=right_start_ms,
            peak_ms=right_peak_ms,
            end_ms=right_end_ms,
        )
    ]

    details, bilateral_count = _merge_events(left_events, right_events)

    assert len(details) == 1
    assert bilateral_count == expected_bilateral_count
    assert (details[0]["source_sides"] == ["left", "right"]) is (expected_bilateral_count == 1)


@pytest.mark.parametrize(
    ("right_start_ms", "right_end_ms"),
    [
        pytest.param(1_600, 1_600, id="zero-duration"),
        pytest.param(1_700, 1_500, id="negative-duration"),
    ],
)
def test_extended_match_rejects_nonpositive_event_duration(right_start_ms, right_end_ms):
    left_events = [_side_event("left", start_ms=0, peak_ms=1_000, end_ms=2_000)]
    right_events = [
        _side_event(
            "right",
            start_ms=right_start_ms,
            peak_ms=1_600,
            end_ms=right_end_ms,
        )
    ]

    details, bilateral_count = _merge_events(left_events, right_events)

    assert len(details) == 1
    assert bilateral_count == 0
    assert details[0]["source_sides"] == ["left"]


def test_direct_400ms_match_still_accepts_zero_duration_event():
    left_events = [_side_event("left", start_ms=0, peak_ms=1_000, end_ms=2_000)]
    right_events = [_side_event("right", start_ms=1_400, peak_ms=1_400, end_ms=1_400)]

    details, bilateral_count = _merge_events(left_events, right_events)

    assert len(details) == 1
    assert bilateral_count == 1
    assert details[0]["source_sides"] == ["left", "right"]


def test_analysis_total_uses_larger_side_count_and_keeps_count_invariants():
    frames = [
        _frame(0, 0.0, 0.0),
        _frame(400, 0.8, 0.8),
        _frame(800, 0.0, 0.0),
        _frame(1_200, 0.0, 0.0),
        _frame(1_600, 0.0, 0.8),
        _frame(2_000, 0.0, 0.0),
        _frame(2_400, 0.0, 0.0),
        _frame(2_800, 0.0, 0.8),
        _frame(3_200, 0.0, 0.0),
        _frame(4_400, 0.0, 0.0),
        _frame(4_800, 0.8, 0.0),
        _frame(5_200, 0.0, 0.0),
    ]

    result = analyze_shoulder_press_keypoints_v2(iter(frames))

    assert result["left_event_count"] == 2
    assert result["right_event_count"] == 3
    assert result["total_count"] == 3
    assert len(result["rep_details"]) == 3
    assert result["bilateral_event_count"] == 1
    assert result["bilateral_event_count"] <= min(
        result["left_event_count"], result["right_event_count"]
    )
    assert result["bilateral_agreement_ratio"] == pytest.approx(1 / 3)
    assert result["standard_count"] + result["nonstandard_count"] == 3


@pytest.mark.parametrize("fps", [5.0, 10.0, 30.0, 60.0])
def test_counts_same_complete_cycles_at_different_frame_rates(fps):
    result = analyze_shoulder_press_keypoints_v2(_triangle_sequence(fps=fps, repetitions=3))

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
        pytest.param(401, 1, 1, id="above-primary-window-with-overlap"),
    ],
)
def test_bilateral_match_threshold_boundary(peak_difference_ms, expected_total, expected_bilateral):
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

    assert ("tempo_abnormal" in result["rep_details"][0]["flags"]) is (expected_tempo_flag)


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
        "tempo_abnormal",
        "low_confidence",
        "bilateral_mismatch",
    ]
    assert result["total_count"] == 1
    assert result["standard_count"] == 0
    assert result["nonstandard_count"] == 1
    assert result["total_count"] == (result["standard_count"] + result["nonstandard_count"])


@pytest.mark.parametrize(
    ("invalid_score", "remove_score"),
    [
        pytest.param(None, True, id="missing"),
        pytest.param("not-a-number", False, id="non-numeric"),
        pytest.param(math.nan, False, id="nan"),
        pytest.param(math.inf, False, id="infinity"),
    ],
)
def test_invalid_scores_remain_measurable_but_are_unreliable(invalid_score, remove_score):
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
        overflow_peak["keypoints"][f"{side}_shoulder"].update(x=shoulder_x, y=1e308)
        overflow_peak["keypoints"][f"{side}_hip"].update(x=shoulder_x, y=0.0)
        overflow_peak["keypoints"][f"{side}_elbow"].update(x=shoulder_x, y=0.0)
        overflow_peak["keypoints"][f"{side}_wrist"].update(x=shoulder_x, y=-1e308)
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
    monkeypatch.setattr(shoulder_press_v2, "_monotonic", lambda: next(clock), raising=False)

    result = analyze_shoulder_press_keypoints_v2(iter([_frame(0, 0.0, 0.0), _frame(800, 0.0, 0.0)]))

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
    with pytest.raises(ActionAnalysisError, match="没有可用的人体关键点"):
        analyze_shoulder_press_keypoints_v2(frames)


def test_rejects_decreasing_timestamps():
    frames = [_frame(100, 0.0, 0.0), _frame(50, 0.4, 0.4)]
    with pytest.raises(ValueError, match="时间戳"):
        analyze_shoulder_press_keypoints_v2(iter(frames))
