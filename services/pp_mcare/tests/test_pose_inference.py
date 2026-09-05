import math
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import NamedTuple

import pytest

from pp_mcare.pose_inference import (
    InferenceFrame,
    InferenceDataValidationError,
    MotionAnalysisDependencyError,
    MotionAnalysisInferenceError,
    PersonPose,
    create_pose_model,
    open_full_frame_pose_stream,
)


class FakeFrame(NamedTuple):
    index: int

    @property
    def shape(self):
        return (100, 200, 3)


class FakeCapture:
    def __init__(self, timestamps, *, fps=10.0, opened=True, frames=None):
        self.timestamps = list(timestamps)
        self.fps = fps
        self.opened = opened
        self.frames = frames
        self.next_index = 0
        self.current_timestamp = 0.0
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        if self.next_index >= len(self.timestamps):
            return False, None
        index = self.next_index
        self.current_timestamp = self.timestamps[index]
        self.next_index += 1
        if self.frames is not None:
            return True, self.frames[index]
        return True, FakeFrame(index)

    def get(self, property_id):
        if property_id == 0:
            return self.current_timestamp
        if property_id == 5:
            return self.fps
        return 0.0

    def release(self):
        self.released = True


def _person(*, center_x=0.5, center_y=0.5, score=0.9):
    points = []
    for index in range(17):
        x = (center_x - 0.08 + (index % 4) * 0.04) * 200
        y = (center_y - 0.16 + (index // 4) * 0.08) * 100
        points.append([x, y, score])
    return {"keypoints": points}


def _result(*people):
    return SimpleNamespace(json={"res": {"kpts": list(people)}})


class FakeModel:
    def __init__(self, results):
        self.results = list(results)
        self.seen_frames = []
        self.closed = False

    def predict(self, frame):
        self.seen_frames.append(frame.index)
        return [self.results[len(self.seen_frames) - 1]]

    def close(self):
        self.closed = True


def test_pose_stream_infers_every_decoded_frame_and_keeps_all_people():
    capture = FakeCapture([0, 100, 200])
    model = FakeModel(
        [
            _result(_person(center_x=0.4), _person(center_x=0.7)),
            _result(_person(center_x=0.41)),
            _result(),
        ]
    )

    with open_full_frame_pose_stream("video.mp4", model=model, capture=capture) as stream:
        frames = list(stream)

    assert stream.decoded_frame_count == 3
    assert stream.inferred_frame_count == 3
    assert model.seen_frames == [0, 1, 2]
    assert len(frames[0].people) == 2
    assert len(frames[0].people[0].raw_keypoints) == 17
    assert frames[0].people[0].named_keypoints["left_shoulder"] == pytest.approx((0.36, 0.42, 0.9))
    assert capture.released is True


def test_pose_stream_is_lazy_and_releases_on_consumer_error():
    capture = FakeCapture([0, 100])
    model = FakeModel([_result(_person()), _result(_person())])
    stream = open_full_frame_pose_stream("video.mp4", model=model, capture=capture)
    assert model.seen_frames == []

    with pytest.raises(RuntimeError, match="consumer broke"):
        with stream:
            next(stream)
            raise RuntimeError("consumer broke")

    assert model.seen_frames == [0]
    assert capture.released is True
    assert model.closed is False


def test_pose_stream_releases_on_inference_and_conversion_errors():
    class ExplodingModel:
        def predict(self, frame):
            raise RuntimeError("model failed")

    inference_capture = FakeCapture([0])
    with pytest.raises(RuntimeError, match="model failed"):
        with open_full_frame_pose_stream(
            "video.mp4", model=ExplodingModel(), capture=inference_capture
        ) as stream:
            next(stream)
    assert inference_capture.released is True

    conversion_capture = FakeCapture([0])
    malformed = FakeModel([SimpleNamespace(json={"unexpected": {}})])
    with pytest.raises(MotionAnalysisInferenceError, match="结果结构无效"):
        with open_full_frame_pose_stream(
            "video.mp4", model=malformed, capture=conversion_capture
        ) as stream:
            next(stream)
    assert conversion_capture.released is True


def test_pose_stream_skips_invalid_people_without_dropping_valid_people():
    invalid = _person()
    invalid["keypoints"][3][0] = math.nan
    capture = FakeCapture([0])
    model = FakeModel([_result(invalid, _person(center_x=0.7))])

    with open_full_frame_pose_stream("video.mp4", model=model, capture=capture) as stream:
        frame = next(stream)

    assert len(frame.people) == 1
    assert frame.people[0].named_keypoints["left_shoulder"][0] == pytest.approx(0.66)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not-json",
        {"res": {"kpts": "not-a-list"}},
        {"res": []},
    ],
)
def test_pose_stream_rejects_malformed_paddlex_payload(payload):
    capture = FakeCapture([0])
    model = FakeModel([SimpleNamespace(json=payload)])

    with pytest.raises(MotionAnalysisInferenceError):
        with open_full_frame_pose_stream("video.mp4", model=model, capture=capture) as stream:
            next(stream)

    assert capture.released is True


def test_person_pose_is_strict_deeply_immutable_and_has_deterministic_fingerprint():
    raw = [[float(index), float(index + 1), 0.9] for index in range(17)]
    first = PersonPose.from_coco_keypoints(raw, frame_width=100, frame_height=200)
    second = PersonPose.from_coco_keypoints(raw, frame_width=100, frame_height=200)
    raw[5][0] = 999.0

    assert first.raw_keypoints[5] == (5.0, 6.0, 0.9)
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint
    with pytest.raises(TypeError):
        first.named_keypoints["left_shoulder"] = (0.0, 0.0, 0.0)
    with pytest.raises(FrozenInstanceError):
        first.mean_score = 0.0


@pytest.mark.parametrize(
    ("raw", "width", "height"),
    [
        ([[0.0, 0.0, 0.9]] * 16, 100, 100),
        ([[0.0, 0.0, True]] * 17, 100, 100),
        ([[0.0, 0.0, 1.1]] * 17, 100, 100),
        ([[0.0, math.inf, 0.9]] * 17, 100, 100),
        ([[0.0, 0.0, 0.9]] * 17, True, 100),
        ([[0.0, 0.0, 0.9]] * 17, 0, 100),
    ],
)
def test_person_pose_rejects_malformed_numeric_input(raw, width, height):
    with pytest.raises(InferenceDataValidationError):
        PersonPose.from_coco_keypoints(raw, frame_width=width, frame_height=height)


def test_person_pose_direct_constructor_reports_stable_validation_for_bad_collections():
    with pytest.raises(InferenceDataValidationError, match="17 个"):
        PersonPose(
            raw_keypoints=None,
            named_keypoints={},
            bbox=(0.0, 0.0, 1.0, 1.0),
            mean_score=0.9,
            fingerprint="fixed",
        )

    raw = tuple((0.0, 0.0, 0.9) for _ in range(17))
    named = {
        name: (0.0, 0.0, 0.9)
        for name in (
            "left_shoulder",
            "right_shoulder",
            "left_elbow",
            "right_elbow",
            "left_wrist",
            "right_wrist",
            "left_hip",
            "right_hip",
        )
    }
    with pytest.raises(InferenceDataValidationError, match="bbox"):
        PersonPose(
            raw_keypoints=raw,
            named_keypoints=named,
            bbox=None,
            mean_score=0.9,
            fingerprint="fixed",
        )


def test_person_pose_direct_constructor_requires_complete_normalized_named_points():
    raw = tuple((float(index), float(index), 0.9) for index in range(17))
    with pytest.raises(InferenceDataValidationError, match="八个"):
        PersonPose(
            raw_keypoints=raw,
            named_keypoints={},
            bbox=(0.0, 0.0, 0.5, 0.5),
            mean_score=0.9,
            fingerprint="fixed",
        )


@pytest.mark.parametrize("fps", [0, -1, True, math.nan, math.inf])
def test_pose_stream_rejects_unusable_source_fps_and_releases_capture(fps):
    capture = FakeCapture([], fps=fps)
    with pytest.raises(MotionAnalysisInferenceError, match="帧率"):
        open_full_frame_pose_stream("video.mp4", model=object(), capture=capture)
    assert capture.released is True


def test_pose_stream_uses_deterministic_strictly_monotonic_timestamp_fallback():
    capture = FakeCapture([0.0, math.nan, 50.0, -1.0, 400.0], fps=10.0)
    model = FakeModel([_result(_person()) for _ in range(5)])

    with open_full_frame_pose_stream("video.mp4", model=model, capture=capture) as stream:
        frames = list(stream)

    assert [frame.timestamp_ms for frame in frames] == [0, 100, 200, 300, 400]


def test_pose_stream_counts_only_real_predict_and_result_materialization_time(monkeypatch):
    from pp_mcare import pose_inference

    capture = FakeCapture([0.0, 100.0], fps=10.0)
    model = FakeModel([_result(_person()), _result(_person())])
    ticks = iter([1.0, 1.25, 2.0, 2.5])
    monkeypatch.setattr(pose_inference.time, "monotonic", lambda: next(ticks))

    with open_full_frame_pose_stream("video.mp4", model=model, capture=capture) as stream:
        list(stream)
        assert stream.inference_seconds == pytest.approx(0.75)


def test_pose_stream_rejects_invalid_frame_and_empty_video_and_releases():
    invalid_capture = FakeCapture([0], frames=[object()])
    with pytest.raises(MotionAnalysisInferenceError, match="视频帧尺寸无效"):
        with open_full_frame_pose_stream(
            "video.mp4", model=FakeModel([_result()]), capture=invalid_capture
        ) as stream:
            next(stream)
    assert invalid_capture.released is True

    empty_capture = FakeCapture([])
    with pytest.raises(MotionAnalysisInferenceError, match="没有可分析帧"):
        with open_full_frame_pose_stream(
            "video.mp4", model=FakeModel([]), capture=empty_capture
        ) as stream:
            next(stream)
    assert empty_capture.released is True


def test_unopened_capture_is_released():
    capture = FakeCapture([], opened=False)
    with pytest.raises(MotionAnalysisInferenceError, match="无法解码"):
        open_full_frame_pose_stream("video.mp4", model=object(), capture=capture)
    assert capture.released is True


def test_runtime_import_is_lazy_and_reports_missing_dependencies(monkeypatch):
    def missing_module(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.import_module", missing_module)

    with pytest.raises(MotionAnalysisDependencyError, match="推理依赖"):
        create_pose_model()


def test_open_stream_releases_supplied_capture_when_model_creation_fails(monkeypatch):
    capture = FakeCapture([])

    def fail_model_creation(**kwargs):
        raise RuntimeError("model creation failed")

    monkeypatch.setattr(
        "pp_mcare.pose_inference.load_motion_analysis_runtime",
        lambda: (object(), fail_model_creation),
    )

    with pytest.raises(RuntimeError, match="model creation failed"):
        open_full_frame_pose_stream("video.mp4", capture=capture)

    assert capture.released is True


def test_inference_frame_copies_and_freezes_numpy_style_image():
    class Flags:
        writeable = True

    class NumpyStyleImage:
        def __init__(self, pixels):
            self.pixels = list(pixels)
            self.flags = Flags()

        def copy(self):
            return NumpyStyleImage(self.pixels)

        def setflags(self, *, write):
            self.flags.writeable = write

        def __getitem__(self, index):
            return self.pixels[index]

        def __setitem__(self, index, value):
            if not self.flags.writeable:
                raise ValueError("image is read-only")
            self.pixels[index] = value

    source = NumpyStyleImage([1, 2, 3])
    inference_frame = InferenceFrame(
        timestamp_ms=0,
        source_fps=30.0,
        image=source,
        people=(),
    )
    source.pixels[0] = 99

    assert inference_frame.image is not source
    assert inference_frame.image[0] == 1
    assert inference_frame.image.flags.writeable is False
    with pytest.raises(ValueError, match="read-only"):
        inference_frame.image[0] = 42


def test_inference_frame_rejects_mutable_image_without_readonly_freeze_support():
    with pytest.raises(InferenceDataValidationError, match="image"):
        InferenceFrame(
            timestamp_ms=0,
            source_fps=30.0,
            image=[1, 2, 3],
            people=(),
        )
