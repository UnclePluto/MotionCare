import math
from statistics import mean, pstdev


REQUIRED_JOINTS = ("shoulder", "elbow", "wrist", "hip")
MIN_CONFIDENCE_SCORE = 0.4
MIN_STATE_CONSECUTIVE_FRAMES = 2
MIN_STATE_DURATION_MS = 120
BILATERAL_STABILITY_TOLERANCE = 0.08
UP_WRIST_LIFT_TORSO_RATIO = 0.55
UP_ELBOW_EXTENSION_DEGREES = 150.0
DOWN_WRIST_LIFT_MAX_TORSO_RATIO = 0.12
DOWN_ELBOW_FLEXION_MAX_DEGREES = 145.0
MIN_ATTEMPT_PEAK_RISE_TORSO_RATIO = 0.2
MIN_ATTEMPT_ASCENT_HYSTERESIS_TORSO_RATIO = 0.08
MIN_ATTEMPT_RETURN_HYSTERESIS_TORSO_RATIO = 0.08
MIN_REPETITION_DURATION_MS = 800
MAX_REPETITION_DURATION_MS = 8000


def _point(frame, name):
    return frame.get("keypoints", {}).get(name, {})


def _point_score(frame, side, joint):
    try:
        return float(_point(frame, f"{side}_{joint}").get("score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _side_stability(frames, side):
    scores = [
        min(_point_score(frame, side, joint) for joint in REQUIRED_JOINTS)
        for frame in frames
    ]
    if not scores:
        return 0.0
    return max(0.0, mean(scores) - pstdev(scores))


def _select_side(frames):
    left = _side_stability(frames, "left")
    right = _side_stability(frames, "right")
    if left > 0 and right > 0 and abs(left - right) <= BILATERAL_STABILITY_TOLERANCE:
        return "bilateral"
    return "left" if left >= right else "right"


def _coordinates(point):
    try:
        return float(point["x"]), float(point["y"])
    except (KeyError, TypeError, ValueError):
        return 0.0, 0.0


def _selected_point(frame, side, joint):
    if side != "bilateral":
        point = _point(frame, f"{side}_{joint}")
        x, y = _coordinates(point)
        return {"x": x, "y": y, "score": _point_score(frame, side, joint)}

    left = _point(frame, f"left_{joint}")
    right = _point(frame, f"right_{joint}")
    left_x, left_y = _coordinates(left)
    right_x, right_y = _coordinates(right)
    return {
        "x": (left_x + right_x) / 2,
        "y": (left_y + right_y) / 2,
        "score": min(
            _point_score(frame, "left", joint),
            _point_score(frame, "right", joint),
        ),
    }


def _distance(first, second):
    return math.hypot(second["x"] - first["x"], second["y"] - first["y"])


def _angle(first, vertex, third):
    first_vector = (first["x"] - vertex["x"], first["y"] - vertex["y"])
    third_vector = (third["x"] - vertex["x"], third["y"] - vertex["y"])
    denominator = math.hypot(*first_vector) * math.hypot(*third_vector)
    if denominator == 0:
        return 0.0
    cosine = sum(a * b for a, b in zip(first_vector, third_vector, strict=True)) / denominator
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _measurement(frame, side):
    points = {joint: _selected_point(frame, side, joint) for joint in REQUIRED_JOINTS}
    torso_length = _distance(points["shoulder"], points["hip"])
    wrist_lift = (
        (points["shoulder"]["y"] - points["wrist"]["y"]) / torso_length
        if torso_length > 0
        else 0.0
    )
    elbow_angle = _angle(points["shoulder"], points["elbow"], points["wrist"])
    if (
        wrist_lift >= UP_WRIST_LIFT_TORSO_RATIO
        and elbow_angle >= UP_ELBOW_EXTENSION_DEGREES
    ):
        state = "up"
    elif (
        wrist_lift <= DOWN_WRIST_LIFT_MAX_TORSO_RATIO
        and elbow_angle <= DOWN_ELBOW_FLEXION_MAX_DEGREES
    ):
        state = "down"
    else:
        state = "transition"
    return {
        "timestamp_ms": int(frame.get("timestamp_ms", 0)),
        "state": state,
        "score": min(point["score"] for point in points.values()),
        "wrist_lift": wrist_lift,
    }


def _is_confirmed(run):
    if not run:
        return False
    duration = run[-1]["timestamp_ms"] - run[0]["timestamp_ms"]
    return len(run) >= MIN_STATE_CONSECUTIVE_FRAMES or duration >= MIN_STATE_DURATION_MS


def _is_attempt(measurements, *, down_baseline):
    if len(measurements) < 3:
        return False

    wrist_lifts = [item["wrist_lift"] for item in measurements]
    peak_index = max(range(len(wrist_lifts)), key=wrist_lifts.__getitem__)
    if peak_index == 0 or peak_index == len(wrist_lifts) - 1:
        return False

    peak = wrist_lifts[peak_index]
    return (
        peak - down_baseline >= MIN_ATTEMPT_PEAK_RISE_TORSO_RATIO
        and peak - min(wrist_lifts[:peak_index])
        >= MIN_ATTEMPT_ASCENT_HYSTERESIS_TORSO_RATIO
        and peak - min(wrist_lifts[peak_index + 1 :])
        >= MIN_ATTEMPT_RETURN_HYSTERESIS_TORSO_RATIO
    )


def _confirmed_events(measurements):
    events = []
    candidate_state = None
    candidate_run = []

    for index, item in enumerate(measurements):
        state = item["state"]
        if state == "transition":
            candidate_state = None
            candidate_run = []
            continue
        if state != candidate_state:
            candidate_state = state
            candidate_run = [item]
        else:
            candidate_run.append(item)
        if not _is_confirmed(candidate_run):
            continue

        run_start_index = index - len(candidate_run) + 1
        event = {
            "state": state,
            "run_start_index": run_start_index,
            "confirmed_index": index,
            "run_start_ms": candidate_run[0]["timestamp_ms"],
            "confirmed_ms": candidate_run[-1]["timestamp_ms"],
            "wrist_lift_baseline": mean(
                measurement["wrist_lift"] for measurement in candidate_run
            ),
        }
        previous = events[-1] if events else None
        if previous is None or previous["state"] != state:
            events.append(event)
        elif state == "down" and _is_attempt(
            measurements[previous["confirmed_index"] + 1 : run_start_index + 1],
            down_baseline=previous["wrist_lift_baseline"],
        ):
            events.append(event)
        candidate_run = []

    return events


def _flags_for_segment(measurements, start_index, end_index, *, range_too_small=False):
    segment = measurements[start_index : end_index + 1]
    duration = segment[-1]["timestamp_ms"] - segment[0]["timestamp_ms"]
    flags = []
    if range_too_small:
        flags.append("range_too_small")
    if duration < MIN_REPETITION_DURATION_MS or duration > MAX_REPETITION_DURATION_MS:
        flags.append("tempo_abnormal")
    if min(item["score"] for item in segment) < MIN_CONFIDENCE_SCORE:
        flags.append("low_confidence")
    return flags


def analyze_shoulder_press_keypoints(frames):
    ordered_frames = sorted(frames, key=lambda item: int(item.get("timestamp_ms", 0)))
    side = _select_side(ordered_frames)
    measurements = [_measurement(frame, side) for frame in ordered_frames]
    events = _confirmed_events(measurements)

    rep_details = []
    index = 0
    while index + 1 < len(events):
        first = events[index]
        if first["state"] != "down":
            index += 1
            continue

        if index + 2 < len(events):
            second, third = events[index + 1 : index + 3]
            if second["state"] == "up" and third["state"] == "down":
                flags = _flags_for_segment(
                    measurements,
                    first["run_start_index"],
                    third["confirmed_index"],
                )
                rep_details.append(
                    {
                        "index": len(rep_details) + 1,
                        "start_ms": first["run_start_ms"],
                        "end_ms": third["confirmed_ms"],
                        "is_standard": not flags,
                        "flags": flags,
                        "side": side,
                    }
                )
                index += 2
                continue

        second = events[index + 1]
        if second["state"] == "down":
            flags = _flags_for_segment(
                measurements,
                first["run_start_index"],
                second["confirmed_index"],
                range_too_small=True,
            )
            rep_details.append(
                {
                    "index": len(rep_details) + 1,
                    "start_ms": first["run_start_ms"],
                    "end_ms": second["confirmed_ms"],
                    "is_standard": False,
                    "flags": flags,
                    "side": side,
                }
            )
        index += 1

    standard_count = sum(item["is_standard"] for item in rep_details)
    total_count = len(rep_details)
    return {
        "total_count": total_count,
        "standard_count": standard_count,
        "nonstandard_count": total_count - standard_count,
        "rep_details": rep_details,
        "quality_flags": ["camera_angle_unverified"],
    }
