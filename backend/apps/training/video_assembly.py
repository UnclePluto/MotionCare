import json
import math
import os
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from django.core.exceptions import ValidationError


_STDERR_LIMIT = 2000


@dataclass(frozen=True)
class VideoProbe:
    duration_seconds: float
    width: int
    height: int
    video_codec: str
    audio_codec: str | None
    video_profile: str = ""
    video_level: int = 0
    pixel_format: str = ""
    frame_rate: str = ""
    time_base: str = ""
    audio_sample_rate: int | None = None
    audio_channel_layout: str | None = None


@dataclass(frozen=True)
class AssemblyResult:
    output_path: Path
    probe: VideoProbe
    size_bytes: int
    transcoded: bool


Runner = Callable[..., subprocess.CompletedProcess[str]]
Clock = Callable[[], float]
ProgressCallback = Callable[[], None]


def _stderr_excerpt(error: BaseException) -> str:
    stderr = getattr(error, "stderr", None)
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    detail = str(stderr or error).strip()
    if len(detail) > _STDERR_LIMIT:
        detail = f"{detail[:_STDERR_LIMIT]}..."
    return detail


def _run_command(
    command: list[str], *, timeout: int, runner: Runner, command_name: str
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValidationError(f"{command_name} 执行失败：{_stderr_excerpt(exc)}") from exc


def probe_video(
    path: Path,
    *,
    ffprobe_path: str,
    timeout: int,
    runner: Runner = subprocess.run,
) -> VideoProbe:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValidationError("训练视频文件不存在或不是普通文件")

    completed = _run_command(
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
        timeout=timeout,
        runner=runner,
        command_name="FFprobe",
    )
    try:
        payload = json.loads(completed.stdout)
        streams = payload["streams"]
        video_stream = next(stream for stream in streams if stream.get("codec_type") == "video")
        audio_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "audio"), None
        )
        duration_seconds = float(payload["format"]["duration"])
        width = int(video_stream["width"])
        height = int(video_stream["height"])
        video_codec = str(video_stream["codec_name"])
        audio_codec = None if audio_stream is None else str(audio_stream["codec_name"])
        video_profile = str(video_stream.get("profile") or "")
        video_level = int(video_stream.get("level") or 0)
        pixel_format = str(video_stream.get("pix_fmt") or "")
        frame_rate = str(video_stream.get("avg_frame_rate") or "")
        time_base = str(video_stream.get("time_base") or "")
        audio_sample_rate = (
            None
            if audio_stream is None or not audio_stream.get("sample_rate")
            else int(audio_stream["sample_rate"])
        )
        audio_channel_layout = (
            None
            if audio_stream is None
            else str(audio_stream.get("channel_layout") or "")
        )
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValidationError("FFprobe 返回的训练视频元数据无效") from exc

    if (
        not math.isfinite(duration_seconds)
        or duration_seconds <= 0
        or width <= 0
        or height <= 0
        or not video_codec
    ):
        raise ValidationError("FFprobe 返回的训练视频元数据无效")
    return VideoProbe(
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        video_codec=video_codec,
        audio_codec=audio_codec,
        video_profile=video_profile,
        video_level=video_level,
        pixel_format=pixel_format,
        frame_rate=frame_rate,
        time_base=time_base,
        audio_sample_rate=audio_sample_rate,
        audio_channel_layout=audio_channel_layout,
    )


def _concat_entry(path: Path) -> str:
    escaped_path = str(path).replace("'", r"'\''")
    return f"file '{escaped_path}'\n"


def _validate_segment_paths(segment_paths: list[Path], output_path: Path) -> list[Path]:
    if not segment_paths:
        raise ValidationError("训练视频分段不能为空")

    resolved_output = output_path.resolve()
    resolved_segments = []
    for raw_path in segment_paths:
        path = Path(raw_path)
        if path.is_symlink() or not path.is_file():
            raise ValidationError("训练视频分段不存在或不是普通文件")
        resolved_path = path.resolve()
        if resolved_path == resolved_output:
            raise ValidationError("训练视频输出路径不能与分段相同")
        resolved_segments.append(resolved_path)
    return resolved_segments


def _duration_is_valid(*, actual: float, expected: float) -> bool:
    return abs(actual - expected) <= max(2.0, expected * 0.02)


def _remaining_timeout(deadline: float, monotonic: Clock) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise ValidationError("训练视频合并整体处理超时")
    return remaining


def _progress(on_progress: ProgressCallback | None) -> None:
    if on_progress is not None:
        on_progress()


def _copy_is_safe(input_probes: list[VideoProbe]) -> bool:
    first = input_probes[0]

    def normalized_rate(value: str) -> Fraction | None:
        try:
            rate = Fraction(value)
        except (ValueError, ZeroDivisionError):
            return None
        return rate if rate > 0 else None

    def browser_safe_h264(probe: VideoProbe) -> bool:
        return (
            probe.video_codec == "h264"
            and probe.video_profile
            in {"Baseline", "Constrained Baseline", "Main", "High"}
            and 0 < probe.video_level <= 42
            and probe.pixel_format == "yuv420p"
            and normalized_rate(probe.frame_rate) is not None
            and normalized_rate(probe.time_base) is not None
        )

    if not browser_safe_h264(first):
        return False
    if any(
        not browser_safe_h264(probe)
        or probe.width != first.width
        or probe.height != first.height
        or probe.video_profile != first.video_profile
        or probe.video_level != first.video_level
        or probe.pixel_format != first.pixel_format
        or normalized_rate(probe.frame_rate) != normalized_rate(first.frame_rate)
        or normalized_rate(probe.time_base) != normalized_rate(first.time_base)
        for probe in input_probes
    ):
        return False
    audio_codecs = {probe.audio_codec for probe in input_probes}
    if audio_codecs == {None}:
        return True
    if audio_codecs != {"aac"}:
        return False
    return all(
        probe.audio_sample_rate == first.audio_sample_rate
        and probe.audio_sample_rate in {44100, 48000}
        and probe.audio_channel_layout == first.audio_channel_layout
        and probe.audio_channel_layout in {"mono", "stereo"}
        for probe in input_probes
    )


def _secure_create_file(path: Path) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ValidationError("训练视频合并临时文件无法安全创建") from exc
    try:
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


def _secure_write_text(path: Path, value: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ValidationError("训练视频合并清单无法安全创建") from exc
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as output:
            output.write(value)
    finally:
        os.close(descriptor)


def _safe_unlink(path: Path) -> None:
    try:
        if path.is_symlink():
            raise ValidationError("训练视频合并临时文件不能是符号链接")
        path.unlink()
    except FileNotFoundError:
        return


def _run_assembly_attempt(
    *,
    command: list[str],
    command_name: str,
    temporary_output: Path,
    expected_duration: float,
    ffmpeg_path: str,
    ffprobe_path: str,
    deadline: float,
    runner: Runner,
    monotonic: Clock,
    on_progress: ProgressCallback | None,
) -> VideoProbe:
    _progress(on_progress)
    _run_command(
        command,
        timeout=_remaining_timeout(deadline, monotonic),
        runner=runner,
        command_name=command_name,
    )
    _progress(on_progress)
    output_probe = probe_video(
        temporary_output,
        ffprobe_path=ffprobe_path,
        timeout=_remaining_timeout(deadline, monotonic),
        runner=runner,
    )
    _progress(on_progress)
    if not _duration_is_valid(
        actual=output_probe.duration_seconds,
        expected=expected_duration,
    ):
        raise ValidationError("合并后训练视频时长与分段时长不一致")
    if not _copy_is_safe([output_probe]):
        raise ValidationError("合并后训练视频编码不受支持")
    _run_command(
        [
            ffmpeg_path,
            "-xerror",
            "-v",
            "error",
            "-i",
            str(temporary_output),
            "-map",
            "0:v",
            "-map",
            "0:a?",
            "-f",
            "null",
            "-",
        ],
        timeout=_remaining_timeout(deadline, monotonic),
        runner=runner,
        command_name="FFmpeg 完整解码验证",
    )
    _progress(on_progress)
    return output_probe


def assemble_video(
    segment_paths: list[Path],
    output_path: Path,
    *,
    ffmpeg_path: str,
    ffprobe_path: str,
    timeout: int,
    runner: Runner = subprocess.run,
    monotonic: Clock = time.monotonic,
    on_progress: ProgressCallback | None = None,
) -> AssemblyResult:
    if timeout <= 0:
        raise ValidationError("训练视频合并超时配置无效")
    deadline = monotonic() + timeout
    output_path = Path(output_path)
    segments = _validate_segment_paths(segment_paths, output_path)
    _progress(on_progress)
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output_path.parent.is_symlink():
        raise ValidationError("训练视频输出目录不能是符号链接")
    work_id = uuid.uuid4().hex
    temporary_output = output_path.with_name(f"{output_path.stem}.{work_id}.tmp.mp4")
    concat_path = output_path.parent / f"concat.{work_id}.txt"
    input_probes = []
    for path in segments:
        _progress(on_progress)
        input_probes.append(
            probe_video(
                path,
                ffprobe_path=ffprobe_path,
                timeout=_remaining_timeout(deadline, monotonic),
                runner=runner,
            )
        )
        _progress(on_progress)
    expected_duration = sum(probe.duration_seconds for probe in input_probes)

    try:
        _progress(on_progress)
        _secure_write_text(
            concat_path,
            "".join(_concat_entry(path) for path in segments),
        )
        copy_command = [
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temporary_output),
        ]
        transcode_command = [
            ffmpeg_path,
            "-y",
            "-xerror",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(temporary_output),
        ]
        transcoded = not _copy_is_safe(input_probes)
        _progress(on_progress)
        _secure_create_file(temporary_output)
        if not transcoded:
            try:
                output_probe = _run_assembly_attempt(
                    command=copy_command,
                    command_name="FFmpeg 无损合并",
                    temporary_output=temporary_output,
                    expected_duration=expected_duration,
                    ffmpeg_path=ffmpeg_path,
                    ffprobe_path=ffprobe_path,
                    deadline=deadline,
                    runner=runner,
                    monotonic=monotonic,
                    on_progress=on_progress,
                )
            except ValidationError:
                _progress(on_progress)
                _safe_unlink(temporary_output)
                _secure_create_file(temporary_output)
                transcoded = True
        if transcoded:
            output_probe = _run_assembly_attempt(
                command=transcode_command,
                command_name="FFmpeg 转码合并",
                temporary_output=temporary_output,
                expected_duration=expected_duration,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
                deadline=deadline,
                runner=runner,
                monotonic=monotonic,
                on_progress=on_progress,
            )

        _progress(on_progress)
        if output_path.is_symlink():
            raise ValidationError("训练视频最终输出不能是符号链接")
        os.replace(temporary_output, output_path)
        os.chmod(output_path, 0o600, follow_symlinks=False)
        return AssemblyResult(
            output_path=output_path,
            probe=output_probe,
            size_bytes=output_path.stat().st_size,
            transcoded=transcoded,
        )
    except Exception:
        _safe_unlink(temporary_output)
        raise
    finally:
        _safe_unlink(concat_path)
