from __future__ import annotations

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


class SkeletonVideoEncoder:
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
        descriptor = os.open(self._partial_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        self._stderr = tempfile.TemporaryFile(mode="w+b")
        self._frame_count = 0
        self._closed = False
        self._published = False
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
        try:
            self._process = _start_ffmpeg(command, self._stderr)
        except Exception as exc:
            self._cleanup_files()
            self._stderr.close()
            raise MediaEncodingError("无法启动 ffmpeg") from exc

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def write(self, frame) -> None:
        if self._failure is not None:
            raise self._failure
        if self._closed:
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

    def close(self) -> VideoMetadata:
        if self._failure is not None:
            raise self._failure
        if self._closed:
            if self.metadata is None:
                raise MediaEncodingError("骨架编码器未产出媒体")
            return self.metadata
        if self._frame_count == 0:
            self._fail("骨架视频没有帧")
            raise self._failure
        try:
            if self._process.stdin is not None:
                self._process.stdin.close()
            return_code = self._process.wait()
        except Exception as exc:
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
            os.replace(self._partial_path, self.path)
            self._published = True
            self.metadata = metadata
            self._closed = True
            self._stderr.close()
            return metadata
        except Exception as exc:
            if isinstance(exc, MediaEncodingError):
                self._fail(str(exc))
            else:
                self._fail("发布骨架视频失败")
            raise self._failure from exc

    def abort(self) -> None:
        if self._closed:
            return
        self._abort_process()
        self._cleanup_files()
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
        self._cleanup_files()
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
            process.wait()
        except (OSError, subprocess.SubprocessError):
            pass

    def _stderr_message(self) -> str:
        try:
            self._stderr.flush()
            self._stderr.seek(0)
            return self._stderr.read(16_384).decode("utf-8", errors="replace").strip()
        except (OSError, ValueError):
            return ""

    def _cleanup_files(self) -> None:
        candidates = [self._partial_path]
        if self._published:
            candidates.append(self.path)
        for candidate in candidates:
            try:
                candidate.unlink(missing_ok=True)
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
