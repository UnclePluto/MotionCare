import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import qiniu
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError

from apps.prescriptions.action_library import MOTION_ACTION_VIDEO_OBJECT_KEYS
from apps.training.qiniu import (
    stat_object_metadata_or_none,
    upload_local_video,
    validate_object_metadata,
)


logger = logging.getLogger(__name__)


MOTION_ACTION_VIDEO_SOURCE_PATHS = {
    "motion-aerobic-high-knee": Path("高抬腿+摆臂/高抬腿+摆臂 动作教学.mp4"),
    "motion-balance-sit-stand": Path("坐站转移/坐姿转移 动作教学.mp4"),
    "motion-resistance-row": Path("坐姿划船/坐姿划船 动作教学.mp4"),
    "motion-resistance-leg-kickback": Path("腿部后踢/腿部后踢 动作教学.mp4"),
    "motion-resistance-shoulder-press": Path("肩部推举/动作教学.mp4"),
}


@dataclass(frozen=True)
class MotionAssetProbe:
    codec: str
    audio_codec: str
    width: int
    height: int
    duration_seconds: float
    size_bytes: int


@dataclass(frozen=True)
class UploadedMotionAsset:
    source_key: str
    object_key: str
    size_bytes: int
    status: Literal["existing", "uploaded"]


@dataclass(frozen=True)
class _PreparedMotionAsset:
    source_key: str
    object_key: str
    path: Path
    probe: MotionAssetProbe


def probe_motion_asset(path: Path, ffprobe_path: str) -> MotionAssetProbe:
    path = Path(path)
    try:
        completed = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        payload = json.loads(completed.stdout)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        raise CommandError("正式动作视频无法通过 FFprobe 解析") from exc

    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise CommandError("正式动作视频 FFprobe 输出无效")
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), None
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"), None
    )
    if not isinstance(video_stream, dict) or not isinstance(audio_stream, dict):
        raise CommandError("正式动作视频必须包含视频和音频流")

    try:
        video_codec = str(video_stream["codec_name"])
        audio_codec = str(audio_stream["codec_name"])
        width = int(video_stream["width"])
        height = int(video_stream["height"])
        duration_seconds = float(payload["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CommandError("正式动作视频 FFprobe 输出无效") from exc

    if video_codec != "h264" or audio_codec != "aac":
        raise CommandError("正式动作视频编码必须为 H.264 + AAC")
    if (width, height) != (1080, 1920):
        raise CommandError("正式动作视频尺寸必须为 1080×1920")
    if not 5 <= duration_seconds <= 120:
        raise CommandError("正式动作视频时长必须为 5–120 秒")

    return MotionAssetProbe(
        codec=video_codec,
        audio_codec=audio_codec,
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        size_bytes=path.stat().st_size,
    )


def validate_motion_action_assets(source_root: Path) -> list[_PreparedMotionAsset]:
    source_root = Path(source_root)
    prepared: list[_PreparedMotionAsset] = []
    for source_key, object_key in MOTION_ACTION_VIDEO_OBJECT_KEYS.items():
        path = source_root / MOTION_ACTION_VIDEO_SOURCE_PATHS[source_key]
        if not path.is_file():
            raise CommandError(f"正式动作视频文件不存在：{path}")
        prepared.append(
            _PreparedMotionAsset(
                source_key=source_key,
                object_key=object_key,
                path=path,
                probe=probe_motion_asset(path, ffprobe_path="ffprobe"),
            )
        )
    return prepared


def _local_etag(path: Path) -> str:
    try:
        return qiniu.etag(str(path))
    except OSError as exc:
        raise CommandError("正式动作视频无法计算七牛 Hash") from exc


def _validate_remote_metadata(
    metadata: dict,
    *,
    expected_hash: str,
    expected_size_bytes: int,
) -> None:
    try:
        validate_object_metadata(
            metadata,
            expected_hash=expected_hash,
            expected_size_bytes=expected_size_bytes,
            expected_content_type="video/mp4",
        )
    except ValidationError as exc:
        raise CommandError(str(exc)) from exc


def upload_motion_action_assets(source_root: Path) -> list[UploadedMotionAsset]:
    prepared = validate_motion_action_assets(source_root)
    uploaded: list[UploadedMotionAsset] = []
    for asset in prepared:
        local_hash = _local_etag(asset.path)
        try:
            metadata = stat_object_metadata_or_none(
                bucket=settings.QINIU_BUCKET,
                key=asset.object_key,
            )
            if metadata is not None:
                _validate_remote_metadata(
                    metadata,
                    expected_hash=local_hash,
                    expected_size_bytes=asset.probe.size_bytes,
                )
                status: Literal["existing", "uploaded"] = "existing"
            else:
                upload_local_video(
                    path=asset.path,
                    bucket=settings.QINIU_BUCKET,
                    key=asset.object_key,
                )
                metadata = stat_object_metadata_or_none(
                    bucket=settings.QINIU_BUCKET, key=asset.object_key
                )
                if metadata is None:
                    raise CommandError("正式动作视频上传后无法读取远端对象")
                _validate_remote_metadata(
                    metadata,
                    expected_hash=local_hash,
                    expected_size_bytes=asset.probe.size_bytes,
                )
                status = "uploaded"
        except ValidationError:
            logger.warning("正式动作视频远端对象操作失败")
            raise CommandError("正式动作视频远端对象操作失败") from None
        uploaded.append(
            UploadedMotionAsset(
                source_key=asset.source_key,
                object_key=asset.object_key,
                size_bytes=asset.probe.size_bytes,
                status=status,
            )
        )
    return uploaded
