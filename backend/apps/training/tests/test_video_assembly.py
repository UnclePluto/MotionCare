import shutil
import subprocess
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError

from apps.training import video_assembly
from apps.training.video_assembly import VideoProbe, assemble_video, probe_video


def _probe(
    *,
    duration_seconds=1.0,
    width=640,
    height=480,
    video_codec="h264",
    audio_codec="aac",
    video_profile="High",
    video_level=31,
    pixel_format="yuv420p",
    frame_rate="30/1",
    time_base="1/15360",
    audio_sample_rate=48000,
    audio_channel_layout="stereo",
):
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
        audio_sample_rate=audio_sample_rate if audio_codec else None,
        audio_channel_layout=audio_channel_layout if audio_codec else None,
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
        if command[-1] != "-":
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
    assert sum(command[-2:] == ["null", "-"] for command in calls) == 1


@pytest.mark.parametrize(
    "input_probes",
    [
        [_probe(), _probe(width=1280)],
        [_probe(), _probe(video_codec="hevc")],
        [_probe(), _probe(audio_codec=None)],
        [_probe(audio_codec="mp3"), _probe(audio_codec="mp3")],
        [_probe(), _probe(video_profile="Main")],
        [_probe(), _probe(video_level=32)],
        [_probe(), _probe(pixel_format="yuv444p")],
        [_probe(), _probe(frame_rate="30000/1001")],
        [_probe(), _probe(time_base="1/90000")],
        [_probe(), _probe(audio_sample_rate=44100)],
        [_probe(), _probe(audio_channel_layout="mono")],
    ],
)
def test_assemble_video_transcodes_incompatible_inputs_without_trying_copy(
    tmp_path, monkeypatch, input_probes
):
    calls = []
    probes = iter([*input_probes, _probe(duration_seconds=2.0)])
    monkeypatch.setattr(
        video_assembly,
        "probe_video",
        lambda *args, **kwargs: next(probes),
    )

    def runner(command, **kwargs):
        calls.append(command)
        if command[-1] != "-":
            Path(command[-1]).write_bytes(b"merged")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = assemble_video(
        _segment_paths(tmp_path),
        tmp_path / "final.mp4",
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        timeout=30,
        runner=runner,
    )

    assert result.transcoded is True
    assert sum("copy" in command for command in calls) == 0
    assert sum("libx264" in command for command in calls) == 1
    assert sum(command[-2:] == ["null", "-"] for command in calls) == 1


def test_assemble_video_rejects_output_that_cannot_be_fully_decoded(
    tmp_path, monkeypatch
):
    calls = []
    probes = iter([
        _probe(),
        _probe(),
        _probe(duration_seconds=2.0),
        _probe(duration_seconds=2.0),
    ])
    monkeypatch.setattr(
        video_assembly,
        "probe_video",
        lambda *args, **kwargs: next(probes),
    )

    def runner(command, **kwargs):
        calls.append(command)
        if command[-2:] == ["null", "-"]:
            raise subprocess.CalledProcessError(1, command, stderr="decode failed")
        Path(command[-1]).write_bytes(b"merged")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with pytest.raises(ValidationError, match="解码验证"):
        assemble_video(
            _segment_paths(tmp_path),
            tmp_path / "final.mp4",
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
            timeout=30,
            runner=runner,
        )

    decode_commands = [command for command in calls if command[-2:] == ["null", "-"]]
    assert decode_commands
    assert all("-xerror" in command for command in decode_commands)

    assert not (tmp_path / "final.mp4").exists()


def test_assemble_video_uses_one_monotonic_deadline_and_reports_stage_progress(
    tmp_path,
):
    now = [100.0]
    timeouts = []
    progress = []

    def monotonic():
        return now[0]

    def runner(command, **kwargs):
        timeouts.append(kwargs["timeout"])
        now[0] += 4.0
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                    stdout=(
                        '{"streams":[{"codec_type":"video","codec_name":"h264",'
                        '"width":640,"height":480,"profile":"High","level":31,'
                        '"pix_fmt":"yuv420p","avg_frame_rate":"30/1",'
                        '"time_base":"1/15360"},{"codec_type":"audio",'
                        '"codec_name":"aac","sample_rate":"48000",'
                        '"channel_layout":"stereo"}],"format":{"duration":"1.0"}}'
                    ),
                stderr="",
            )
        if command[-1] != "-":
            Path(command[-1]).write_bytes(b"merged")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with pytest.raises(ValidationError, match="整体处理超时"):
        assemble_video(
            _segment_paths(tmp_path),
            tmp_path / "final.mp4",
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
            timeout=10,
            runner=runner,
            monotonic=monotonic,
            on_progress=lambda: progress.append(now[0]),
        )

    assert timeouts == sorted(timeouts, reverse=True)
    assert timeouts[0] <= 10
    assert len(progress) >= 2


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

    probes = iter([
        _probe(duration_seconds=3.0),
        _probe(duration_seconds=3.0),
        _probe(),
        _probe(),
    ])
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
                '"width":640,"height":480,"profile":"High","level":31,'
                '"pix_fmt":"yuv420p","avg_frame_rate":"30/1",'
                '"time_base":"1/15360"},{"codec_type":"audio",'
                '"codec_name":"aac","sample_rate":"48000",'
                '"channel_layout":"stereo"}],"format":{"duration":"1.25"}}'
            ),
            stderr="",
        )

    assert probe_video(path, ffprobe_path="ffprobe", timeout=30, runner=runner) == VideoProbe(
        duration_seconds=1.25,
        width=640,
        height=480,
        video_codec="h264",
        audio_codec="aac",
        video_profile="High",
        video_level=31,
        pixel_format="yuv420p",
        frame_rate="30/1",
        time_base="1/15360",
        audio_sample_rate=48000,
        audio_channel_layout="stereo",
    )


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required")
def test_assemble_video_rejects_real_probeable_but_corrupted_h264(tmp_path):
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    assert ffmpeg_path is not None
    assert ffprobe_path is not None
    corrupted = tmp_path / "corrupted.mp4"
    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=30:duration=3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "30",
            "-movflags",
            "+faststart",
            str(corrupted),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = bytearray(corrupted.read_bytes())
    mdat = payload.find(b"mdat")
    assert mdat > 0
    corrupt_start = mdat + 8 + len(payload[mdat + 8 :]) // 3
    for index in range(corrupt_start, min(corrupt_start + 5000, len(payload))):
        payload[index] ^= 0xFF
    corrupted.write_bytes(payload)
    probe_video(corrupted, ffprobe_path=ffprobe_path, timeout=30)

    with pytest.raises(ValidationError):
        assemble_video(
            [corrupted],
            tmp_path / "final.mp4",
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            timeout=30,
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
