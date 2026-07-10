import shutil
import subprocess
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError

from apps.training import video_assembly
from apps.training.video_assembly import VideoProbe, assemble_video, probe_video


def _probe(*, duration_seconds=1.0):
    return VideoProbe(
        duration_seconds=duration_seconds,
        width=640,
        height=480,
        video_codec="h264",
        audio_codec="aac",
    )


def _segment_paths(tmp_path, count=2):
    paths = []
    for index in range(count):
        path = tmp_path / f"{index:06d}.mp4"
        path.write_bytes(b"segment")
        paths.append(path)
    return paths


def test_assemble_video_falls_back_to_one_transcode(tmp_path, monkeypatch):
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if "copy" in command:
            raise subprocess.CalledProcessError(1, command, stderr="bad timestamps")
        Path(command[-1]).write_bytes(b"merged")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(video_assembly, "probe_video", lambda *args, **kwargs: _probe())

    result = assemble_video(
        _segment_paths(tmp_path),
        tmp_path / "final.mp4",
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        timeout=30,
        runner=runner,
    )

    assert result.transcoded is True
    assert sum("libx264" in command for command in calls) == 1
    assert calls[0][0] == "ffmpeg"
    assert "-c" in calls[0]
    assert "copy" in calls[0]
    assert "-safe" in calls[0]
    assert result.output_path == tmp_path / "final.mp4"
    assert result.size_bytes == len(b"merged")


def test_assemble_video_rejects_invalid_segment_paths(tmp_path):
    missing = tmp_path / "missing.mp4"

    with pytest.raises(ValidationError, match="分段"):
        assemble_video(
            [missing],
            tmp_path / "final.mp4",
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
            timeout=30,
        )


def test_assemble_video_rejects_symlinked_segment(tmp_path):
    target = tmp_path / "target.mp4"
    target.write_bytes(b"segment")
    symlink = tmp_path / "linked.mp4"
    symlink.symlink_to(target)

    with pytest.raises(ValidationError, match="分段"):
        assemble_video(
            [symlink],
            tmp_path / "final.mp4",
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
            timeout=30,
        )


def test_assemble_video_rejects_duration_mismatch_without_final_output(tmp_path, monkeypatch):
    def runner(command, **kwargs):
        Path(command[-1]).write_bytes(b"merged")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    probes = iter([_probe(duration_seconds=3.0), _probe(duration_seconds=3.0), _probe()])
    monkeypatch.setattr(video_assembly, "probe_video", lambda *args, **kwargs: next(probes))

    with pytest.raises(ValidationError, match="时长"):
        assemble_video(
            _segment_paths(tmp_path),
            tmp_path / "final.mp4",
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
            timeout=30,
            runner=runner,
        )

    assert not (tmp_path / "final.mp4").exists()
    assert not (tmp_path / "final.tmp.mp4").exists()


def test_probe_video_parses_ffprobe_json(tmp_path):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"video")

    def runner(command, **kwargs):
        assert command == [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
        assert kwargs == {
            "check": True,
            "capture_output": True,
            "text": True,
            "timeout": 30,
        }
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"streams":[{"codec_type":"video","codec_name":"h264",'
                '"width":640,"height":480},{"codec_type":"audio",'
                '"codec_name":"aac"}],"format":{"duration":"1.25"}}'
            ),
            stderr="",
        )

    assert probe_video(path, ffprobe_path="ffprobe", timeout=30, runner=runner) == VideoProbe(
        duration_seconds=1.25,
        width=640,
        height=480,
        video_codec="h264",
        audio_codec="aac",
    )


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required")
def test_assemble_video_merges_twenty_three_real_h264_aac_segments(tmp_path):
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    assert ffmpeg_path is not None
    assert ffprobe_path is not None

    segment_paths = []
    for index in range(23):
        segment_path = tmp_path / f"{index:06d}.mp4"
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=160x120:r=10:d=0.1",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:sample_rate=44100:duration=0.1",
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(segment_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        segment_paths.append(segment_path)

    result = assemble_video(
        segment_paths,
        tmp_path / "final.mp4",
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
        timeout=30,
    )

    assert result.output_path.is_file()
    assert result.probe.video_codec == "h264"
    assert result.probe.duration_seconds > 2.0
