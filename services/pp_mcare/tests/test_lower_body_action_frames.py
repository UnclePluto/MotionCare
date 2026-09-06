import numpy as np
import pytest

from pp_mcare.actions.base import PoseFrame
from pp_mcare.pose_inference import InferenceFrame, PersonPose
from pp_mcare.subject_tracker import TrackedPoseFrame


def test_action_frame_exposes_knees_ankles_without_changing_tracking_points():
    points = [(50, 50, 0.9)] * 17
    points[13] = (40, 120, 0.8)
    points[16] = (60, 180, 0.7)
    person = PersonPose.from_coco_keypoints(points, frame_width=100, frame_height=200)
    frame = InferenceFrame(
        timestamp_ms=100,
        source_fps=60,
        image=np.zeros((200, 100, 3), dtype=np.uint8),
        people=(person,),
    )
    action = TrackedPoseFrame(
        frame=frame,
        primary=person,
        observation_fingerprint=person.fingerprint,
    ).to_action_frame()
    assert action.named_keypoints.get("left_knee") == (0.4, 0.6, 0.8)
    assert action.named_keypoints.get("right_ankle") == (0.6, 0.9, 0.7)
    assert action.coordinate_aspect_ratio == 0.5
    assert "left_knee" not in person.named_keypoints


@pytest.mark.parametrize("ratio", [0, -1, float("nan"), float("inf"), True])
def test_action_frame_rejects_invalid_coordinate_aspect_ratio(ratio):
    with pytest.raises(ValueError):
        PoseFrame(timestamp_ms=0, named_keypoints={}, coordinate_aspect_ratio=ratio)
