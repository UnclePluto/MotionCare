from __future__ import annotations

import errno
import importlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TypeVar


_CLOCK = time.monotonic

PROBE_SUMMARY_LIMIT_BYTES = 1 * 1024 * 1024
PROBE_TIMELINE_LIMIT_BYTES = 64 * 1024 * 1024
PROBE_STDERR_LIMIT_BYTES = 1 * 1024 * 1024
PROBE_ERROR_SUMMARY_BYTES = 4096
PROBE_TIMELINE_LINE_LIMIT_BYTES = 256
PROBE_TIMEOUT_SECONDS = 3600
PROBE_POLL_SECONDS = 0.05
PROBE_KILL_WAIT_SECONDS = 5
TIMESTAMP_RELATIVE_TOLERANCE = 0.01
TIMESTAMP_ABSOLUTE_TOLERANCE_SECONDS = 0.001
MAX_MISSING_NOMINAL_TICK_RATIO = 0.01


_ProbeResult = TypeVar("_ProbeResult")


class MediaEncodingError(RuntimeError):
    """FFmpeg 编码或输出媒体校验失败。"""


@dataclass(frozen=True)
class VideoMetadata:
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float
    codec_name: str
    pixel_format: str
    has_audio: bool
    faststart: bool
    content_type: str = "video/mp4"

    def __post_init__(self) -> None:
        _positive_int(self.width, "width")
        _positive_int(self.height, "height")
        _positive_float(self.fps, "fps")
        _positive_int(self.frame_count, "frame_count")
        _positive_float(self.duration_seconds, "duration_seconds")
        if not isinstance(self.codec_name, str) or not self.codec_name:
            raise MediaEncodingError("codec_name 必须是非空字符串")
        if not isinstance(self.pixel_format, str) or not self.pixel_format:
            raise MediaEncodingError("pixel_format 必须是非空字符串")
        if not isinstance(self.has_audio, bool) or not isinstance(self.faststart, bool):
            raise MediaEncodingError("媒体布尔属性无效")
        if self.content_type != "video/mp4":
            raise MediaEncodingError("骨架媒体类型必须是 video/mp4")


@dataclass(frozen=True)
class SourceVideoMetadata:
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float
    codec_name: str

    def __post_init__(self) -> None:
        _positive_int(self.width, "width")
        _positive_int(self.height, "height")
        _positive_float(self.fps, "fps")
        _positive_int(self.frame_count, "frame_count")
        _positive_float(self.duration_seconds, "duration_seconds")
        if not isinstance(self.codec_name, str) or not self.codec_name:
            raise MediaEncodingError("codec_name 必须是非空字符串")


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MediaEncodingError(f"{name} 必须是正整数")
    return value


def _positive_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MediaEncodingError(f"{name} 必须是有限正数")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise MediaEncodingError(f"{name} 必须是有限正数")
    return normalized


def _start_ffmpeg(command: list[str], stderr):
    return subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=stderr,
        shell=False,
    )


def _start_ffprobe(
    command: list[str],
    stdout: BinaryIO,
    stderr: BinaryIO,
    *,
    pass_fds: tuple[int, ...] = (),
):
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        shell=False,
        pass_fds=pass_fds,
    )


def _file_size(file: BinaryIO) -> int:
    return os.fstat(file.fileno()).st_size


def _kill_and_wait(process) -> None:
    try:
        if getattr(process, "returncode", None) is None:
            process.kill()
        process.wait(timeout=PROBE_KILL_WAIT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        pass


def _bounded_probe_error(stderr: BinaryIO, redact_paths: tuple[Path, ...]) -> str:
    stderr.seek(0)
    message = stderr.read(PROBE_ERROR_SUMMARY_BYTES).decode("utf-8", errors="replace").strip()
    for path in redact_paths:
        message = message.replace(str(path), "<media>")
    return message[:PROBE_ERROR_SUMMARY_BYTES]


def _run_ffprobe(
    command: list[str],
    *,
    stdout_limit: int,
    stderr_limit: int,
    timeout_seconds: float,
    redact_paths: tuple[Path, ...],
    parser: Callable[[BinaryIO], _ProbeResult],
    pass_fds: tuple[int, ...] = (),
) -> _ProbeResult:
    """Run ffprobe with bounded 0600 files and parse before automatic cleanup."""
    process = None
    with tempfile.TemporaryFile(mode="w+b") as stdout, tempfile.TemporaryFile(mode="w+b") as stderr:
        os.fchmod(stdout.fileno(), 0o600)
        os.fchmod(stderr.fileno(), 0o600)
        try:
            for descriptor in pass_fds:
                os.lseek(descriptor, 0, os.SEEK_SET)
            if pass_fds:
                process = _start_ffprobe(command, stdout, stderr, pass_fds=pass_fds)
            else:
                process = _start_ffprobe(command, stdout, stderr)
            deadline = time.monotonic() + timeout_seconds
            while True:
                if _file_size(stdout) > stdout_limit:
                    raise MediaEncodingError("ffprobe 标准输出超过上限")
                if _file_size(stderr) > stderr_limit:
                    raise MediaEncodingError("ffprobe 错误输出超过上限")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MediaEncodingError("ffprobe 探测超时")
                try:
                    return_code = process.wait(timeout=min(PROBE_POLL_SECONDS, remaining))
                except subprocess.TimeoutExpired:
                    continue
                if _file_size(stdout) > stdout_limit:
                    raise MediaEncodingError("ffprobe 标准输出超过上限")
                if _file_size(stderr) > stderr_limit:
                    raise MediaEncodingError("ffprobe 错误输出超过上限")
                if return_code != 0:
                    detail = _bounded_probe_error(stderr, redact_paths)
                    raise MediaEncodingError(detail or f"ffprobe 探测失败（退出码 {return_code}）")
                stdout.seek(0)
                return parser(stdout)
        except BaseException:
            if process is not None:
                _kill_and_wait(process)
            raise
        finally:
            for descriptor in pass_fds:
                os.lseek(descriptor, 0, os.SEEK_SET)


def _parse_rate(value: object) -> float:
    try:
        numerator, denominator = str(value).split("/", 1)
        rate = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError) as exc:
        raise MediaEncodingError("ffprobe 返回了无效帧率") from exc
    return _positive_float(rate, "输出帧率")


def _display_dimensions(video: dict[str, object]) -> tuple[int, int]:
    width = int(video["width"])
    height = int(video["height"])
    rotations = [
        item.get("rotation")
        for item in video.get("side_data_list", [])
        if isinstance(item, dict) and item.get("rotation") is not None
    ]
    tags = video.get("tags")
    if not rotations and isinstance(tags, dict) and tags.get("rotate") is not None:
        rotations.append(tags["rotate"])
    if len(rotations) > 1:
        raise MediaEncodingError("输入视频包含多个显示旋转信息")
    if not rotations:
        return width, height
    try:
        rotation = float(rotations[0])
    except (TypeError, ValueError) as exc:
        raise MediaEncodingError("输入视频显示旋转信息无效") from exc
    if not math.isfinite(rotation):
        raise MediaEncodingError("输入视频显示旋转信息无效")
    quarter_turns = round(rotation / 90)
    if abs(rotation - quarter_turns * 90) > 0.01:
        raise MediaEncodingError("输入视频显示旋转角度不受支持")
    if quarter_turns % 2:
        return height, width
    return width, height


def _optional_positive_float(value: object) -> float | None:
    try:
        return _positive_float(float(value), "时长")
    except (MediaEncodingError, TypeError, ValueError):
        return None


def _load_probe_json(output: BinaryIO) -> dict[str, object]:
    try:
        payload = json.load(output)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise MediaEncodingError("ffprobe 返回了无效 JSON") from exc
    if not isinstance(payload, dict):
        raise MediaEncodingError("ffprobe JSON 必须是对象")
    return payload


@dataclass(frozen=True)
class _TimelineMetadata:
    frame_count: int
    duration_seconds: float


def _parse_cfr_timeline(output: BinaryIO, *, expected_fps: float) -> _TimelineMetadata:
    nominal_interval = 1.0 / expected_fps
    tolerance = max(
        TIMESTAMP_ABSOLUTE_TOLERANCE_SECONDS,
        nominal_interval * TIMESTAMP_RELATIVE_TOLERANCE,
    )
    first_pts: float | None = None
    previous_pts: float | None = None
    frame_count = 0
    nominal_tick_count = 0
    last_duration: float | None = None
    while True:
        raw_line = output.readline(PROBE_TIMELINE_LINE_LIMIT_BYTES + 1)
        if not raw_line:
            break
        if len(raw_line) > PROBE_TIMELINE_LINE_LIMIT_BYTES:
            raise MediaEncodingError("ffprobe 帧时间戳行超过上限")
        try:
            line = raw_line.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError as exc:
            raise MediaEncodingError("输入视频帧时间戳编码无效") from exc
        if not line:
            continue
        fields = {}
        for item in line.split("|"):
            if "=" in item:
                key, value = item.split("=", 1)
                fields[key] = value
        try:
            pts = float(fields["best_effort_timestamp_time"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MediaEncodingError("输入视频帧时间戳无法可靠验证") from exc
        if not math.isfinite(pts):
            raise MediaEncodingError("输入视频帧时间戳无法可靠验证")
        duration = _optional_positive_float(fields.get("pkt_duration_time"))
        if duration is not None:
            duration_ticks = round(duration / nominal_interval)
            if (
                duration_ticks < 1
                or abs(duration - duration_ticks * nominal_interval) > tolerance
            ):
                raise MediaEncodingError("输入视频帧持续时间不均匀")
        if first_pts is None:
            first_pts = pts
        if previous_pts is not None:
            interval = pts - previous_pts
            interval_ticks = round(interval / nominal_interval)
            if (
                interval_ticks < 1
                or abs(interval - interval_ticks * nominal_interval) > tolerance
            ):
                raise MediaEncodingError("输入视频帧时间戳不均匀")
            nominal_tick_count += interval_ticks
        else:
            nominal_tick_count = 1
        previous_pts = pts
        last_duration = duration
        frame_count += 1
    if frame_count < 2 or first_pts is None or previous_pts is None:
        raise MediaEncodingError("输入视频时间轴无法可靠验证")
    missing_tick_count = nominal_tick_count - frame_count
    if missing_tick_count / nominal_tick_count > MAX_MISSING_NOMINAL_TICK_RATIO:
        raise MediaEncodingError("输入视频缺帧比例过高")
    duration_seconds = previous_pts - first_pts + (last_duration or nominal_interval)
    return _TimelineMetadata(
        frame_count=frame_count,
        duration_seconds=_positive_float(duration_seconds, "输入视频时间轴时长"),
    )


def _has_faststart(path: Path) -> bool:
    """Read only MP4 atom headers; never load a potentially hour-long video into memory."""
    file_size = path.stat().st_size
    offset = 0
    moov_offset: int | None = None
    mdat_offset: int | None = None
    with path.open("rb") as media_file:
        while offset + 8 <= file_size:
            media_file.seek(offset)
            header = media_file.read(8)
            atom_size = int.from_bytes(header[:4], "big")
            atom_type = header[4:8]
            header_size = 8
            if atom_size == 1:
                extended = media_file.read(8)
                if len(extended) != 8:
                    break
                atom_size = int.from_bytes(extended, "big")
                header_size = 16
            elif atom_size == 0:
                atom_size = file_size - offset
            if atom_size < header_size or offset + atom_size > file_size:
                break
            if atom_type == b"moov" and moov_offset is None:
                moov_offset = offset
            elif atom_type == b"mdat" and mdat_offset is None:
                mdat_offset = offset
            if moov_offset is not None and mdat_offset is not None:
                return moov_offset < mdat_offset
            offset += atom_size
    return False


def _probe_video(path: Path) -> VideoMetadata:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise MediaEncodingError("找不到 ffprobe")
    command = [
        ffprobe,
        "-v",
        "error",
        "-count_frames",
        "-show_entries",
        "stream=codec_name,codec_type,pix_fmt,width,height,avg_frame_rate,nb_read_frames:format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        payload = _run_ffprobe(
            command,
            stdout_limit=PROBE_SUMMARY_LIMIT_BYTES,
            stderr_limit=PROBE_STDERR_LIMIT_BYTES,
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
            redact_paths=(path,),
            parser=_load_probe_json,
        )
        streams = payload["streams"]
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if len(video_streams) != 1:
            raise MediaEncodingError("骨架视频必须只有一个视频流")
        video = video_streams[0]
        duration = float(payload["format"]["duration"])
        return VideoMetadata(
            width=int(video["width"]),
            height=int(video["height"]),
            fps=_parse_rate(video["avg_frame_rate"]),
            frame_count=int(video["nb_read_frames"]),
            duration_seconds=_positive_float(duration, "输出时长"),
            codec_name=str(video["codec_name"]),
            pixel_format=str(video["pix_fmt"]),
            has_audio=bool(audio_streams),
            faststart=_has_faststart(path),
        )
    except MediaEncodingError:
        raise
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise MediaEncodingError("骨架视频无法通过 ffprobe 校验") from exc


def probe_source_video(path, *, pass_fds: tuple[int, ...] = ()) -> SourceVideoMetadata:
    """Probe and decode-count the independent input timeline before inference starts."""
    source_path = Path(path)
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise MediaEncodingError("找不到 ffprobe")
    summary_command = [
        ffprobe,
        "-v",
        "error",
        "-count_frames",
        "-show_entries",
        "stream=codec_name,codec_type,width,height,r_frame_rate,avg_frame_rate,nb_read_frames,duration:stream_tags=rotate:stream_side_data=rotation",
        "-of",
        "json",
        str(source_path),
    ]
    timeline_command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "frame=best_effort_timestamp_time,pkt_duration_time",
        "-of",
        "compact=p=0:nk=0",
        str(source_path),
    ]
    try:
        payload = _run_ffprobe(
            summary_command,
            stdout_limit=PROBE_SUMMARY_LIMIT_BYTES,
            stderr_limit=PROBE_STDERR_LIMIT_BYTES,
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
            redact_paths=(source_path,),
            parser=_load_probe_json,
            pass_fds=pass_fds,
        )
        video_streams = [
            stream for stream in payload["streams"] if stream.get("codec_type") == "video"
        ]
        if len(video_streams) != 1:
            raise MediaEncodingError("输入媒体必须只有一个视频流")
        video = video_streams[0]
        average_fps = _parse_rate(video["avg_frame_rate"])
        nominal_fps = _parse_rate(video["r_frame_rate"])
        timeline = _run_ffprobe(
            timeline_command,
            stdout_limit=PROBE_TIMELINE_LIMIT_BYTES,
            stderr_limit=PROBE_STDERR_LIMIT_BYTES,
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
            redact_paths=(source_path,),
            parser=lambda output: _parse_cfr_timeline(output, expected_fps=nominal_fps),
            pass_fds=pass_fds,
        )
        summary_frame_count = int(video["nb_read_frames"])
        if timeline.frame_count != summary_frame_count:
            raise MediaEncodingError("输入视频探测帧数与时间轴帧数不一致")
        stream_duration = _optional_positive_float(video.get("duration"))
        if stream_duration is not None:
            duration_tolerance = max(
                TIMESTAMP_ABSOLUTE_TOLERANCE_SECONDS,
                (1.0 / average_fps) * TIMESTAMP_RELATIVE_TOLERANCE,
            )
            if abs(stream_duration - timeline.duration_seconds) > duration_tolerance:
                raise MediaEncodingError("输入视频流时长与帧时间轴不一致")
            duration_seconds = stream_duration
        else:
            duration_seconds = timeline.duration_seconds
        display_width, display_height = _display_dimensions(video)
        return SourceVideoMetadata(
            width=display_width,
            height=display_height,
            fps=average_fps,
            frame_count=summary_frame_count,
            duration_seconds=duration_seconds,
            codec_name=str(video["codec_name"]),
        )
    except MediaEncodingError:
        raise
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise MediaEncodingError("输入视频无法通过 ffprobe 解码校验") from exc


class SkeletonVideoEncoder:
    """Stream a video inside a private TaskWorkspace and publish once with hardlink.

    A successful ``os.link`` is the irreversible commit point. ``abort`` only cleans the
    private partial; the owning TaskWorkspace must clean a published target after an
    interruption that occurs between that commit point and the caller's successful return.
    """

    FINISH_TIMEOUT_SECONDS = 120

    def __init__(self, path, width, height, fps):
        self.path = Path(path)
        self.width = _positive_int(width, "width")
        self.height = _positive_int(height, "height")
        self.fps = _positive_float(fps, "fps")
        if self.path.exists():
            raise MediaEncodingError("骨架视频目标已存在")
        if not self.path.parent.is_dir():
            raise MediaEncodingError("骨架视频目标目录不存在")
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise MediaEncodingError("找不到 ffmpeg")
        self._partial_path = self.path.with_name(f".{self.path.stem}.{uuid.uuid4().hex}.mp4")
        self._stderr = None
        self._frame_count = 0
        self._closed = False
        self._finished = False
        self._committed = False
        self._partial_cleanup_pending = False
        self._encoding_seconds = 0.0
        self._failure: MediaEncodingError | None = None
        self.metadata: VideoMetadata | None = None
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{self.width}x{self.height}",
            "-r",
            str(self.fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(self._partial_path),
        ]
        descriptor: int | None = None
        try:
            descriptor = os.open(self._partial_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
            descriptor = None
            self._stderr = tempfile.TemporaryFile(mode="w+b")
            self._process = _start_ffmpeg(command, self._stderr)
        except BaseException as exc:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            self._cleanup_partial()
            if self._stderr is not None:
                self._stderr.close()
            if not isinstance(exc, Exception):
                raise
            raise MediaEncodingError("无法启动 ffmpeg") from exc

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def partial_path(self) -> Path:
        return self._partial_path

    @property
    def artifact_size_bytes(self) -> int:
        if not self._finished:
            raise MediaEncodingError("编码尚未完成")
        candidate = self.path if self._committed else self._partial_path
        return candidate.stat().st_size

    @property
    def partial_cleanup_pending(self) -> bool:
        return self._partial_cleanup_pending

    @property
    def encoding_seconds(self) -> float:
        return self._encoding_seconds

    def write(self, frame) -> None:
        if self._failure is not None:
            raise self._failure
        if self._closed or self._finished:
            raise MediaEncodingError("骨架编码器已经关闭")
        try:
            np = importlib.import_module("numpy")
        except ModuleNotFoundError as exc:
            self._fail("骨架编码需要 inference extra 中的 NumPy")
            raise self._failure from exc
        if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8:
            self._fail("骨架帧必须是 uint8 NumPy 数组")
            raise self._failure
        if frame.shape != (self.height, self.width, 3):
            self._fail("骨架帧尺寸与编码器不一致")
            raise self._failure
        if not frame.flags.c_contiguous:
            self._fail("骨架帧必须是连续 BGR 内存")
            raise self._failure
        started = _CLOCK()
        try:
            if self._process.stdin is None:
                raise BrokenPipeError
            self._process.stdin.write(frame.tobytes(order="C"))
        except (BrokenPipeError, OSError) as exc:
            message = self._stderr_message() or "ffmpeg 管道提前关闭"
            self._fail(message)
            raise self._failure from exc
        finally:
            self._encoding_seconds += max(0.0, _CLOCK() - started)
        self._frame_count += 1

    def finish(self) -> VideoMetadata:
        if self._failure is not None:
            raise self._failure
        if self._finished:
            if self.metadata is None:
                raise MediaEncodingError("骨架编码器未产出媒体")
            return self.metadata
        if self._frame_count == 0:
            self._fail("骨架视频没有帧")
            raise self._failure
        started = _CLOCK()
        try:
            if self._process.stdin is not None:
                self._process.stdin.close()
            return_code = self._process.wait(timeout=self.FINISH_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            self._fail("ffmpeg 编码收尾超时")
            raise self._failure from exc
        except BaseException as exc:
            self.abort()
            if not isinstance(exc, Exception):
                raise
            self._fail("等待 ffmpeg 结束失败")
            raise self._failure from exc
        if return_code != 0:
            self._fail(self._stderr_message() or f"ffmpeg 编码失败（退出码 {return_code}）")
            raise self._failure
        try:
            metadata = _probe_video(self._partial_path)
            expected_duration = self._frame_count / self.fps
            tolerance = max(1.0, expected_duration * 0.01)
            if (
                metadata.codec_name != "h264"
                or metadata.pixel_format != "yuv420p"
                or metadata.has_audio
                or not metadata.faststart
                or metadata.width != self.width
                or metadata.height != self.height
                or metadata.frame_count != self._frame_count
                or not math.isclose(metadata.fps, self.fps, rel_tol=0.001, abs_tol=0.001)
                or abs(metadata.duration_seconds - expected_duration) > tolerance
            ):
                raise MediaEncodingError("骨架视频媒体属性不符合协议")
            os.chmod(self._partial_path, 0o600)
            self.metadata = metadata
            self._finished = True
            self._stderr.close()
            return metadata
        except BaseException as exc:
            if not isinstance(exc, Exception):
                self.abort()
                raise
            if isinstance(exc, MediaEncodingError):
                self._fail(str(exc))
            else:
                self._fail("校验骨架视频失败")
            raise self._failure from exc
        finally:
            self._encoding_seconds += max(0.0, _CLOCK() - started)

    def commit(self) -> None:
        if self._failure is not None:
            raise self._failure
        if self._committed:
            return
        if not self._finished or self.metadata is None:
            raise MediaEncodingError("提交前必须先完成编码校验")
        partial_identity = os.stat(self._partial_path, follow_symlinks=False)
        try:
            os.link(self._partial_path, self.path, follow_symlinks=False)
        except FileExistsError as exc:
            self._failure = MediaEncodingError("骨架视频目标已经存在")
            self.abort()
            raise self._failure from exc
        except OSError as exc:
            message = (
                "骨架视频目标已经存在" if exc.errno == errno.EEXIST else "无法原子发布骨架视频"
            )
            self._failure = MediaEncodingError(message)
            self.abort()
            raise self._failure from exc
        target_identity = os.stat(self.path, follow_symlinks=False)
        current_partial_identity = os.stat(self._partial_path, follow_symlinks=False)
        expected_identity = (partial_identity.st_dev, partial_identity.st_ino)
        if (target_identity.st_dev, target_identity.st_ino) != expected_identity or (
            current_partial_identity.st_dev,
            current_partial_identity.st_ino,
        ) != expected_identity:
            self._failure = MediaEncodingError("骨架视频目标在提交后被替换")
            self.abort()
            raise self._failure
        self._committed = True
        self._closed = True
        try:
            self._partial_path.unlink()
        except OSError:
            self._partial_cleanup_pending = True

    def close(self) -> VideoMetadata:
        try:
            metadata = self.finish()
            self.commit()
            return metadata
        except BaseException:
            self.abort()
            raise

    def abort(self) -> None:
        self._abort_process()
        self._cleanup_partial()
        self._closed = True
        stderr = getattr(self, "_stderr", None)
        try:
            if stderr is not None:
                stderr.close()
        except OSError:
            pass

    def _fail(self, message: str) -> None:
        if self._failure is None:
            redacted = message.replace(str(self.path), "<output>").replace(
                str(self._partial_path), "<partial>"
            )
            self._failure = MediaEncodingError(redacted[:2000])
        self._abort_process()
        self._cleanup_partial()
        self._closed = True
        try:
            self._stderr.close()
        except OSError:
            pass

    def _abort_process(self) -> None:
        process = getattr(self, "_process", None)
        if process is None:
            return
        stdin = getattr(process, "stdin", None)
        try:
            if stdin is not None:
                stdin.close()
        except OSError:
            pass
        try:
            if getattr(process, "returncode", None) is None:
                process.kill()
            process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass

    def _stderr_message(self) -> str:
        if self._stderr is None:
            return ""
        try:
            self._stderr.flush()
            self._stderr.seek(0)
            return self._stderr.read(16_384).decode("utf-8", errors="replace").strip()
        except (OSError, ValueError):
            return ""

    def _cleanup_partial(self) -> None:
        try:
            self._partial_path.unlink(missing_ok=True)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self.close()
        else:
            self.abort()
        return False
