from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess

import numpy as np
import pytest


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_encoder_produces_two_second_faststart_h264_yuv420p_video_without_audio(tmp_path):
    from pp_mcare.media import SkeletonVideoEncoder

    output = tmp_path / "skeleton;touch PWNED.mp4"
    encoder = SkeletonVideoEncoder(output, width=64, height=48, fps=20.0)
    for index in range(40):
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        frame[:, :, index % 3] = (index * 7) % 255
        encoder.write(frame)
    metadata = encoder.finish()

    assert output.exists() is False
    assert encoder.partial_path.exists() is True

    encoder.commit()

    probe = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=codec_name,codec_type,pix_fmt,width,height,nb_read_frames:format=duration",
            "-of",
            "json",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(probe.stdout)
    video_streams = [item for item in payload["streams"] if item["codec_type"] == "video"]
    audio_streams = [item for item in payload["streams"] if item["codec_type"] == "audio"]
    duration = float(payload["format"]["duration"])

    assert len(video_streams) == 1
    assert audio_streams == []
    assert video_streams[0] == {
        "codec_name": "h264",
        "codec_type": "video",
        "width": 64,
        "height": 48,
        "pix_fmt": "yuv420p",
        "nb_read_frames": "40",
    }
    assert abs(duration - 2.0) <= max(1.0, 2.0 * 0.01)
    data = output.read_bytes()
    assert 0 < data.find(b"moov") < data.find(b"mdat")
    assert metadata.frame_count == 40
    assert metadata.duration_seconds == pytest.approx(duration, abs=0.05)
    assert encoder.close() is metadata
    assert not (tmp_path / "PWNED").exists()


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
@pytest.mark.parametrize(
    ("bad_frame", "message"),
    [
        (np.zeros((48, 64, 3), dtype=np.float32), "uint8"),
        (np.zeros((47, 64, 3), dtype=np.uint8), "尺寸"),
        (np.zeros((48, 64, 3), dtype=np.uint8)[:, ::-1, :], "连续"),
    ],
)
def test_encoder_rejects_bad_frames_and_never_publishes_partial_output(
    tmp_path, bad_frame, message
):
    from pp_mcare.media import MediaEncodingError, SkeletonVideoEncoder

    output = tmp_path / "skeleton.mp4"
    encoder = SkeletonVideoEncoder(output, width=64, height=48, fps=20.0)

    with pytest.raises(MediaEncodingError, match=message):
        encoder.write(bad_frame)

    assert not output.exists()
    encoder.abort()
    encoder.abort()


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_encoder_close_without_frames_is_repeatably_failed_and_leaves_no_artifact(tmp_path):
    from pp_mcare.media import MediaEncodingError, SkeletonVideoEncoder

    output = tmp_path / "empty.mp4"
    encoder = SkeletonVideoEncoder(output, width=64, height=48, fps=20.0)

    with pytest.raises(MediaEncodingError, match="没有帧") as first:
        encoder.close()
    with pytest.raises(MediaEncodingError) as second:
        encoder.close()

    assert str(second.value) == str(first.value)
    assert not output.exists()


@pytest.mark.parametrize(
    ("width", "height", "fps"),
    [(0, 48, 20.0), (64, -1, 20.0), (64, 48, 0), (64, 48, float("nan"))],
)
def test_encoder_rejects_invalid_media_geometry_before_spawning(tmp_path, width, height, fps):
    from pp_mcare.media import MediaEncodingError, SkeletonVideoEncoder

    with pytest.raises(MediaEncodingError):
        SkeletonVideoEncoder(tmp_path / "bad.mp4", width=width, height=height, fps=fps)


def test_encoder_surfaces_broken_pipe_stderr_and_removes_partial_output(tmp_path, monkeypatch):
    from pp_mcare import media

    output = tmp_path / "skeleton.mp4"

    class BrokenStdin:
        def write(self, value):
            raise BrokenPipeError

        def close(self):
            pass

    class FailedProcess:
        stdin = BrokenStdin()
        returncode = 9

        def wait(self, timeout=None):
            return 9

        def kill(self):
            self.returncode = 9

    monkeypatch.setattr(media, "_start_ffmpeg", lambda command, stderr: FailedProcess())
    encoder = media.SkeletonVideoEncoder(output, width=4, height=4, fps=1.0)
    encoder._stderr.write(b"synthetic ffmpeg failure")

    with pytest.raises(media.MediaEncodingError, match="synthetic ffmpeg failure"):
        encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))

    assert not output.exists()
    with pytest.raises(media.MediaEncodingError, match="synthetic ffmpeg failure"):
        encoder.close()


def test_encoder_accumulates_write_and_finish_time_separately(tmp_path, monkeypatch):
    from pp_mcare import media

    class Sink:
        def write(self, _value):
            return None

        def close(self):
            return None

    class Process:
        stdin = Sink()
        returncode = 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(media, "_start_ffmpeg", lambda _command, _stderr: Process())
    monkeypatch.setattr(
        media,
        "_probe_video",
        lambda _path: media.VideoMetadata(4, 4, 1.0, 1, 1.0, "h264", "yuv420p", False, True),
    )
    ticks = iter([1.0, 1.2, 2.0, 2.7])
    monkeypatch.setattr(media, "_CLOCK", lambda: next(ticks), raising=False)
    encoder = media.SkeletonVideoEncoder(tmp_path / "timed.mp4", 4, 4, 1.0)

    encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))
    encoder.finish()

    assert encoder.encoding_seconds == pytest.approx(0.9)
    encoder.abort()


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_encoder_commit_never_clobbers_target_created_after_initialization(tmp_path):
    from pp_mcare.media import MediaEncodingError, SkeletonVideoEncoder

    output = tmp_path / "raced.mp4"
    encoder = SkeletonVideoEncoder(output, width=4, height=4, fps=1.0)
    encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))
    encoder.finish()
    output.write_bytes(b"external-owner")

    with pytest.raises(MediaEncodingError, match="已经存在") as first:
        encoder.commit()
    with pytest.raises(MediaEncodingError) as second:
        encoder.commit()
    encoder.abort()

    assert str(second.value) == str(first.value)
    assert output.read_bytes() == b"external-owner"


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_abort_after_commit_never_removes_published_target(tmp_path):
    from pp_mcare.media import SkeletonVideoEncoder

    output = tmp_path / "committed.mp4"
    encoder = SkeletonVideoEncoder(output, width=4, height=4, fps=1.0)
    encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))
    encoder.finish()
    encoder.commit()
    encoder.abort()

    assert output.exists() is True


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_abort_after_commit_preserves_later_external_replacement(tmp_path):
    from pp_mcare.media import SkeletonVideoEncoder

    output = tmp_path / "owned.mp4"
    encoder = SkeletonVideoEncoder(output, width=4, height=4, fps=1.0)
    encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))
    encoder.finish()
    encoder.commit()
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"external-replacement")
    replacement.replace(output)

    encoder.abort()

    assert output.read_bytes() == b"external-replacement"


def test_encoder_initialization_preserves_base_exception_and_cleans_partial(tmp_path, monkeypatch):
    from pp_mcare import media

    monkeypatch.setattr(
        media,
        "_start_ffmpeg",
        lambda command, stderr: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    with pytest.raises(KeyboardInterrupt):
        media.SkeletonVideoEncoder(tmp_path / "never-started.mp4", 4, 4, 1.0)

    assert list(tmp_path.iterdir()) == []


def test_encoder_finish_timeout_kills_process_and_removes_partial(tmp_path, monkeypatch):
    from pp_mcare import media

    class Sink:
        def write(self, value):
            return len(value)

        def close(self):
            pass

    class HangingProcess:
        stdin = Sink()
        returncode = None
        killed = False

        def wait(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("ffmpeg", timeout)
            self.returncode = -9
            return -9

        def kill(self):
            self.killed = True

    process = HangingProcess()
    monkeypatch.setattr(media, "_start_ffmpeg", lambda command, stderr: process)
    encoder = media.SkeletonVideoEncoder(tmp_path / "timeout.mp4", 4, 4, 1.0)
    encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))

    with pytest.raises(media.MediaEncodingError, match="超时"):
        encoder.finish()

    assert process.killed is True
    assert encoder.partial_path.exists() is False


def test_encoder_finish_cleans_up_but_preserves_keyboard_interrupt(tmp_path, monkeypatch):
    from pp_mcare import media

    class Sink:
        def write(self, value):
            return len(value)

        def close(self):
            pass

    class InterruptedProcess:
        stdin = Sink()
        returncode = None
        killed = False

        def wait(self, timeout=None):
            if not self.killed:
                raise KeyboardInterrupt
            return -9

        def kill(self):
            self.killed = True

    process = InterruptedProcess()
    monkeypatch.setattr(media, "_start_ffmpeg", lambda command, stderr: process)
    encoder = media.SkeletonVideoEncoder(tmp_path / "interrupt.mp4", 4, 4, 1.0)
    encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))

    with pytest.raises(KeyboardInterrupt):
        encoder.finish()

    assert process.killed is True
    assert encoder.partial_path.exists() is False


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_probe_source_video_uses_video_duration_and_rejects_multiple_video_streams(
    tmp_path,
):
    from pp_mcare.media import MediaEncodingError, probe_source_video

    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x48:rate=20:duration=2",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    metadata = probe_source_video(source)

    assert metadata.duration_seconds == pytest.approx(2.0, abs=0.05)
    assert metadata.width == 64
    assert metadata.height == 48
    assert metadata.frame_count == 40

    longer_audio = tmp_path / "longer-audio.mp4"
    subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x48:rate=20:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(longer_audio),
        ],
        check=True,
    )
    audio_metadata = probe_source_video(longer_audio)
    assert audio_metadata.duration_seconds == pytest.approx(2.0, abs=0.05)

    multi = tmp_path / "multi.mkv"
    subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=size=16x16:duration=1",
            "-f",
            "lavfi",
            "-i",
            "color=size=16x16:duration=1",
            "-map",
            "0:v",
            "-map",
            "1:v",
            "-c:v",
            "ffv1",
            str(multi),
        ],
        check=True,
    )
    with pytest.raises(MediaEncodingError, match="一个视频流"):
        probe_source_video(multi)


def test_encoder_initialization_cleans_partial_if_stderr_file_creation_is_interrupted(
    tmp_path, monkeypatch
):
    from pp_mcare import media

    monkeypatch.setattr(
        media.tempfile,
        "TemporaryFile",
        lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    with pytest.raises(KeyboardInterrupt):
        media.SkeletonVideoEncoder(tmp_path / "stderr-interrupted.mp4", 4, 4, 1.0)

    assert list(tmp_path.iterdir()) == []


def test_encoder_commit_interruption_after_link_never_rolls_back_published_target(
    tmp_path, monkeypatch
):
    from pp_mcare import media

    output = tmp_path / "commit-interrupted.mp4"
    encoder = object.__new__(media.SkeletonVideoEncoder)
    encoder.path = output
    encoder._partial_path = tmp_path / ".private.mp4"
    encoder._partial_path.write_bytes(b"owned")
    encoder._failure = None
    encoder._finished = True
    encoder._committed = False
    encoder._closed = False
    encoder._owned_target_identity = None
    encoder.metadata = object()

    real_link = media.os.link

    def link_then_interrupt(source, target, *, follow_symlinks):
        real_link(source, target, follow_symlinks=follow_symlinks)
        raise KeyboardInterrupt

    monkeypatch.setattr(media.os, "link", link_then_interrupt)

    with pytest.raises(KeyboardInterrupt):
        encoder.commit()

    assert output.read_bytes() == b"owned"
    assert encoder.partial_path.read_bytes() == b"owned"

    encoder.abort()
    assert output.read_bytes() == b"owned"
    assert encoder.partial_path.exists() is False


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_encoder_reports_external_replacement_after_link_without_deleting_it(tmp_path, monkeypatch):
    from pp_mcare import media

    output = tmp_path / "replaced-after-link.mp4"
    encoder = media.SkeletonVideoEncoder(output, width=4, height=4, fps=1.0)
    encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))
    encoder.finish()
    real_link = media.os.link

    def link_then_replace(source, target, *, follow_symlinks):
        real_link(source, target, follow_symlinks=follow_symlinks)
        replacement = tmp_path / "external-replacement"
        replacement.write_bytes(b"external")
        replacement.replace(target)

    monkeypatch.setattr(media.os, "link", link_then_replace)

    with pytest.raises(media.MediaEncodingError, match="提交后被替换"):
        encoder.commit()

    assert output.read_bytes() == b"external"
    assert encoder.partial_path.exists() is False


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_encoder_partial_unlink_failure_after_link_is_successful_and_observable(
    tmp_path, monkeypatch
):
    from pp_mcare import media

    output = tmp_path / "published.mp4"
    encoder = media.SkeletonVideoEncoder(output, width=4, height=4, fps=1.0)
    encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))
    encoder.finish()
    partial = encoder.partial_path
    real_unlink = media.Path.unlink

    def fail_partial_unlink(path, *args, **kwargs):
        if path == partial:
            raise OSError("synthetic partial cleanup failure")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(media.Path, "unlink", fail_partial_unlink)

    encoder.commit()

    assert output.exists() is True
    assert partial.exists() is True
    assert encoder.partial_cleanup_pending is True
    encoder.abort()
    assert output.exists() is True


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_probe_source_video_rejects_excessive_missing_nominal_ticks(tmp_path):
    from pp_mcare.media import MediaEncodingError, probe_source_video

    source = tmp_path / "vfr.mp4"
    subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x48:rate=10:duration=1.8",
            "-vf",
            "select='not(eq(n,8)+eq(n,9))'",
            "-fps_mode",
            "vfr",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    fixture_probe = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=r_frame_rate,avg_frame_rate,nb_read_frames,duration",
            "-of",
            "json",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    fixture_stream = json.loads(fixture_probe.stdout)["streams"][0]
    assert fixture_stream == {
        "r_frame_rate": "10/1",
        "avg_frame_rate": "80/9",
        "duration": "1.800000",
        "nb_read_frames": "16",
    }

    with pytest.raises(MediaEncodingError, match="缺帧比例"):
        probe_source_video(source)


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_probe_source_video_accepts_sparse_missing_nominal_ticks_below_one_percent(tmp_path):
    from pp_mcare.media import probe_source_video

    source = tmp_path / "sparse-drop.mp4"
    subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x48:rate=30:duration=4",
            "-vf",
            "select='not(eq(n,60))'",
            "-fps_mode",
            "vfr",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )

    metadata = probe_source_video(source)

    assert metadata.frame_count == 119
    assert metadata.fps == pytest.approx(119 / 4)
    assert metadata.duration_seconds == pytest.approx(4.0, abs=0.01)


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_probe_source_video_rejects_excessive_missing_ticks_even_when_rates_match(tmp_path):
    from pp_mcare.media import MediaEncodingError, probe_source_video

    source = tmp_path / "vfr-rates-match.mkv"
    subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x48:rate=10:duration=1.8",
            "-vf",
            "select='not(eq(n,8)+eq(n,9))'",
            "-fps_mode",
            "vfr",
            "-an",
            "-c:v",
            "ffv1",
            str(source),
        ],
        check=True,
    )

    with pytest.raises(MediaEncodingError, match="缺帧比例"):
        probe_source_video(source)


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_probe_source_video_derives_missing_stream_duration_without_using_long_audio(
    tmp_path,
):
    from pp_mcare.media import probe_source_video

    source = tmp_path / "stream-duration-na.mkv"
    subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x48:rate=10:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=4",
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            str(source),
        ],
        check=True,
    )

    metadata = probe_source_video(source)

    assert metadata.frame_count == 20
    assert metadata.duration_seconds == pytest.approx(2.0, abs=0.01)


class _ProbeProcess:
    def __init__(self, return_code=0, *, hangs=False):
        self.returncode = None
        self.return_code = return_code
        self.hangs = hangs
        self.killed = False
        self.wait_after_kill = False

    def wait(self, timeout=None):
        if self.hangs and not self.killed:
            raise subprocess.TimeoutExpired("ffprobe", timeout)
        if self.killed:
            self.wait_after_kill = True
            self.returncode = -9
            return -9
        self.returncode = self.return_code
        return self.return_code

    def kill(self):
        self.killed = True


def test_bounded_ffprobe_rejects_stdout_and_stderr_over_limits(tmp_path, monkeypatch):
    from pp_mcare import media

    cases = [
        (b"x" * 1_048_577, b"", "标准输出超过上限"),
        (b"", b"secret-stderr-payload" * 49_933, "错误输出超过上限"),
    ]
    for stdout_payload, stderr_payload, expected in cases:

        def start(command, stdout, stderr):
            stdout.write(stdout_payload)
            stdout.flush()
            stderr.write(stderr_payload)
            stderr.flush()
            return _ProbeProcess()

        monkeypatch.setattr(media, "_start_ffprobe", start)
        with pytest.raises(media.MediaEncodingError, match=expected) as raised:
            media._run_ffprobe(
                ["ffprobe", str(tmp_path / "patient-secret.mp4")],
                stdout_limit=1_048_576,
                stderr_limit=1_048_576,
                timeout_seconds=1,
                redact_paths=(tmp_path / "patient-secret.mp4",),
                parser=lambda output: None,
            )
        assert "secret-stderr-payload" not in str(raised.value)


def test_bounded_ffprobe_uses_secure_temporary_files_redacts_and_cleans(tmp_path, monkeypatch):
    from pp_mcare import media

    process = _ProbeProcess(return_code=2)
    observed_files = []

    def start(command, stdout, stderr):
        observed_files.extend((stdout, stderr))
        assert stat.S_IMODE(os.fstat(stdout.fileno()).st_mode) == 0o600
        assert stat.S_IMODE(os.fstat(stderr.fileno()).st_mode) == 0o600
        stderr.write(f"open failed {tmp_path / 'patient-secret.mp4'}".encode())
        stderr.flush()
        return process

    monkeypatch.setattr(media, "_start_ffprobe", start)

    with pytest.raises(media.MediaEncodingError) as raised:
        media._run_ffprobe(
            ["ffprobe", str(tmp_path / "patient-secret.mp4")],
            stdout_limit=1024,
            stderr_limit=1024,
            timeout_seconds=1,
            redact_paths=(tmp_path / "patient-secret.mp4",),
            parser=lambda output: None,
        )

    assert "open failed <media>" in str(raised.value)
    assert "patient-secret.mp4" not in str(raised.value)
    assert all(file.closed for file in observed_files)


def test_bounded_ffprobe_timeout_kills_and_waits(monkeypatch):
    from pp_mcare import media

    process = _ProbeProcess(hangs=True)
    monkeypatch.setattr(media, "_start_ffprobe", lambda command, stdout, stderr: process)

    with pytest.raises(media.MediaEncodingError, match="超时"):
        media._run_ffprobe(
            ["ffprobe", "input.mp4"],
            stdout_limit=1024,
            stderr_limit=1024,
            timeout_seconds=0.01,
            redact_paths=(),
            parser=lambda output: None,
        )

    assert process.killed is True
    assert process.wait_after_kill is True


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff\n",
        b"best_effort_timestamp_time=" + b"1" * 300 + b"\n",
    ],
)
def test_timeline_parser_rejects_untrusted_or_overlong_lines_stably(payload):
    from pp_mcare import media

    with pytest.raises(media.MediaEncodingError, match="时间戳"):
        media._parse_cfr_timeline(io.BytesIO(payload), expected_fps=25.0)


def test_timeline_parser_accepts_sparse_integer_tick_duration_below_one_percent():
    from pp_mcare import media

    present_ticks = [tick for tick in range(120) if tick != 60]
    lines = []
    for index, tick in enumerate(present_ticks):
        next_tick = present_ticks[index + 1] if index + 1 < len(present_ticks) else tick + 1
        lines.append(
            "best_effort_timestamp_time="
            f"{tick / 30:.6f}|pkt_duration_time={(next_tick - tick) / 30:.6f}|\n"
        )

    timeline = media._parse_cfr_timeline(
        io.BytesIO("".join(lines).encode("ascii")),
        expected_fps=30.0,
    )

    assert timeline.frame_count == 119
    assert timeline.duration_seconds == pytest.approx(4.0, abs=0.001)
