from __future__ import annotations

import math
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from motion_analysis_contract import (
    ClaimedJob,
    CompletionPayload,
    MotionCounts,
    SkeletonArtifact,
    validate_counts,
)

from .actions.base import AnalysisResult, PoseFrame
from .media import SkeletonVideoEncoder, VideoMetadata, probe_source_video
from .paddle_visualize_pose import render_primary_pose
from .pose_inference import open_full_frame_pose_stream
from .registry import get_action_plugin
from .subject_tracker import PrimarySubjectTracker, SUBJECT_TRACKER_VERSION


_CLOCK = time.monotonic


class LocalPipelineError(RuntimeError):
    """本地全帧分析流水线违反稳定协议。"""


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _json_copy(value: object):
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_copy(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise LocalPipelineError("本地结果包含非 JSON 值")


@dataclass(frozen=True)
class LocalAnalysisResult:
    counts: MotionCounts
    quality_summary: Mapping[str, object]
    result_payload: Mapping[str, object]
    tracking_summary: Mapping[str, object]
    decoded_frame_count: int
    inferred_frame_count: int
    encoded_frame_count: int
    inference_seconds: float
    encoding_seconds: float
    media_metadata: VideoMetadata

    __hash__ = None

    def __post_init__(self) -> None:
        if validate_counts(self.result_payload) != self.counts:
            raise LocalPipelineError("动作计数不满足共享守恒协议")
        if not isinstance(self.media_metadata, VideoMetadata):
            raise TypeError("media_metadata 必须是 VideoMetadata")
        for name in ("decoded_frame_count", "inferred_frame_count", "encoded_frame_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise LocalPipelineError(f"{name} 必须是正整数")
        for name in ("inference_seconds", "encoding_seconds"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise LocalPipelineError(f"{name} 必须是非负有限数值")
        object.__setattr__(self, "quality_summary", _freeze(dict(self.quality_summary)))
        object.__setattr__(self, "result_payload", _freeze(dict(self.result_payload)))
        object.__setattr__(self, "tracking_summary", _freeze(dict(self.tracking_summary)))
        self.quality_summary_json()
        self.result_payload_json()
        self.tracking_summary_json()

    def quality_summary_json(self) -> dict[str, object]:
        exported = _json_copy(self.quality_summary)
        if not isinstance(exported, dict):
            raise LocalPipelineError("质量摘要必须是 JSON 对象")
        return exported

    def result_payload_json(self) -> dict[str, object]:
        exported = _json_copy(self.result_payload)
        if not isinstance(exported, dict):
            raise LocalPipelineError("动作结果必须是 JSON 对象")
        return exported

    def tracking_summary_json(self) -> dict[str, object]:
        exported = _json_copy(self.tracking_summary)
        if not isinstance(exported, dict):
            raise LocalPipelineError("追踪摘要必须是 JSON 对象")
        return exported

    def to_completion_payload(
        self,
        *,
        job: ClaimedJob,
        skeleton: SkeletonArtifact,
        idempotency_key: str,
    ) -> CompletionPayload:
        if not isinstance(job, ClaimedJob):
            raise TypeError("job 必须是 ClaimedJob")
        return CompletionPayload(
            protocol_version=job.protocol_version,
            lease_token=job.lease_token,
            idempotency_key=idempotency_key,
            algorithm_version=job.algorithm_version,
            rule_version=job.rule_version,
            parameter_version=job.parameter_version,
            subject_tracker_version=job.subject_tracker_version,
            counts=self.counts,
            quality_summary=self.quality_summary_json(),
            result_payload=self.result_payload_json(),
            skeleton=skeleton,
        )


class _OneShotActionFrames:
    def __init__(self, iterator: Iterator[PoseFrame]):
        self._iterator = iterator
        self._iterated = False

    def __iter__(self) -> Iterator[PoseFrame]:
        if self._iterated:
            raise LocalPipelineError("动作关键点流只能迭代一次")
        self._iterated = True
        return self._iterator

    def close(self) -> None:
        self._iterator.close()


def _quality_summary(
    analysis: AnalysisResult,
    tracking_summary: Mapping[str, object],
) -> dict[str, object]:
    payload = analysis.to_json_dict()
    return {
        "confidence_level": payload.get("confidence_level", "unknown"),
        "quality_flags": payload.get("quality_flags", []),
        "subject_coverage_ratio": tracking_summary.get("subject_coverage_ratio", 0.0),
        "ambiguity_ratio": tracking_summary.get("ambiguity_ratio", 0.0),
    }


def _dummy_skeleton(job: ClaimedJob, encoder: SkeletonVideoEncoder) -> SkeletonArtifact:
    metadata = encoder.metadata
    if metadata is None:
        raise LocalPipelineError("骨架媒体尚未完成")
    return SkeletonArtifact(
        bucket=job.upload.bucket,
        object_key=job.upload.object_key,
        object_hash="local-validation-only",
        size_bytes=encoder.artifact_size_bytes,
        duration_seconds=metadata.duration_seconds,
        width=metadata.width,
        height=metadata.height,
        fps=metadata.fps,
        content_type=metadata.content_type,
    )


def run_local_pipeline(
    job: ClaimedJob,
    input_path,
    output_path,
    heartbeat: Callable[[str], None],
    *,
    source_metadata=None,
) -> LocalAnalysisResult:
    """Analyze one video whose output lives inside a caller-owned private TaskWorkspace.

    Media commit is irreversible after its no-replace hardlink succeeds. The TaskWorkspace
    owner must remove the whole private workspace after upload, failure, or interruption;
    encoder abort intentionally never unlinks the published output path.
    """
    if not isinstance(job, ClaimedJob):
        raise TypeError("job 必须是 ClaimedJob")
    if not callable(heartbeat):
        raise TypeError("heartbeat 必须可调用")
    if job.subject_tracker_version != SUBJECT_TRACKER_VERSION:
        raise LocalPipelineError("任务要求的主训练者追踪版本不受支持")
    plugin = get_action_plugin(
        job.action_source_key,
        job.algorithm_version,
        job.rule_version,
        job.parameter_version,
    )
    if plugin is None:
        raise LocalPipelineError("任务要求了不支持的动作插件版本")

    source = source_metadata if source_metadata is not None else probe_source_video(input_path)
    tracker = PrimarySubjectTracker()
    encoder: SkeletonVideoEncoder | None = None
    frames: _OneShotActionFrames | None = None
    action_stream_completed = False
    published = False
    render_seconds = 0.0

    try:
        with open_full_frame_pose_stream(input_path) as pose_stream:

            def action_frames() -> Iterator[PoseFrame]:
                nonlocal encoder, action_stream_completed, render_seconds
                for inference_frame in pose_stream:
                    heartbeat("inference")
                    image = inference_frame.image
                    try:
                        height, width = image.shape[:2]
                    except (AttributeError, TypeError, ValueError) as exc:
                        raise LocalPipelineError("推理帧尺寸无效") from exc
                    if encoder is None:
                        if (width, height) != (source.width, source.height):
                            raise LocalPipelineError("解码分辨率与输入媒体探测不一致")
                        if abs(pose_stream.source_fps - source.fps) > 0.001:
                            raise LocalPipelineError("解码帧率与输入媒体探测不一致")
                        encoder = SkeletonVideoEncoder(
                            output_path,
                            width=width,
                            height=height,
                            fps=pose_stream.source_fps,
                        )
                    tracked = tracker.observe(inference_frame)
                    render_started = _CLOCK()
                    encoded_frame = image
                    if tracked.primary is not None:
                        encoded_frame = render_primary_pose(image, tracked.primary)
                    render_seconds += max(0.0, _CLOCK() - render_started)
                    encoder.write(encoded_frame)
                    action_frame = tracked.to_action_frame()
                    if action_frame is not None:
                        yield action_frame
                action_stream_completed = True

            frames = _OneShotActionFrames(action_frames())
            analysis = plugin.analyze(frames)
            if not isinstance(analysis, AnalysisResult):
                raise LocalPipelineError("动作插件返回了无效结果")
            if not action_stream_completed:
                raise LocalPipelineError("动作插件必须完整消费全帧生成器")
            tracking_summary = tracker.finish()
            if encoder is None:
                raise LocalPipelineError("训练视频没有可编码帧")
            metadata = encoder.finish()
            decoded = pose_stream.decoded_frame_count
            inferred = pose_stream.inferred_frame_count
            encoded = encoder.frame_count
            if not decoded == inferred == encoded == source.frame_count:
                raise LocalPipelineError("输入探测、解码、推理和编码帧数不一致")
            if metadata.frame_count != encoded:
                raise LocalPipelineError("媒体探测帧数与编码帧数不一致")
            duration_tolerance = max(1.0, source.duration_seconds * 0.01)
            if (
                metadata.codec_name != "h264"
                or metadata.pixel_format != "yuv420p"
                or metadata.has_audio
                or not metadata.faststart
                or metadata.width != source.width
                or metadata.height != source.height
                or abs(metadata.duration_seconds - source.duration_seconds) > duration_tolerance
            ):
                raise LocalPipelineError("骨架输出与输入视频时长或媒体属性不一致")
            result = LocalAnalysisResult(
                counts=analysis.counts,
                quality_summary=_quality_summary(analysis, tracking_summary),
                result_payload=analysis.to_json_dict(),
                tracking_summary=tracking_summary,
                decoded_frame_count=decoded,
                inferred_frame_count=inferred,
                encoded_frame_count=encoded,
                inference_seconds=pose_stream.inference_seconds,
                encoding_seconds=render_seconds + encoder.encoding_seconds,
                media_metadata=metadata,
            )
            result.to_completion_payload(
                job=job,
                skeleton=_dummy_skeleton(job, encoder),
                idempotency_key=f"local-validation-{job.job_id}",
            )
            frames.close()
            frames = None
            encoder.commit()
            published = True
            return result
    finally:
        try:
            if frames is not None:
                frames.close()
        finally:
            if encoder is not None and (not published or sys.exc_info()[0] is not None):
                encoder.abort()
