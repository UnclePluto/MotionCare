from datetime import datetime, timezone as datetime_timezone

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

from apps.prescriptions.motion_videos import (
    MotionVideoResolution,
    build_demo_motion_video_manifest,
    private_download_url,
    resolve_motion_video_url,
)


@override_settings(
    QINIU_ACCESS_KEY="ak",
    QINIU_SECRET_KEY="sk",
    MOTION_ACTION_VIDEO_DOWNLOAD_DOMAIN="https://cdn.whestsun.com",
    MOTION_ACTION_VIDEO_TOKEN_TTL_SECONDS=7200,
)
def test_motion_video_key_resolves_to_short_lived_https_url(monkeypatch):
    expires_at_values = []
    monkeypatch.setattr(
        "apps.prescriptions.motion_videos.private_download_url",
        lambda base_url, expires_at: (
            expires_at_values.append(expires_at) or f"{base_url}?e={expires_at}&token=signed"
        ),
    )
    fixed_now = datetime(2026, 8, 20, 12, 0, tzinfo=datetime_timezone.utc)
    monkeypatch.setattr("apps.prescriptions.motion_videos.timezone.now", lambda: fixed_now)

    result = resolve_motion_video_url(
        "motion-action-videos/v1/motion-resistance-row.mp4"
    )

    assert result.unavailable is False
    assert result.url.startswith(
        "https://cdn.whestsun.com/motion-action-videos/v1/motion-resistance-row.mp4?"
    )
    assert expires_at_values == [int(fixed_now.timestamp()) + 7200]


def test_motion_video_signer_rejects_arbitrary_key():
    result = resolve_motion_video_url("training-videos/private-patient.mp4")

    assert result == MotionVideoResolution(url="", unavailable=True)


@override_settings(MOTION_ACTION_VIDEO_DOWNLOAD_DOMAIN="http://insecure.example.com")
def test_motion_video_signer_rejects_non_https_domain():
    result = resolve_motion_video_url(
        "motion-action-videos/v1/motion-resistance-row.mp4"
    )

    assert result.unavailable is True
    assert result.url == ""


def test_motion_video_without_object_key_uses_legacy_url():
    result = resolve_motion_video_url("", legacy_url="https://legacy.example.com/video.mp4")

    assert result == MotionVideoResolution(
        url="https://legacy.example.com/video.mp4",
        unavailable=False,
    )


@override_settings(
    QINIU_ACCESS_KEY="ak",
    QINIU_SECRET_KEY="sk",
    MOTION_ACTION_VIDEO_DOWNLOAD_DOMAIN="https://cdn.whestsun.com",
)
def test_demo_motion_video_manifest_contains_only_source_keys_and_signed_urls(monkeypatch):
    monkeypatch.setattr(
        "apps.prescriptions.motion_videos.private_download_url",
        lambda base_url, expires_at: f"{base_url}?token=signed",
    )

    manifest = build_demo_motion_video_manifest()

    assert manifest == [
        {
            "source_key": "motion-aerobic-high-knee",
            "video_url": "https://cdn.whestsun.com/motion-action-videos/v1/motion-aerobic-high-knee.mp4?token=signed",
        },
        {
            "source_key": "motion-balance-sit-stand",
            "video_url": "https://cdn.whestsun.com/motion-action-videos/v1/motion-balance-sit-stand.mp4?token=signed",
        },
        {
            "source_key": "motion-resistance-row",
            "video_url": "https://cdn.whestsun.com/motion-action-videos/v1/motion-resistance-row.mp4?token=signed",
        },
        {
            "source_key": "motion-resistance-leg-kickback",
            "video_url": "https://cdn.whestsun.com/motion-action-videos/v1/motion-resistance-leg-kickback.mp4?token=signed",
        },
        {
            "source_key": "motion-resistance-shoulder-press",
            "video_url": "https://cdn.whestsun.com/motion-action-videos/v1/motion-resistance-shoulder-press.mp4?token=signed",
        },
    ]


@pytest.mark.parametrize(
    ("expires_at", "expected_ttl"),
    [
        (8_200, 7_200),
        (1_000, 1),
    ],
)
def test_private_download_url_converts_absolute_expiry_to_relative_ttl(
    monkeypatch,
    expires_at,
    expected_ttl,
):
    class FakeAuth:
        def __init__(self):
            self.received = None

        def private_download_url(self, base_url, expires):
            self.received = (base_url, expires)
            return "https://cdn.whestsun.com/signed.mp4?token=signed"

    auth = FakeAuth()
    monkeypatch.setattr("apps.prescriptions.motion_videos.Auth", lambda ak, sk: auth)
    monkeypatch.setattr("apps.prescriptions.motion_videos.time.time", lambda: 1_000.9)

    url = private_download_url(
        "https://cdn.whestsun.com/video.mp4",
        expires_at=expires_at,
    )

    assert url == "https://cdn.whestsun.com/signed.mp4?token=signed"
    assert auth.received == ("https://cdn.whestsun.com/video.mp4", expected_ttl)


@override_settings(QINIU_ACCESS_KEY="", QINIU_SECRET_KEY="")
def test_demo_motion_video_manifest_hides_signing_failures():
    with pytest.raises(ValidationError) as exc_info:
        build_demo_motion_video_manifest()

    assert exc_info.value.messages == ["演示视频暂时不可用"]
