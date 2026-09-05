from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from motion_analysis_contract import ClaimedJob, MotionCounts

from pp_mcare.actions.base import AnalysisResult
from pp_mcare.pose_inference import InferenceFrame, PersonPose
from pp_mcare.subject_tracker import PrimarySubjectTracker


def _job(**changes) -> ClaimedJob:
    payload = {
        "protocol_version": "1",
        "job_id": 7,
        "action_source_key": "motion-resistance-shoulder-press",
        "algorithm_version": "PP-TinyPose_128x96",
        "rule_version": "shoulder-press-v2",
        "parameter_version": "shoulder-press-v2-defaults",
        "subject_tracker_version": "primary-subject-v1",
        "lease_token": "lease-token",
        "lease_expires_at": "2026-09-05T10:00:00Z",
        "heartbeat_interval_seconds": 60,
        "download": {
            "url": "https://example.invalid/original.mp4",
            "bucket": "bucket",
            "object_key": "original.mp4",
            "expires_at": "2026-09-05T10:00:00Z",
            "size_bytes": 100,
            "content_type": "video/mp4",
        },
        "upload": {
            "bucket": "bucket",
            "object_key": "skeleton.mp4",
            "token": "upload-token",
            "expires_at": "2026-09-05T12:00:00Z",
        },
    }
    payload.update(changes)
    return ClaimedJob.from_dict(payload)


def _person(center_x: float = 0.5, wrist_y: float = 0.4) -> PersonPose:
    points = []
    for index in range(17):
        x = (center_x - 0.08 + (index % 4) * 0.04) * 80
        y = (0.35 + (index // 4) * 0.06) * 60
        points.append([x, y, 0.95])
    points[9][1] = wrist_y * 60
    return PersonPose.from_coco_keypoints(points, frame_width=80, frame_height=60)


def _frame(index: int, people: tuple[PersonPose, ...]) -> InferenceFrame:
    image = np.full((60, 80, 3), index, dtype=np.uint8)
    return InferenceFrame(
        timestamp_ms=index * 40,
        source_fps=25.0,
        image=image,
        people=people,
    )


class FakePoseStream:
    def __init__(self, frames):
        self.frames = tuple(frames)
        self.source_fps = 25.0
        self.decoded_frame_count = 0
        self.inferred_frame_count = 0
        self.iteration_count = 0
        self.closed = False

    def __iter__(self):
        self.iteration_count += 1
        if self.iteration_count > 1:
            raise AssertionError("pose stream 不得被二次迭代")
        for frame in self.frames:
            self.decoded_frame_count += 1
            self.inferred_frame_count += 1
            yield frame

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.closed = True


class FakeEncoder:
    instances = []

    def __init__(self, path, width, height, fps):
        self.path = path
        self.width = width
        self.height = height
        self.fps = fps
        self.frames = []
        self.aborted = False
        self.closed = False
        self.metadata = None
        self.__class__.instances.append(self)

    def write(self, frame):
        self.frames.append(np.array(frame, copy=True))

    @property
    def frame_count(self):
        return len(self.frames)

    def close(self):
        from pp_mcare.media import VideoMetadata

        self.closed = True
        self.metadata = VideoMetadata(
            width=self.width,
            height=self.height,
            fps=self.fps,
            frame_count=len(self.frames),
            duration_seconds=len(self.frames) / self.fps,
            codec_name="h264",
            pixel_format="yuv420p",
            has_audio=False,
            faststart=True,
        )
        return self.metadata

    def abort(self):
        self.aborted = True


class RecordingPlugin:
    def __init__(self, *, consume=True, error=None):
        self.consume = consume
        self.error = error
        self.timestamps = []

    def analyze(self, frames):
        if self.error is not None:
            for frame in frames:
                self.timestamps.append(frame.timestamp_ms)
                raise self.error
        if self.consume:
            last_encoded_count = 0
            for frame in frames:
                self.timestamps.append(frame.timestamp_ms)
                encoded_count = len(FakeEncoder.instances[-1].frames)
                assert encoded_count > last_encoded_count
                last_encoded_count = encoded_count
        return AnalysisResult(
            counts=MotionCounts(0, 0, 0),
            payload={
                "total_count": 0,
                "standard_count": 0,
                "nonstandard_count": 0,
                "quality_flags": [],
            },
        )


def _install_pipeline_fakes(monkeypatch, stream, plugin):
    from pp_mcare import pipeline

    FakeEncoder.instances.clear()
    monkeypatch.setattr(pipeline, "open_full_frame_pose_stream", lambda path: stream)
    monkeypatch.setattr(pipeline, "get_action_plugin", lambda *versions: plugin)
    monkeypatch.setattr(pipeline, "SkeletonVideoEncoder", FakeEncoder)
    monkeypatch.setattr(
        pipeline,
        "render_primary_pose",
        lambda image, person: np.array(image, copy=True) + 10,
    )
    return pipeline


def test_pipeline_uses_one_full_frame_stream_for_counting_and_video(monkeypatch, tmp_path):
    frames = [_frame(index, (_person(center_x=0.5 + index * 0.001),)) for index in range(3)]
    stream = FakePoseStream(frames)
    plugin = RecordingPlugin()
    pipeline = _install_pipeline_fakes(monkeypatch, stream, plugin)
    heartbeats = []

    result = pipeline.run_local_pipeline(
        _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", heartbeats.append
    )

    encoder = FakeEncoder.instances[0]
    assert stream.closed is True
    assert stream.iteration_count == 1
    assert stream.decoded_frame_count == stream.inferred_frame_count == 3
    assert (
        result.decoded_frame_count == result.inferred_frame_count == result.encoded_frame_count == 3
    )
    assert plugin.timestamps == [0, 40, 80]
    assert [int(frame[0, 0, 0]) for frame in encoder.frames] == [10, 11, 12]
    assert heartbeats == ["inference", "inference", "inference"]
    assert result.counts == MotionCounts(0, 0, 0)
    assert result.result_payload["quality_flags"] == ()
    assert "observation_fingerprint" not in repr(result.result_payload)
    with pytest.raises(TypeError):
        result.result_payload["new"] = "bad"
    with pytest.raises(FrozenInstanceError):
        result.decoded_frame_count = 0


def test_pipeline_writes_ambiguous_frame_unchanged_but_skips_it_for_algorithm(
    monkeypatch, tmp_path
):
    first = _person(0.5)
    frames = [
        _frame(0, (first,)),
        _frame(1, (_person(0.49), _person(0.51))),
        _frame(2, ()),
        *[_frame(index, (_person(0.5 + index * 0.0001),)) for index in range(3, 11)],
    ]
    plugin = RecordingPlugin()
    pipeline = _install_pipeline_fakes(monkeypatch, FakePoseStream(frames), plugin)

    result = pipeline.run_local_pipeline(
        _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", lambda stage: None
    )

    encoded = FakeEncoder.instances[0].frames
    assert plugin.timestamps == [0, *[index * 40 for index in range(3, 11)]]
    assert int(encoded[0][0, 0, 0]) == 10
    assert int(encoded[1][0, 0, 0]) == 1
    assert int(encoded[2][0, 0, 0]) == 2
    assert int(encoded[3][0, 0, 0]) == 13
    assert result.tracking_summary["ambiguous_frames"] == 1
    assert result.tracking_summary["missing_frames"] == 1


@pytest.mark.parametrize("failure_source", ["plugin", "heartbeat", "renderer", "encoder"])
def test_pipeline_aborts_encoder_and_closes_stream_on_midstream_failure(
    monkeypatch, tmp_path, failure_source
):
    stream = FakePoseStream([_frame(0, (_person(),)), _frame(1, (_person(0.501),))])
    plugin = (
        RecordingPlugin(error=RuntimeError("plugin failed"))
        if failure_source == "plugin"
        else RecordingPlugin()
    )
    pipeline = _install_pipeline_fakes(monkeypatch, stream, plugin)

    heartbeat_calls = 0

    def heartbeat(stage):
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        if failure_source == "heartbeat" and heartbeat_calls == 2:
            raise RuntimeError("lease lost")
        return None

    if failure_source == "renderer":
        monkeypatch.setattr(
            pipeline,
            "render_primary_pose",
            lambda image, person: (_ for _ in ()).throw(RuntimeError("render failed")),
        )
    if failure_source == "encoder":

        def fail_write(self, frame):
            raise RuntimeError("encoder failed")

        monkeypatch.setattr(FakeEncoder, "write", fail_write)

    with pytest.raises(RuntimeError):
        pipeline.run_local_pipeline(
            _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", heartbeat
        )

    assert stream.closed is True
    if FakeEncoder.instances:
        assert FakeEncoder.instances[0].aborted is True


def test_pipeline_rejects_registry_miss_and_plugin_that_does_not_consume_stream(
    monkeypatch, tmp_path
):
    stream = FakePoseStream([_frame(0, (_person(),))])
    plugin = RecordingPlugin(consume=False)
    pipeline = _install_pipeline_fakes(monkeypatch, stream, plugin)

    with pytest.raises(pipeline.LocalPipelineError, match="完整消费"):
        pipeline.run_local_pipeline(
            _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", lambda stage: None
        )
    assert stream.closed is True
    assert stream.decoded_frame_count == stream.inferred_frame_count == 0

    monkeypatch.setattr(pipeline, "get_action_plugin", lambda *versions: None)
    with pytest.raises(pipeline.LocalPipelineError, match="不支持"):
        pipeline.run_local_pipeline(
            _job(rule_version="shoulder-press-v3"),
            tmp_path / "input.mp4",
            tmp_path / "output.mp4",
            lambda stage: None,
        )


def test_pipeline_surfaces_tracker_finish_and_encoder_close_failures(monkeypatch, tmp_path):
    stream = FakePoseStream([_frame(0, (_person(),))])
    pipeline = _install_pipeline_fakes(monkeypatch, stream, RecordingPlugin())

    class FinishFailureTracker(PrimarySubjectTracker):
        def finish(self):
            raise RuntimeError("tracker finish failed")

    monkeypatch.setattr(pipeline, "PrimarySubjectTracker", FinishFailureTracker)
    with pytest.raises(RuntimeError, match="tracker finish failed"):
        pipeline.run_local_pipeline(
            _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", lambda stage: None
        )
    assert FakeEncoder.instances[0].aborted is True

    class CloseFailureEncoder(FakeEncoder):
        def close(self):
            raise RuntimeError("encoder close failed")

    stream = FakePoseStream([_frame(0, (_person(),))])
    monkeypatch.setattr(pipeline, "PrimarySubjectTracker", PrimarySubjectTracker)
    monkeypatch.setattr(pipeline, "open_full_frame_pose_stream", lambda path: stream)
    monkeypatch.setattr(pipeline, "SkeletonVideoEncoder", CloseFailureEncoder)
    monkeypatch.setattr(pipeline, "get_action_plugin", lambda *versions: RecordingPlugin())
    with pytest.raises(RuntimeError, match="encoder close failed"):
        pipeline.run_local_pipeline(
            _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", lambda stage: None
        )
    assert stream.closed is True
    assert CloseFailureEncoder.instances[-1].aborted is True
