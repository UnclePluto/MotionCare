from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from motion_analysis_contract import ClaimedJob, CompletionPayload, MotionCounts, SkeletonArtifact

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
            "object_hash": "FqiniuOriginalHash1234567890abc",
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
        self.finished = False
        self.committed = False
        self.metadata = None
        self.__class__.instances.append(self)

    def write(self, frame):
        self.frames.append(np.array(frame, copy=True))

    @property
    def frame_count(self):
        return len(self.frames)

    @property
    def artifact_size_bytes(self):
        return 123

    def finish(self):
        from pp_mcare.media import VideoMetadata

        self.finished = True
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

    def commit(self):
        if not self.finished:
            raise RuntimeError("finish required")
        self.committed = True
        self.closed = True

    def close(self):
        metadata = self.finish()
        self.commit()
        return metadata

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
    from pp_mcare.media import SourceVideoMetadata

    FakeEncoder.instances.clear()
    monkeypatch.setattr(pipeline, "open_full_frame_pose_stream", lambda path: stream)
    monkeypatch.setattr(pipeline, "get_action_plugin", lambda *versions: plugin)
    monkeypatch.setattr(pipeline, "SkeletonVideoEncoder", FakeEncoder)
    monkeypatch.setattr(
        pipeline,
        "probe_source_video",
        lambda path: SourceVideoMetadata(
            width=80,
            height=60,
            fps=25.0,
            frame_count=len(stream.frames),
            duration_seconds=len(stream.frames) / 25.0,
            codec_name="h264",
        ),
    )
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
    assert encoder.finished is True
    assert encoder.committed is True
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
        def finish(self):
            raise RuntimeError("encoder finish failed")

    stream = FakePoseStream([_frame(0, (_person(),))])
    monkeypatch.setattr(pipeline, "PrimarySubjectTracker", PrimarySubjectTracker)
    monkeypatch.setattr(pipeline, "open_full_frame_pose_stream", lambda path: stream)
    monkeypatch.setattr(pipeline, "SkeletonVideoEncoder", CloseFailureEncoder)
    monkeypatch.setattr(pipeline, "get_action_plugin", lambda *versions: RecordingPlugin())
    with pytest.raises(RuntimeError, match="encoder finish failed"):
        pipeline.run_local_pipeline(
            _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", lambda stage: None
        )
    assert stream.closed is True
    assert CloseFailureEncoder.instances[-1].aborted is True


def test_pipeline_compares_output_to_independent_input_duration_before_commit(
    monkeypatch, tmp_path
):
    from pp_mcare.media import SourceVideoMetadata

    stream = FakePoseStream([_frame(index, (_person(),)) for index in range(3)])
    pipeline = _install_pipeline_fakes(monkeypatch, stream, RecordingPlugin())
    monkeypatch.setattr(
        pipeline,
        "probe_source_video",
        lambda path: SourceVideoMetadata(
            width=80,
            height=60,
            fps=25.0,
            frame_count=3,
            duration_seconds=10.0,
            codec_name="h264",
        ),
    )

    with pytest.raises(pipeline.LocalPipelineError, match="输入视频时长"):
        pipeline.run_local_pipeline(
            _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", lambda stage: None
        )

    encoder = FakeEncoder.instances[0]
    assert encoder.finished is True
    assert encoder.committed is False
    assert encoder.aborted is True


def test_pipeline_rejects_vfr_duration_drift_instead_of_using_encoded_frames_as_truth(
    monkeypatch, tmp_path
):
    from pp_mcare.media import SourceVideoMetadata

    stream = FakePoseStream([_frame(index, (_person(),)) for index in range(100)])
    pipeline = _install_pipeline_fakes(monkeypatch, stream, RecordingPlugin())
    monkeypatch.setattr(
        pipeline,
        "probe_source_video",
        lambda path: SourceVideoMetadata(
            width=80,
            height=60,
            fps=25.0,
            frame_count=100,
            duration_seconds=6.0,
            codec_name="h264",
        ),
    )

    with pytest.raises(pipeline.LocalPipelineError, match="输入视频时长"):
        pipeline.run_local_pipeline(
            _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", lambda stage: None
        )


@pytest.mark.parametrize("when", ["before_consumption", "after_consumption"])
def test_pipeline_action_frames_are_explicitly_one_shot(monkeypatch, tmp_path, when):
    stream = FakePoseStream([_frame(0, (_person(),))])

    class DoubleIterPlugin(RecordingPlugin):
        def analyze(self, frames):
            first = iter(frames)
            if when == "before_consumption":
                iter(frames)
            list(first)
            if when == "after_consumption":
                iter(frames)
            raise AssertionError("第二次 iter 必须先失败")

    pipeline = _install_pipeline_fakes(monkeypatch, stream, DoubleIterPlugin())

    with pytest.raises(pipeline.LocalPipelineError, match="只能迭代一次"):
        pipeline.run_local_pipeline(
            _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", lambda stage: None
        )
    assert stream.closed is True
    if FakeEncoder.instances:
        assert FakeEncoder.instances[0].aborted is True


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_pipeline_aborts_committed_media_on_base_exception_before_return(
    monkeypatch, tmp_path, interruption
):
    stream = FakePoseStream([_frame(0, (_person(),))])
    pipeline = _install_pipeline_fakes(monkeypatch, stream, RecordingPlugin())

    class CommitThenInterruptEncoder(FakeEncoder):
        def commit(self):
            super().commit()
            raise interruption

    monkeypatch.setattr(pipeline, "SkeletonVideoEncoder", CommitThenInterruptEncoder)

    with pytest.raises(interruption):
        pipeline.run_local_pipeline(
            _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", lambda stage: None
        )

    encoder = CommitThenInterruptEncoder.instances[-1]
    assert encoder.committed is True
    assert encoder.aborted is True
    assert stream.closed is True


def test_local_result_exports_independent_json_and_builds_shared_completion_payload(
    monkeypatch, tmp_path
):
    from pp_mcare.actions.shoulder_press_v2 import ShoulderPressV2Plugin

    stream = FakePoseStream([_frame(index, (_person(),)) for index in range(3)])
    pipeline = _install_pipeline_fakes(monkeypatch, stream, ShoulderPressV2Plugin())
    job = _job()
    result = pipeline.run_local_pipeline(
        job, tmp_path / "input.mp4", tmp_path / "output.mp4", lambda stage: None
    )
    skeleton = SkeletonArtifact(
        bucket=job.upload.bucket,
        object_key=job.upload.object_key,
        object_hash="dummy-hash",
        size_bytes=123,
        duration_seconds=result.media_metadata.duration_seconds,
        width=result.media_metadata.width,
        height=result.media_metadata.height,
        fps=result.media_metadata.fps,
        content_type="video/mp4",
    )

    first = result.result_payload_json()
    second = result.result_payload_json()
    first_quality = result.quality_summary_json()
    second_quality = result.quality_summary_json()
    first["quality_flags"].append("mutation")
    first_quality["quality_flags"].append("mutation")
    completion = result.to_completion_payload(
        job=job,
        skeleton=skeleton,
        idempotency_key="task-10-test",
    )

    assert isinstance(completion, CompletionPayload)
    assert "mutation" not in second["quality_flags"]
    assert "mutation" not in second_quality["quality_flags"]
    assert completion.algorithm_version == job.algorithm_version
    assert completion.quality_summary == result.quality_summary_json()
    assert "observation_fingerprint" not in repr(completion.to_dict())


def test_pipeline_validates_completion_compatibility_before_media_commit(monkeypatch, tmp_path):
    stream = FakePoseStream([_frame(0, (_person(),))])
    pipeline = _install_pipeline_fakes(monkeypatch, stream, RecordingPlugin())

    def incompatible(self, **kwargs):
        raise RuntimeError("completion incompatible")

    monkeypatch.setattr(pipeline.LocalAnalysisResult, "to_completion_payload", incompatible)

    with pytest.raises(RuntimeError, match="completion incompatible"):
        pipeline.run_local_pipeline(
            _job(), tmp_path / "input.mp4", tmp_path / "output.mp4", lambda stage: None
        )

    encoder = FakeEncoder.instances[0]
    assert encoder.finished is True
    assert encoder.committed is False
    assert encoder.aborted is True
