from __future__ import annotations

import errno
import importlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path


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


def _parse_rate(value: object) -> float:
    try:
        numerator, denominator = str(value).split("/", 1)
        rate = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError) as exc:
        raise MediaEncodingError("ffprobe 返回了无效帧率") from exc
    return _positive_float(rate, "输出帧率")


def _parse_duration(primary: object, fallback: object) -> float:
    for candidate in (primary, fallback):
        try:
            return _positive_float(float(candidate), "输入时长")
        except (MediaEncodingError, TypeError, ValueError):
            continue
    raise MediaEncodingError("ffprobe 返回了无效输入时长")


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
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-count_frames",
                "-show_entries",
                "stream=codec_name,codec_type,pix_fmt,width,height,avg_frame_rate,nb_read_frames:format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(completed.stdout)
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
        subprocess.SubprocessError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise MediaEncodingError("骨架视频无法通过 ffprobe 校验") from exc


def probe_source_video(path) -> SourceVideoMetadata:
    """Probe and decode-count the independent input timeline before inference starts."""
    source_path = Path(path)
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise MediaEncodingError("找不到 ffprobe")
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-count_frames",
                "-show_entries",
                "stream=codec_name,codec_type,width,height,avg_frame_rate,nb_read_frames,duration:format=duration",
                "-of",
                "json",
                str(source_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        payload = json.loads(completed.stdout)
        video_streams = [
            stream for stream in payload["streams"] if stream.get("codec_type") == "video"
        ]
        if len(video_streams) != 1:
            raise MediaEncodingError("输入媒体必须只有一个视频流")
        video = video_streams[0]
        return SourceVideoMetadata(
            width=int(video["width"]),
            height=int(video["height"]),
            fps=_parse_rate(video["avg_frame_rate"]),
            frame_count=int(video["nb_read_frames"]),
            duration_seconds=_parse_duration(
                video.get("duration"), payload.get("format", {}).get("duration")
            ),
            codec_name=str(video["codec_name"]),
        )
    except MediaEncodingError:
        raise
    except (
        subprocess.SubprocessError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise MediaEncodingError("输入视频无法通过 ffprobe 解码校验") from exc


class SkeletonVideoEncoder:
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
        self._owned_target_identity: tuple[int, int] | None = None
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
        try:
            if self._process.stdin is None:
                raise BrokenPipeError
            self._process.stdin.write(frame.tobytes(order="C"))
        except (BrokenPipeError, OSError) as exc:
            message = self._stderr_message() or "ffmpeg 管道提前关闭"
            self._fail(message)
            raise self._failure from exc
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

    def commit(self) -> None:
        if self._failure is not None:
            raise self._failure
        if self._committed:
            return
        if not self._finished or self.metadata is None:
            raise MediaEncodingError("提交前必须先完成编码校验")
        identity = os.stat(self._partial_path, follow_symlinks=False)
        try:
            os.link(self._partial_path, self.path, follow_symlinks=False)
        except FileExistsError as exc:
            self.abort()
            raise MediaEncodingError("骨架视频目标已经存在") from exc
        except OSError as exc:
            self.abort()
            if exc.errno == errno.EEXIST:
                raise MediaEncodingError("骨架视频目标已经存在") from exc
            raise MediaEncodingError("无法原子发布骨架视频") from exc
        except BaseException:
            self._remove_target_if_identity((identity.st_dev, identity.st_ino))
            raise
        self._owned_target_identity = (identity.st_dev, identity.st_ino)
        try:
            self._partial_path.unlink()
        except BaseException:
            self._remove_owned_target()
            raise
        self._committed = True
        self._closed = True

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
        self._remove_owned_target()
        self._closed = True
        try:
            self._stderr.close()
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
        self._remove_owned_target()
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

    def _remove_owned_target(self) -> None:
        if self._owned_target_identity is None:
            return
        self._remove_target_if_identity(self._owned_target_identity)

    def _remove_target_if_identity(self, identity: tuple[int, int]) -> None:
        try:
            current = os.stat(self.path, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == identity:
                self.path.unlink()
        except FileNotFoundError:
            pass
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
