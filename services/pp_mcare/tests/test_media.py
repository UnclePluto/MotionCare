from __future__ import annotations

import json
import shutil
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


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_encoder_commit_never_clobbers_target_created_after_initialization(tmp_path):
    from pp_mcare.media import MediaEncodingError, SkeletonVideoEncoder

    output = tmp_path / "raced.mp4"
    encoder = SkeletonVideoEncoder(output, width=4, height=4, fps=1.0)
    encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))
    encoder.finish()
    output.write_bytes(b"external-owner")

    with pytest.raises(MediaEncodingError, match="已经存在"):
        encoder.commit()
    encoder.abort()

    assert output.read_bytes() == b"external-owner"


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_abort_after_commit_only_removes_the_encoder_owned_inode(tmp_path):
    from pp_mcare.media import SkeletonVideoEncoder

    output = tmp_path / "committed.mp4"
    encoder = SkeletonVideoEncoder(output, width=4, height=4, fps=1.0)
    encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))
    encoder.finish()
    encoder.commit()
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"external-replacement")
    replacement.replace(output)

    encoder.abort()

    assert output.read_bytes() == b"external-replacement"


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="需要真实 ffmpeg/ffprobe")
def test_abort_after_commit_removes_encoder_owned_published_file(tmp_path):
    from pp_mcare.media import SkeletonVideoEncoder

    output = tmp_path / "owned.mp4"
    encoder = SkeletonVideoEncoder(output, width=4, height=4, fps=1.0)
    encoder.write(np.zeros((4, 4, 3), dtype=np.uint8))
    encoder.finish()
    encoder.commit()

    encoder.abort()

    assert output.exists() is False


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


def test_encoder_commit_interruption_after_link_removes_only_its_new_link(tmp_path, monkeypatch):
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

    assert output.exists() is False
    assert encoder.partial_path.read_bytes() == b"owned"
