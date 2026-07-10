from apps.training.analysis import analyze_shoulder_press_keypoints


def _frame(
    timestamp_ms,
    position,
    *,
    left_score=0.95,
    right_score=0.95,
    left_position=None,
    right_position=None,
):
    positions = {
        "down": {
            "left_elbow": (0.32, 0.56),
            "left_wrist": (0.24, 0.52),
            "right_elbow": (0.68, 0.56),
            "right_wrist": (0.76, 0.52),
        },
        "partial": {
            "left_elbow": (0.36, 0.44),
            "left_wrist": (0.32, 0.39),
            "right_elbow": (0.64, 0.44),
            "right_wrist": (0.68, 0.39),
        },
        "up": {
            "left_elbow": (0.40, 0.37),
            "left_wrist": (0.40, 0.25),
            "right_elbow": (0.60, 0.37),
            "right_wrist": (0.60, 0.25),
        },
    }
    keypoints = {}
    for side, score, selected_position in (
        ("left", left_score, left_position or position),
        ("right", right_score, right_position or position),
    ):
        keypoints[f"{side}_shoulder"] = {
            "x": 0.4 if side == "left" else 0.6,
            "y": 0.5,
            "score": score,
        }
        keypoints[f"{side}_hip"] = {
            "x": 0.42 if side == "left" else 0.58,
            "y": 0.8,
            "score": score,
        }
        for joint in ("elbow", "wrist"):
            x, y = positions[selected_position][f"{side}_{joint}"]
            keypoints[f"{side}_{joint}"] = {"x": x, "y": y, "score": score}
    return {"timestamp_ms": timestamp_ms, "keypoints": keypoints}


def _sequence(samples):
    return [_frame(timestamp_ms, position, **kwargs) for timestamp_ms, position, kwargs in samples]


def test_counts_only_debounced_down_up_down_repetitions():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (250, "up", {}),  # 单帧噪声不得确认状态
            (350, "partial", {}),
            (500, "up", {}),
            (600, "up", {}),
            (850, "partial", {}),
            (1200, "down", {}),
            (1300, "down", {}),
            (1600, "partial", {}),
            (1900, "up", {}),
            (2000, "up", {}),
            (2300, "partial", {}),
            (2700, "down", {}),
            (2800, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 2
    assert result["standard_count"] == 2
    assert result["nonstandard_count"] == 0
    assert len(result["rep_details"]) == 2
    assert result["total_count"] == result["standard_count"] + result["nonstandard_count"]


def test_uses_the_more_stable_side_when_other_side_has_low_confidence():
    frames = _sequence(
        [
            (0, "down", {"left_score": 0.2, "left_position": "up"}),
            (100, "down", {"left_score": 0.2, "left_position": "partial"}),
            (500, "up", {"left_score": 0.2, "left_position": "down"}),
            (600, "up", {"left_score": 0.2, "left_position": "partial"}),
            (1200, "down", {"left_score": 0.2, "left_position": "up"}),
            (1300, "down", {"left_score": 0.2, "left_position": "partial"}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert result["standard_count"] == 1
    assert result["rep_details"][0]["side"] == "right"
    assert "low_confidence" not in result["rep_details"][0]["flags"]


def test_uses_bilateral_average_when_both_sides_are_stable():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (500, "up", {}),
            (600, "up", {}),
            (1200, "down", {}),
            (1300, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert result["rep_details"][0]["side"] == "bilateral"


def test_ignores_incomplete_leading_and_trailing_half_repetitions():
    frames = _sequence(
        [
            (0, "up", {}),
            (100, "up", {}),
            (500, "down", {}),
            (600, "down", {}),
            (1000, "up", {}),
            (1100, "up", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 0
    assert result["rep_details"] == []


def test_marks_a_low_amplitude_attempt_as_range_too_small():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (500, "partial", {}),
            (600, "partial", {}),
            (1200, "down", {}),
            (1300, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert result["standard_count"] == 0
    assert result["nonstandard_count"] == 1
    assert result["rep_details"][0]["flags"] == ["range_too_small"]


def test_marks_too_fast_repetition_as_tempo_abnormal():
    frames = _sequence(
        [
            (0, "down", {}),
            (40, "down", {}),
            (180, "up", {}),
            (220, "up", {}),
            (500, "down", {}),
            (540, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert "tempo_abnormal" in result["rep_details"][0]["flags"]


def test_marks_repetition_with_low_joint_confidence_nonstandard():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (500, "up", {"left_score": 0.2, "right_score": 0.2}),
            (600, "up", {"left_score": 0.2, "right_score": 0.2}),
            (1200, "down", {}),
            (1300, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert result["standard_count"] == 0
    assert result["nonstandard_count"] == 1
    assert "low_confidence" in result["rep_details"][0]["flags"]
    assert result["quality_flags"] == ["camera_angle_unverified"]
