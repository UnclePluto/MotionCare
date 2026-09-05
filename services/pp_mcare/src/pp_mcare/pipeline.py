from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from motion_analysis_contract import ClaimedJob, MotionCounts, validate_counts

from .actions.base import AnalysisResult
from .media import SkeletonVideoEncoder, VideoMetadata
from .paddle_visualize_pose import render_primary_pose
from .pose_inference import open_full_frame_pose_stream
from .registry import get_action_plugin
from .subject_tracker import PrimarySubjectTracker, SUBJECT_TRACKER_VERSION


class LocalPipelineError(RuntimeError):
    """本地全帧分析流水线违反稳定协议。"""


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class LocalAnalysisResult:
    counts: MotionCounts
    result_payload: Mapping[str, object]
    tracking_summary: Mapping[str, object]
    decoded_frame_count: int
    inferred_frame_count: int
    encoded_frame_count: int
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
        object.__setattr__(self, "result_payload", _freeze(dict(self.result_payload)))
        object.__setattr__(self, "tracking_summary", _freeze(dict(self.tracking_summary)))


def run_local_pipeline(
    job: ClaimedJob,
    input_path,
    output_path,
    heartbeat: Callable[[str], None],
) -> LocalAnalysisResult:
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

    tracker = PrimarySubjectTracker()
    encoder: SkeletonVideoEncoder | None = None
    action_stream_completed = False

    with open_full_frame_pose_stream(input_path) as pose_stream:

        def action_frames():
            nonlocal encoder, action_stream_completed
            for inference_frame in pose_stream:
                heartbeat("inference")
                image = inference_frame.image
                try:
                    height, width = image.shape[:2]
                except (AttributeError, TypeError, ValueError) as exc:
                    raise LocalPipelineError("推理帧尺寸无效") from exc
                if encoder is None:
                    encoder = SkeletonVideoEncoder(
                        output_path,
                        width=width,
                        height=height,
                        fps=pose_stream.source_fps,
                    )
                tracked = tracker.observe(inference_frame)
                if tracked.primary is None:
                    encoded_frame = image
                else:
                    encoded_frame = render_primary_pose(image, tracked.primary)
                encoder.write(encoded_frame)
                action_frame = tracked.to_action_frame()
                if action_frame is not None:
                    yield action_frame
            action_stream_completed = True

        frames = action_frames()
        try:
            analysis = plugin.analyze(frames)
            if not isinstance(analysis, AnalysisResult):
                raise LocalPipelineError("动作插件返回了无效结果")
            if not action_stream_completed:
                raise LocalPipelineError("动作插件必须完整消费全帧生成器")
            tracking_summary = tracker.finish()
            if encoder is None:
                raise LocalPipelineError("训练视频没有可编码帧")
            metadata = encoder.close()
            decoded = pose_stream.decoded_frame_count
            inferred = pose_stream.inferred_frame_count
            encoded = encoder.frame_count
            if not decoded == inferred == encoded:
                raise LocalPipelineError("解码、推理和编码帧数不一致")
            if metadata.frame_count != encoded:
                raise LocalPipelineError("媒体探测帧数与编码帧数不一致")
            expected_duration = encoded / pose_stream.source_fps
            if (
                metadata.codec_name != "h264"
                or metadata.pixel_format != "yuv420p"
                or metadata.has_audio
                or not metadata.faststart
                or metadata.width != encoder.width
                or metadata.height != encoder.height
                or abs(metadata.fps - pose_stream.source_fps) > 0.001
                or abs(metadata.duration_seconds - expected_duration)
                > max(1.0, expected_duration * 0.01)
            ):
                raise LocalPipelineError("骨架媒体属性不符合任务协议")
            payload = analysis.to_json_dict()
            return LocalAnalysisResult(
                counts=analysis.counts,
                result_payload=payload,
                tracking_summary=tracking_summary,
                decoded_frame_count=decoded,
                inferred_frame_count=inferred,
                encoded_frame_count=encoded,
                media_metadata=metadata,
            )
        except Exception:
            if encoder is not None:
                encoder.abort()
            raise
        finally:
            frames.close()
