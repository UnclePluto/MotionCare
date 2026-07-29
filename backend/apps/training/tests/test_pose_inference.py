from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.training.pose_inference import (
    MotionAnalysisDependencyError,
    convert_paddlex_result,
    extract_video_keypoint_frames,
    load_motion_analysis_runtime,
)


def _person(score, *, offset=0):
    return {
        "keypoints": [
            [offset + index * 10, offset + index * 5, score]
            for index in range(17)
        ]
    }


def _result(score=0.9, *, offset=0):
    return SimpleNamespace(json={"res": {"kpts": [_person(score, offset=offset)]}})


def test_converts_best_paddlex_person_from_coco_pixels_to_normalized_joints():
    result = SimpleNamespace(
        json={
            "res": {
                "kpts": [
                    _person(0.2, offset=100),
                    _person(0.9),
                ]
            }
        }
    )

    keypoints = convert_paddlex_result(result, frame_width=200, frame_height=100)

    assert keypoints["left_shoulder"] == {"x": 0.25, "y": 0.25, "score": 0.9}
    assert keypoints["right_shoulder"] == {"x": 0.3, "y": 0.3, "score": 0.9}
    assert keypoints["left_elbow"] == {"x": 0.35, "y": 0.35, "score": 0.9}
    assert keypoints["right_elbow"] == {"x": 0.4, "y": 0.4, "score": 0.9}
    assert keypoints["left_wrist"] == {"x": 0.45, "y": 0.45, "score": 0.9}
    assert keypoints["right_wrist"] == {"x": 0.5, "y": 0.5, "score": 0.9}
    assert keypoints["left_hip"] == {"x": 0.55, "y": 0.55, "score": 0.9}
    assert keypoints["right_hip"] == {"x": 0.6, "y": 0.6, "score": 0.9}


class FakeFrame:
    shape = (100, 200, 3)

    def __init__(self, index):
        self.index = index


class FakeCapture:
    def __init__(self, timestamps):
        self.timestamps = timestamps
        self.next_index = 0
        self.current_timestamp = 0
        self.released = False

    def isOpened(self):
        return True

    def read(self):
        if self.next_index >= len(self.timestamps):
            return False, None
        index = self.next_index
        self.current_timestamp = self.timestamps[index]
        self.next_index += 1
        return True, FakeFrame(index)

    def get(self, property_id):
        if property_id == 0:
            return self.current_timestamp
        if property_id == 5:
            return 10.0
        return 0.0

    def release(self):
        self.released = True


class FakeModel:
    def __init__(self):
        self.seen_frames = []

    def predict(self, frame):
        self.seen_frames.append(frame.index)
        return [_result()]


def test_samples_video_frames_and_runs_fake_model_without_heavy_runtime():
    capture = FakeCapture([0, 100, 200, 300, 400])
    model = FakeModel()

    frames = extract_video_keypoint_frames(
        "ignored.mp4",
        sample_fps=5,
        model=model,
        capture=capture,
    )

    assert model.seen_frames == [0, 2, 4]
    assert [frame["timestamp_ms"] for frame in frames] == [0, 200, 400]
    assert frames[0]["keypoints"]["left_shoulder"]["x"] == 0.25
    assert capture.released is True


def test_releases_capture_when_inference_fails():
    capture = FakeCapture([0])
    model = Mock()
    model.predict.side_effect = RuntimeError("inference failed")

    with pytest.raises(RuntimeError, match="inference failed"):
        extract_video_keypoint_frames(
            "ignored.mp4",
            model=model,
            capture=capture,
        )

    assert capture.released is True


def test_missing_optional_dependency_fails_only_when_runtime_is_loaded(monkeypatch):
    def missing_module(name):
        if name == "cv2":
            raise ModuleNotFoundError("No module named 'cv2'")
        return Mock()

    monkeypatch.setattr("importlib.import_module", missing_module)

    with pytest.raises(MotionAnalysisDependencyError, match="motion-analysis"):
        load_motion_analysis_runtime()
