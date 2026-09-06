"""Small, time-based primitives shared by independently versioned action plugins."""

from __future__ import annotations

import math
from collections import deque
from statistics import median

from motion_analysis_contract import validate_counts

from .base import ActionAnalysisError, AnalysisResult


def point(frame, name, *, minimum_score=0.35):
    value = frame.named_keypoints.get(name)
    if value is None or not all(math.isfinite(v) for v in value):
        return None
    x, y, score = value
    if not minimum_score <= score <= 1:
        return None
    return x * frame.coordinate_aspect_ratio, y, score


def angle(a, b, c):
    u = (a[0] - b[0], a[1] - b[1])
    v = (c[0] - b[0], c[1] - b[1])
    denominator = math.hypot(*u) * math.hypot(*v)
    if denominator < 1e-8:
        return None
    return math.degrees(math.acos(max(-1, min(1, (u[0] * v[0] + u[1] * v[1]) / denominator))))


class CycleCounter:
    """Rest -> excursion -> rest, with hysteresis, dwell and missing-data reset."""

    def __init__(
        self,
        *,
        rest,
        active,
        prominence,
        standard_peak,
        minimum_duration_ms=600,
        max_missing_gap_ms=600,
        active_dwell_ms=80,
        return_dwell_ms=80,
        minimum_interval_ms=0,
        count_on_active=False,
    ):
        self.rest = rest
        self.active = active
        self.prominence = prominence
        self.standard_peak = standard_peak
        self.minimum_duration_ms = minimum_duration_ms
        self.max_missing_gap_ms = max_missing_gap_ms
        self.active_dwell_ms = active_dwell_ms
        self.return_dwell_ms = return_dwell_ms
        self.minimum_interval_ms = minimum_interval_ms
        self.count_on_active = count_on_active
        self.window = deque()
        self.last_valid = None
        self.events = []
        self.reset()

    def reset(self):
        self.window.clear()
        self.armed = False
        self.started = None
        self.peak = -math.inf
        self.peak_ms = None
        self.rest_value = None
        self.active_since = None
        self.reached = False
        self.return_since = None
        self.rest_since = None
        self.quality_observed = False
        self.counted = False

    def observe(self, timestamp, value, *, can_arm=True, quality_ok=True):
        if self.last_valid is not None and timestamp - self.last_valid > self.max_missing_gap_ms:
            self.reset()
        if value is None or not math.isfinite(value):
            return
        self.last_valid = timestamp
        self.window.append((timestamp, value))
        while self.window and self.window[0][0] < timestamp - 120:
            self.window.popleft()
        smoothed = median(v for _, v in self.window)
        if not self.armed:
            if smoothed <= self.rest and can_arm:
                if self.rest_since is None:
                    self.rest_since = timestamp
                if timestamp - self.rest_since >= 80:
                    self.armed = True
                    self.rest_value = smoothed
            else:
                self.rest_since = None
            return
        if self.started is None:
            if smoothed <= self.rest:
                self.rest_value = min(self.rest_value, smoothed)
                return
            self.started = timestamp
        if smoothed > self.peak:
            self.peak, self.peak_ms = smoothed, timestamp
        if smoothed >= self.active:
            self.quality_observed |= quality_ok
            if self.active_since is None:
                self.active_since = timestamp
            if timestamp - self.active_since >= self.active_dwell_ms:
                self.reached = True
        else:
            self.active_since = None
        if self.count_on_active and smoothed >= self.active:
            self._record_event(timestamp)
        if smoothed > self.rest:
            self.return_since = None
            return
        if self.return_since is None:
            self.return_since = timestamp
        if timestamp - self.return_since < self.return_dwell_ms:
            return
        if not self.count_on_active:
            self._record_event(timestamp)
        self.reset()
        self.armed = can_arm
        self.rest_value = smoothed

    def _record_event(self, timestamp):
        duration = timestamp - self.started
        if (
            not self.counted
            and self.reached
            and self.peak - self.rest_value >= self.prominence
            and duration >= self.minimum_duration_ms
            and (
                not self.events
                or self.peak_ms - self.events[-1]["peak_ms"] >= self.minimum_interval_ms
            )
        ):
            self.events.append(
                {
                    "start_ms": self.started,
                    "peak_ms": self.peak_ms,
                    "end_ms": timestamp,
                    "peak_value": round(self.peak, 3),
                    "excursion": round(self.peak - self.rest_value, 3),
                    "standard": self.peak >= self.standard_peak and self.quality_observed,
                }
            )
            self.counted = True


def analyze_cycles(
    frames, *, plugin, channels, measurement, counter_factory, aggregation, eligibility=None
):
    counters = {channel: counter_factory() for channel in channels}
    reliable = dict.fromkeys(channels, 0)
    count = 0
    last = -1
    first = None
    for frame in frames:
        if frame.timestamp_ms <= last:
            raise ValueError("动作帧时间戳必须严格递增")
        first = frame.timestamp_ms if first is None else first
        last = frame.timestamp_ms
        count += 1
        values = measurement(frame)
        eligible = eligibility(frame) if eligibility else {}
        for channel, counter in counters.items():
            value = values.get(channel)
            reliable[channel] += int(value is not None)
            can_arm, quality_ok = eligible.get(channel, (True, True))
            counter.observe(last, value, can_arm=can_arm, quality_ok=quality_ok)
    if not count or max(reliable.values(), default=0) / count < 0.2:
        raise ActionAnalysisError("可用动作关键点不足，无法可靠计数")
    if aggregation == "maximum":
        selected = max(channels, key=lambda s: (len(counters[s].events), reliable[s]))
        selected_channels = [selected]
    else:
        selected = "body" if channels == ("body",) else "both"
        selected_channels = channels
    side_events = {
        channel: [
            {**event, "standard": event["standard"] and reliable[channel] / count >= 0.7}
            for event in counter.events
        ]
        for channel, counter in counters.items()
    }
    events = sorted(
        [
            {**event, "side": channel}
            for channel in selected_channels
            for event in side_events[channel]
        ],
        key=lambda event: (event["end_ms"], event["side"]),
    )
    coverage = max(reliable.values()) / count
    for i, event in enumerate(events, 1):
        event["index"] = i
    standard = sum(event["standard"] for event in events)
    payload = {
        "total_count": len(events),
        "standard_count": standard,
        "nonstandard_count": len(events) - standard,
        "algorithm_version": plugin.algorithm_version,
        "rule_version": plugin.rule_version,
        "parameter_version": plugin.parameter_version,
        "pose_preprocessing_version": plugin.pose_preprocessing_version,
        "processed_frame_count": count,
        "analysis_duration_ms": last - first,
        "counting_mode": aggregation,
        "completion_phase": getattr(plugin, "completion_phase", "return_to_rest"),
        "counting_side": selected,
        "left_event_count": len(counters["left"].events) if "left" in counters else 0,
        "right_event_count": len(counters["right"].events) if "right" in counters else 0,
        "keypoint_coverage_ratio": coverage,
        "confidence_level": "medium" if coverage >= 0.7 else "low",
        "quality_validation_status": "provisional_unvalidated",
        "quality_flags": [
            "single_reference_video",
            "quality_rules_unvalidated",
            "camera_angle_unverified",
        ],
        "rep_details": events,
        "side_rep_details": side_events,
    }
    return AnalysisResult(validate_counts(payload), payload)
