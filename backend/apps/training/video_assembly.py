import json
import math
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class AssemblyResult:
    output_path: Path
    probe: VideoProbe
    size_bytes: int
    transcoded: bool


Runner = Callable[..., subprocess.CompletedProcess[str]]


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
    if not path.is_file():
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


def assemble_video(
    segment_paths: list[Path],
    output_path: Path,
    *,
    ffmpeg_path: str,
    ffprobe_path: str,
    timeout: int,
    runner: Runner = subprocess.run,
) -> AssemblyResult:
    output_path = Path(output_path)
    segments = _validate_segment_paths(segment_paths, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output_path.with_name(
        f"{output_path.stem}.tmp{output_path.suffix}"
    )
    concat_path = output_path.parent / "concat.txt"
    input_probes = [
        probe_video(path, ffprobe_path=ffprobe_path, timeout=timeout, runner=runner)
        for path in segments
    ]
    expected_duration = sum(probe.duration_seconds for probe in input_probes)

    try:
        concat_path.write_text("".join(_concat_entry(path) for path in segments), encoding="utf-8")
        temporary_output.unlink(missing_ok=True)
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
        try:
            _run_command(
                copy_command,
                timeout=timeout,
                runner=runner,
                command_name="FFmpeg 无损合并",
            )
            output_probe = probe_video(
                temporary_output,
                ffprobe_path=ffprobe_path,
                timeout=timeout,
                runner=runner,
            )
            transcoded = False
        except ValidationError:
            temporary_output.unlink(missing_ok=True)
            transcode_command = [
                ffmpeg_path,
                "-y",
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
            _run_command(
                transcode_command,
                timeout=timeout,
                runner=runner,
                command_name="FFmpeg 转码合并",
            )
            output_probe = probe_video(
                temporary_output,
                ffprobe_path=ffprobe_path,
                timeout=timeout,
                runner=runner,
            )
            transcoded = True

        if not _duration_is_valid(
            actual=output_probe.duration_seconds,
            expected=expected_duration,
        ):
            raise ValidationError("合并后训练视频时长与分段时长不一致")

        os.replace(temporary_output, output_path)
        return AssemblyResult(
            output_path=output_path,
            probe=output_probe,
            size_bytes=output_path.stat().st_size,
            transcoded=transcoded,
        )
    except Exception:
        temporary_output.unlink(missing_ok=True)
        raise
    finally:
        concat_path.unlink(missing_ok=True)
