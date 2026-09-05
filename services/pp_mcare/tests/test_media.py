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
    with SkeletonVideoEncoder(output, width=64, height=48, fps=20.0) as encoder:
        for index in range(40):
            frame = np.zeros((48, 64, 3), dtype=np.uint8)
            frame[:, :, index % 3] = (index * 7) % 255
            encoder.write(frame)
    metadata = encoder.metadata

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

        def wait(self):
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
