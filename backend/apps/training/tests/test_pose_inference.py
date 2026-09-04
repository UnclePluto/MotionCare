from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.training.pose_inference import (
    MotionAnalysisDependencyError,
    PP_TINYPOSE_MODEL_NAME,
    VideoKeypointExtraction,
    convert_paddlex_result,
    create_pose_model,
    extract_video_keypoint_frames,
    extract_video_keypoint_frames_with_stats,
    load_motion_analysis_runtime,
    open_video_keypoint_stream,
    warm_up_pose_model,
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


def test_create_pose_model_forces_cpu_and_disables_hpip(monkeypatch):
    create_model = Mock(return_value=object())
    monkeypatch.setattr(
        "apps.training.pose_inference.load_motion_analysis_runtime",
        lambda: (Mock(), create_model),
    )

    model = create_pose_model()

    assert model is create_model.return_value
    create_model.assert_called_once_with(
        model_name=PP_TINYPOSE_MODEL_NAME,
        device="cpu",
        use_hpip=False,
    )


def test_warm_up_uses_first_decoded_frame_and_releases_capture():
    capture = FakeCapture([0, 100])
    model = FakeModel()

    warm_up_pose_model("ignored.mp4", model=model, capture=capture)

    assert model.seen_frames == [0]
    assert capture.released is True


def test_full_frame_mode_infers_every_decoded_frame():
    capture = FakeCapture([0, 100, 200, 300, 400])
    model = FakeModel()

    result = extract_video_keypoint_frames_with_stats(
        "ignored.mp4",
        sample_fps=None,
        model=model,
        capture=capture,
    )

    assert isinstance(result, VideoKeypointExtraction)
    assert result.decoded_frame_count == 5
    assert result.inferred_frame_count == 5
    assert model.seen_frames == [0, 1, 2, 3, 4]
    assert [frame["timestamp_ms"] for frame in result.frames] == [0, 100, 200, 300, 400]


def test_keypoint_stream_is_lazy_and_infers_every_frame_in_all_mode():
    capture = FakeCapture([0, 100, 200])
    model = FakeModel()

    stream = open_video_keypoint_stream(
        "ignored.mp4",
        sample_fps=None,
        model=model,
        capture=capture,
    )
    assert model.seen_frames == []

    with stream:
        frames = list(stream)

    assert model.seen_frames == [0, 1, 2]
    assert [item["timestamp_ms"] for item in frames] == [0, 100, 200]
    assert all(item["source_fps"] == 10.0 for item in frames)
    assert stream.decoded_frame_count == 3
    assert stream.inferred_frame_count == 3
    assert capture.released is True


def test_keypoint_stream_context_releases_capture_when_consumer_fails():
    capture = FakeCapture([0, 100])
    stream = open_video_keypoint_stream(
        "ignored.mp4",
        sample_fps=None,
        model=FakeModel(),
        capture=capture,
    )

    with pytest.raises(RuntimeError, match="consumer failed"):
        with stream:
            next(stream)
            raise RuntimeError("consumer failed")

    assert capture.released is True


def test_keypoint_stream_keeps_fixed_fps_sampling_and_stats():
    capture = FakeCapture([0, 50, 100, 150, 200])
    model = FakeModel()

    with open_video_keypoint_stream(
        "ignored.mp4",
        sample_fps=10.0,
        model=model,
        capture=capture,
    ) as stream:
        frames = list(stream)

    assert model.seen_frames == [0, 2, 4]
    assert stream.decoded_frame_count == 5
    assert stream.inferred_frame_count == 3
    assert stream.inference_seconds >= 0
    assert [item["timestamp_ms"] for item in frames] == [0, 100, 200]


def test_ten_fps_mode_reports_decoded_and_inferred_counts():
    capture = FakeCapture([0, 50, 100, 150, 200])
    model = FakeModel()

    result = extract_video_keypoint_frames_with_stats(
        "ignored.mp4",
        sample_fps=10,
        model=model,
        capture=capture,
    )

    assert result.decoded_frame_count == 5
    assert result.inferred_frame_count == 3
    assert model.seen_frames == [0, 2, 4]


def test_existing_extractor_still_returns_only_frame_list():
    capture = FakeCapture([0, 100, 200])
    frames = extract_video_keypoint_frames(
        "ignored.mp4",
        sample_fps=5,
        model=FakeModel(),
        capture=capture,
    )

    assert isinstance(frames, list)
    assert [frame["timestamp_ms"] for frame in frames] == [0, 200]


@pytest.mark.parametrize("sample_fps", [0, -1])
def test_stats_extractor_rejects_non_positive_fixed_fps(sample_fps):
    with pytest.raises(ValueError, match="sample_fps"):
        extract_video_keypoint_frames_with_stats(
            "ignored.mp4",
            sample_fps=sample_fps,
            model=FakeModel(),
            capture=FakeCapture([]),
        )
