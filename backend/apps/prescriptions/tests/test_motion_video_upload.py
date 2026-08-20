import json
import re
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.prescriptions.action_library import MOTION_ACTION_VIDEO_OBJECT_KEYS
from apps.prescriptions import motion_video_assets as assets


SOURCE_FILES = {
    "motion-aerobic-high-knee": "高抬腿+摆臂/高抬腿+摆臂 动作教学.mp4",
    "motion-balance-sit-stand": "坐站转移/坐姿转移 动作教学.mp4",
    "motion-resistance-row": "坐姿划船/坐姿划船 动作教学.mp4",
    "motion-resistance-leg-kickback": "腿部后踢/腿部后踢 动作教学.mp4",
    "motion-resistance-shoulder-press": "肩部推举/动作教学.mp4",
}


def _source_root(tmp_path: Path, *, missing_source_key: str | None = None) -> Path:
    source_root = tmp_path / "运动处方"
    for source_key, relative_path in SOURCE_FILES.items():
        if source_key == missing_source_key:
            continue
        path = source_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"official-motion-video")
    return source_root


def _probe() -> assets.MotionAssetProbe:
    return assets.MotionAssetProbe(
        codec="h264",
        audio_codec="aac",
        width=1080,
        height=1920,
        duration_seconds=30.0,
        size_bytes=len(b"official-motion-video"),
    )


def _metadata(*, object_hash: str = "local-etag", size_bytes: int | None = None) -> dict:
    return {
        "hash": object_hash,
        "fsize": size_bytes if size_bytes is not None else len(b"official-motion-video"),
        "mimeType": "video/mp4",
    }


def _ffprobe_output(
    *,
    video_codec: str = "h264",
    audio_codec: str = "aac",
    width: int = 1080,
    height: int = 1920,
    duration: str = "30.0",
    format_name: str = "mov,mp4,m4a,3gp,3g2,mj2",
) -> str:
    return json.dumps(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": video_codec,
                    "width": width,
                    "height": height,
                },
                {"codec_type": "audio", "codec_name": audio_codec},
            ],
            "format": {"duration": duration, "format_name": format_name},
        }
    )


def test_missing_source_file_stops_before_any_remote_request(tmp_path, monkeypatch):
    source_root = _source_root(
        tmp_path, missing_source_key="motion-resistance-shoulder-press"
    )
    stat = Mock()
    upload = Mock()
    monkeypatch.setattr(assets, "probe_motion_asset", lambda path, ffprobe_path: _probe())
    monkeypatch.setattr(assets, "stat_object_metadata_or_none", stat)
    monkeypatch.setattr(assets, "upload_local_video", upload)

    with pytest.raises(CommandError, match="正式动作视频文件不存在"):
        assets.upload_motion_action_assets(source_root)

    stat.assert_not_called()
    upload.assert_not_called()


@pytest.mark.parametrize(
    ("video_codec", "audio_codec", "width", "height", "duration", "message"),
    [
        ("hevc", "aac", 1080, 1920, "30.0", "正式动作视频编码必须为 H.264 + AAC"),
        ("h264", "opus", 1080, 1920, "30.0", "正式动作视频编码必须为 H.264 + AAC"),
        ("h264", "aac", 720, 1920, "30.0", "正式动作视频尺寸必须为 1080×1920"),
        ("h264", "aac", 1080, 1920, "4.99", "正式动作视频时长必须为 5–120 秒"),
        ("h264", "aac", 1080, 1920, "120.01", "正式动作视频时长必须为 5–120 秒"),
    ],
)
def test_probe_rejects_invalid_official_video_format(
    tmp_path,
    monkeypatch,
    video_codec,
    audio_codec,
    width,
    height,
    duration,
    message,
):
    path = tmp_path / "official.mp4"
    path.write_bytes(b"official-motion-video")
    run = Mock(
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=_ffprobe_output(
                video_codec=video_codec,
                audio_codec=audio_codec,
                width=width,
                height=height,
                duration=duration,
            ),
        )
    )
    monkeypatch.setattr(assets.subprocess, "run", run)

    with pytest.raises(CommandError, match=re.escape(message)):
        assets.probe_motion_asset(path, ffprobe_path="ffprobe")

    run.assert_called_once_with(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )


def test_probe_returns_validated_media_metadata(tmp_path, monkeypatch):
    path = tmp_path / "official.mp4"
    path.write_bytes(b"official-motion-video")
    monkeypatch.setattr(
        assets.subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout=_ffprobe_output()
            )
        ),
    )

    result = assets.probe_motion_asset(path, ffprobe_path="ffprobe")

    assert result == assets.MotionAssetProbe(
        codec="h264",
        audio_codec="aac",
        width=1080,
        height=1920,
        duration_seconds=30.0,
        size_bytes=len(b"official-motion-video"),
    )


def test_probe_rejects_non_mp4_suffix_before_running_ffprobe(tmp_path, monkeypatch):
    path = tmp_path / "official.mov"
    path.write_bytes(b"official-motion-video")
    run = Mock()
    monkeypatch.setattr(assets.subprocess, "run", run)

    with pytest.raises(CommandError, match="扩展名必须为 .mp4"):
        assets.probe_motion_asset(path, ffprobe_path="ffprobe")

    run.assert_not_called()


def test_probe_rejects_non_mp4_container(tmp_path, monkeypatch):
    path = tmp_path / "official.mp4"
    path.write_bytes(b"official-motion-video")
    monkeypatch.setattr(
        assets.subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=_ffprobe_output(format_name="matroska,webm"),
            )
        ),
    )

    with pytest.raises(CommandError, match="容器必须为 MP4"):
        assets.probe_motion_asset(path, ffprobe_path="ffprobe")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"streams": "not-a-list", "format": {}},
        {"streams": ["not-a-stream"], "format": {}},
        {"streams": [], "format": []},
        {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1080,
                    "height": 1920,
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
            "format": {"format_name": ["mp4"], "duration": "30"},
        },
    ],
)
def test_probe_turns_malformed_ffprobe_structures_into_command_error(
    tmp_path,
    monkeypatch,
    payload,
):
    path = tmp_path / "official.mp4"
    path.write_bytes(b"official-motion-video")
    monkeypatch.setattr(
        assets.subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(payload)
            )
        ),
    )

    with pytest.raises(CommandError, match="FFprobe 输出无效"):
        assets.probe_motion_asset(path, ffprobe_path="ffprobe")


def test_matching_remote_objects_are_reported_as_existing_without_upload(tmp_path, monkeypatch):
    source_root = _source_root(tmp_path)
    stat = Mock(return_value=_metadata())
    upload = Mock()
    monkeypatch.setattr(assets, "probe_motion_asset", lambda path, ffprobe_path: _probe())
    monkeypatch.setattr(assets.qiniu, "etag", lambda path: "local-etag")
    monkeypatch.setattr(assets, "stat_object_metadata_or_none", stat)
    monkeypatch.setattr(assets, "upload_local_video", upload)

    uploaded = assets.upload_motion_action_assets(source_root)

    assert [asset.object_key for asset in uploaded] == list(
        MOTION_ACTION_VIDEO_OBJECT_KEYS.values()
    )
    assert [asset.status for asset in uploaded] == ["existing"] * 5
    upload.assert_not_called()


def test_conflicting_remote_object_is_rejected_without_overwrite(tmp_path, monkeypatch):
    source_root = _source_root(tmp_path)
    upload = Mock()
    monkeypatch.setattr(assets, "probe_motion_asset", lambda path, ffprobe_path: _probe())
    monkeypatch.setattr(assets.qiniu, "etag", lambda path: "local-etag")
    monkeypatch.setattr(
        assets,
        "stat_object_metadata_or_none",
        Mock(return_value=_metadata(object_hash="other-etag")),
    )
    monkeypatch.setattr(assets, "upload_local_video", upload)

    with pytest.raises(CommandError, match="Hash 不匹配"):
        assets.upload_motion_action_assets(source_root)

    upload.assert_not_called()


def test_missing_remote_objects_are_uploaded_and_revalidated(tmp_path, monkeypatch):
    source_root = _source_root(tmp_path)
    stat = Mock(side_effect=[None, _metadata()] * 5)
    upload = Mock(return_value=_metadata())
    monkeypatch.setattr(assets, "probe_motion_asset", lambda path, ffprobe_path: _probe())
    monkeypatch.setattr(assets.qiniu, "etag", lambda path: "local-etag")
    monkeypatch.setattr(assets, "stat_object_metadata_or_none", stat)
    monkeypatch.setattr(assets, "upload_local_video", upload)

    uploaded = assets.upload_motion_action_assets(source_root)

    assert [asset.status for asset in uploaded] == ["uploaded"] * 5
    assert [call.kwargs["key"] for call in upload.call_args_list] == list(
        MOTION_ACTION_VIDEO_OBJECT_KEYS.values()
    )
    assert [call.kwargs["insert_only"] for call in upload.call_args_list] == [True] * 5
    assert stat.call_count == 10


@pytest.mark.parametrize("failure_point", ["initial_stat", "upload", "post_upload_stat"])
def test_storage_validation_errors_do_not_leak_sensitive_details(
    tmp_path, monkeypatch, caplog, failure_point
):
    source_root = _source_root(tmp_path)
    secret = "token=private-access-key"
    error = ValidationError(secret)
    stat = Mock()
    upload = Mock()
    if failure_point == "initial_stat":
        stat.side_effect = error
    elif failure_point == "upload":
        stat.return_value = None
        upload.side_effect = error
    else:
        stat.side_effect = [None, error]

    monkeypatch.setattr(assets, "probe_motion_asset", lambda path, ffprobe_path: _probe())
    monkeypatch.setattr(assets.qiniu, "etag", lambda path: "local-etag")
    monkeypatch.setattr(assets, "stat_object_metadata_or_none", stat)
    monkeypatch.setattr(assets, "upload_local_video", upload)

    with pytest.raises(CommandError, match="正式动作视频远端对象操作失败") as exc_info:
        assets.upload_motion_action_assets(source_root)

    assert secret not in str(exc_info.value)
    assert secret not in caplog.text
    assert "正式动作视频远端对象操作失败" in caplog.text


def test_check_only_uses_no_qiniu_operations(tmp_path, monkeypatch):
    source_root = _source_root(tmp_path)
    stat = Mock()
    upload = Mock()
    monkeypatch.setattr(assets, "probe_motion_asset", lambda path, ffprobe_path: _probe())
    monkeypatch.setattr(assets, "stat_object_metadata_or_none", stat)
    monkeypatch.setattr(assets, "upload_local_video", upload)

    call_command(
        "upload_motion_action_videos",
        "--source-root",
        str(source_root),
        "--check-only",
    )

    stat.assert_not_called()
    upload.assert_not_called()
