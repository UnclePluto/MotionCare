from dataclasses import FrozenInstanceError

import pytest

from pp_mcare.actions.base import PoseFrame
from pp_mcare.pose_inference import InferenceFrame, PersonPose
from pp_mcare.subject_tracker import PrimarySubjectTracker, SubjectUnstable


def person(
    *,
    center_x,
    center_y=0.5,
    width=0.20,
    height=0.50,
    score=0.95,
    left_wrist_y=None,
):
    raw = []
    for index in range(17):
        dx = (-0.5 + (index % 4) / 3) * width
        dy = (-0.5 + (index // 4) / 4) * height
        raw.append([(center_x + dx) * 1000, (center_y + dy) * 1000, score])
    if left_wrist_y is not None:
        raw[9][1] = left_wrist_y * 1000
    return PersonPose.from_coco_keypoints(raw, frame_width=1000, frame_height=1000)


def frame(timestamp_ms, people):
    return InferenceFrame(
        timestamp_ms=timestamp_ms,
        source_fps=30.0,
        image=None,
        people=people,
    )


def test_tracker_initializes_to_largest_person_inside_center_seventy_percent():
    edge = person(center_x=0.05, width=0.30, height=0.70)
    small_center = person(center_x=0.45, width=0.15, height=0.40)
    large_center = person(center_x=0.70, width=0.25, height=0.55)

    tracked = PrimarySubjectTracker().observe(frame(0, [edge, small_center, large_center]))

    assert tracked.primary == large_center


def test_tracker_keeps_original_subject_when_larger_bystander_enters():
    tracker = PrimarySubjectTracker()
    trainee = person(center_x=0.50, width=0.20)
    first = tracker.observe(frame(0, [trainee]))
    moved_trainee = person(center_x=0.51, width=0.20)
    bystander = person(center_x=0.25, width=0.35, height=0.70)

    second = tracker.observe(frame(33, [moved_trainee, bystander]))

    assert first.primary == trainee
    assert second.primary.raw_keypoints == moved_trainee.raw_keypoints
    assert second.primary.raw_keypoints != bystander.raw_keypoints
    assert second.primary.fingerprint == first.primary.fingerprint
    assert second.observation_fingerprint == moved_trainee.fingerprint
    assert second.observation_fingerprint != bystander.fingerprint


def test_tracker_matches_by_pose_when_detection_order_swaps_during_crossing():
    tracker = PrimarySubjectTracker()
    trainee = person(center_x=0.42, center_y=0.48, height=0.50)
    tracker.observe(frame(0, [trainee]))

    step_one = tracker.observe(
        frame(
            33,
            [
                person(center_x=0.60, center_y=0.62, height=0.65),
                person(center_x=0.47, center_y=0.48, height=0.50),
            ],
        )
    )
    step_two = tracker.observe(
        frame(
            66,
            [
                person(center_x=0.52, center_y=0.48, height=0.50),
                person(center_x=0.55, center_y=0.62, height=0.65),
            ],
        )
    )

    assert step_one.primary.bbox[1] < 0.3
    assert step_two.primary.bbox[1] < 0.3


def test_tracker_uses_motion_history_to_keep_real_subject_through_crossing_and_occlusion():
    tracker = PrimarySubjectTracker()
    first = tracker.observe(
        frame(
            0,
            [
                person(center_x=0.35, width=0.20, left_wrist_y=0.45),
                person(center_x=0.65, width=0.20, left_wrist_y=0.55),
            ],
        )
    )
    second = tracker.observe(
        frame(
            33,
            [
                person(center_x=0.56, width=0.20, left_wrist_y=0.55),
                person(center_x=0.44, width=0.20, left_wrist_y=0.45),
            ],
        )
    )
    crossed = tracker.observe(
        frame(
            66,
            [
                person(center_x=0.45, width=0.20, left_wrist_y=0.55),
                person(center_x=0.55, width=0.20, left_wrist_y=0.45),
            ],
        )
    )
    occluded = tracker.observe(frame(99, [person(center_x=0.35, width=0.20, left_wrist_y=0.55)]))
    recovered = tracker.observe(
        frame(
            132,
            [
                person(center_x=0.30, width=0.20, left_wrist_y=0.55),
                person(center_x=0.70, width=0.20, left_wrist_y=0.45),
            ],
        )
    )

    assert first.primary.named_keypoints["left_wrist"][1] == pytest.approx(0.45)
    assert second.primary.named_keypoints["left_wrist"][1] == pytest.approx(0.45)
    assert crossed.primary is None
    assert crossed.ambiguous is True
    assert crossed.observation_fingerprint is None
    assert occluded.primary is None
    assert recovered.primary.named_keypoints["left_wrist"][1] == pytest.approx(0.45)
    assert recovered.primary.raw_keypoints[9][1] == pytest.approx(450.0)


def test_tracker_skips_when_last_position_and_prediction_disagree_after_subject_slows():
    tracker = PrimarySubjectTracker()
    tracker.observe(frame(0, [person(center_x=0.35), person(center_x=0.65, left_wrist_y=0.55)]))
    tracker.observe(frame(33, [person(center_x=0.45), person(center_x=0.55, left_wrist_y=0.55)]))
    actual_subject = person(center_x=0.45)
    bystander = person(center_x=0.55, left_wrist_y=0.55)

    uncertain = tracker.observe(frame(66, [actual_subject, bystander]))

    assert uncertain.primary is None
    assert uncertain.observation_fingerprint is None
    assert uncertain.ambiguous is True
    assert uncertain.to_action_frame() is None


def test_tracker_skips_crossing_when_last_and_prediction_evidence_conflict():
    tracker = PrimarySubjectTracker()
    tracker.observe(frame(0, [person(center_x=0.40), person(center_x=0.60, left_wrist_y=0.55)]))
    tracker.observe(frame(33, [person(center_x=0.48), person(center_x=0.52, left_wrist_y=0.55)]))
    actual_subject = person(center_x=0.58)
    bystander = person(center_x=0.42, left_wrist_y=0.55)

    uncertain = tracker.observe(frame(66, [actual_subject, bystander]))

    assert uncertain.primary is None
    assert uncertain.observation_fingerprint is None
    assert uncertain.ambiguous is True
    assert actual_subject.raw_keypoints != bystander.raw_keypoints


def test_tracker_applies_max_jump_to_actual_displacement_not_only_prediction_residual():
    tracker = PrimarySubjectTracker()
    tracker.observe(frame(0, [person(center_x=0.25)]))
    tracker.observe(frame(100, [person(center_x=0.40)]))
    far_candidate = person(center_x=0.85)

    skipped = tracker.observe(frame(400, [far_candidate]))

    assert skipped.primary is None
    assert skipped.observation_fingerprint is None
    assert skipped.ambiguous is False


def test_tracker_rejects_low_confidence_bystander_with_only_tiny_bbox_overlap():
    tracker = PrimarySubjectTracker()
    tracker.observe(frame(0, [person(center_x=0.50, score=0.95)]))

    skipped = tracker.observe(frame(33, [person(center_x=0.69, score=0.10)]))

    assert skipped.primary is None
    assert skipped.ambiguous is False


def test_tracker_accepts_low_confidence_detection_only_with_high_iou_continuity():
    tracker = PrimarySubjectTracker()
    tracker.observe(frame(0, [person(center_x=0.50, score=0.95)]))

    continued = tracker.observe(frame(33, [person(center_x=0.505, score=0.10)]))

    assert continued.primary is not None
    assert continued.primary.mean_score == pytest.approx(0.10)


def test_tracker_short_missing_frame_keeps_lock_without_outputting_bystander():
    tracker = PrimarySubjectTracker()
    trainee = person(center_x=0.5)
    tracker.observe(frame(0, [trainee]))

    missing = tracker.observe(frame(2999, [person(center_x=0.02)]))
    recovered = tracker.observe(frame(3000, [person(center_x=0.51)]))

    assert missing.primary is None
    assert missing.to_action_frame() is None
    assert recovered.primary is not None
    assert recovered.to_action_frame().timestamp_ms == 3000


def test_tracker_raises_when_continuous_loss_reaches_three_seconds():
    tracker = PrimarySubjectTracker()
    tracker.observe(frame(0, [person(center_x=0.5)]))

    tracker.observe(frame(2999, []))
    with pytest.raises(SubjectUnstable, match="连续失锁"):
        tracker.observe(frame(3000, []))


def test_tracker_rejects_first_frame_without_central_subject():
    with pytest.raises(SubjectUnstable, match="无法建立"):
        PrimarySubjectTracker().observe(frame(0, [person(center_x=0.02)]))


def test_tracker_does_not_output_an_ambiguous_candidate_and_reports_ratio():
    tracker = PrimarySubjectTracker()
    tracker.observe(frame(0, [person(center_x=0.50)]))

    ambiguous = tracker.observe(frame(33, [person(center_x=0.48), person(center_x=0.52)]))

    assert ambiguous.primary is None
    assert ambiguous.ambiguous is True
    assert ambiguous.to_action_frame() is None
    with pytest.raises(SubjectUnstable, match="歧义帧占比"):
        tracker.finish()


def test_tracker_allows_ambiguity_ratio_at_exactly_ten_percent():
    tracker = PrimarySubjectTracker()
    tracker.observe(frame(0, [person(center_x=0.50)]))
    for index in range(1, 9):
        tracker.observe(frame(index * 33, [person(center_x=0.50 + index * 0.001)]))
    tracker.observe(frame(9 * 33, [person(center_x=0.49), person(center_x=0.51)]))

    summary = tracker.finish()

    assert summary["ambiguity_ratio"] == pytest.approx(0.1)
    assert summary["subject_tracker_version"] == "primary-subject-v1"
    assert summary["max_normalized_jump"] == 0.35
    assert summary["lost_timeout_ms"] == 3000
    assert summary["max_ambiguity_ratio"] == 0.10
    assert summary["minimum_common_reliable_keypoints"] == 4
    assert summary["minimum_fallback_iou"] == 0.70
    assert summary["reliable_keypoint_score"] == 0.5
    assert summary["central_region_margin"] == 0.15
    assert summary["ambiguous_distance_delta"] == 0.03
    assert summary["history_clear_match_distance"] == 0.175
    assert summary["max_prediction_intervals"] == 3.0


def test_tracked_frame_exposes_only_primary_named_points_to_action_plugin():
    trainee = person(center_x=0.5)
    bystander = person(center_x=0.8)
    tracked = PrimarySubjectTracker().observe(frame(0, [trainee, bystander]))

    action_frame = tracked.to_action_frame()

    assert isinstance(action_frame, PoseFrame)
    assert action_frame.named_keypoints == trainee.named_keypoints
    assert not hasattr(action_frame, "people")
    assert tracked.primary.raw_keypoints == trainee.raw_keypoints


def test_tracker_dtos_are_deeply_immutable_and_reject_bad_frame_values():
    people = [person(center_x=0.5)]
    inference_frame = frame(0, people)
    people.clear()
    assert len(inference_frame.people) == 1
    with pytest.raises(FrozenInstanceError):
        inference_frame.timestamp_ms = 1

    with pytest.raises(ValueError):
        InferenceFrame(timestamp_ms=True, source_fps=30.0, image=None, people=[])
    with pytest.raises(ValueError):
        InferenceFrame(timestamp_ms=0, source_fps=float("nan"), image=None, people=[])
    with pytest.raises(TypeError):
        InferenceFrame(timestamp_ms=0, source_fps=30.0, image=None, people=[object()])


def test_tracker_rejects_non_monotonic_observation_timestamps():
    tracker = PrimarySubjectTracker()
    tracker.observe(frame(10, [person(center_x=0.5)]))

    with pytest.raises(ValueError, match="严格递增"):
        tracker.observe(frame(10, [person(center_x=0.5)]))


def test_tracker_finish_without_observations_fails_safely():
    with pytest.raises(SubjectUnstable, match="未建立"):
        PrimarySubjectTracker().finish()


def test_tracker_treats_jump_over_threshold_as_loss_and_accepts_boundary():
    boundary_tracker = PrimarySubjectTracker()
    boundary_tracker.observe(frame(0, [person(center_x=0.30)]))
    at_boundary = boundary_tracker.observe(frame(33, [person(center_x=0.65)]))
    assert at_boundary.primary is not None

    over_tracker = PrimarySubjectTracker()
    over_tracker.observe(frame(0, [person(center_x=0.30)]))
    over = over_tracker.observe(frame(33, [person(center_x=0.651)]))
    assert over.primary is None
