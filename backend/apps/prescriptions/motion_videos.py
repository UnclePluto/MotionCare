import time
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from qiniu import Auth

from apps.prescriptions.action_library import MOTION_ACTION_VIDEO_OBJECT_KEYS


@dataclass(frozen=True)
class MotionVideoResolution:
    url: str
    unavailable: bool


def private_download_url(base_url: str, expires_at: int) -> str:
    auth = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    return auth.private_download_url(
        base_url,
        expires=max(1, expires_at - int(time.time())),
    )


def resolve_motion_video_url(
    object_key: str,
    legacy_url: str = "",
) -> MotionVideoResolution:
    if not object_key:
        return MotionVideoResolution(url=legacy_url, unavailable=False)
    if object_key not in MOTION_ACTION_VIDEO_OBJECT_KEYS.values():
        return MotionVideoResolution(url="", unavailable=True)

    domain = settings.MOTION_ACTION_VIDEO_DOWNLOAD_DOMAIN.rstrip("/")
    if urlparse(domain).scheme != "https":
        return MotionVideoResolution(url="", unavailable=True)
    if not settings.QINIU_ACCESS_KEY or not settings.QINIU_SECRET_KEY:
        return MotionVideoResolution(url="", unavailable=True)

    expires_at = int(
        (
            timezone.now()
            + timedelta(seconds=settings.MOTION_ACTION_VIDEO_TOKEN_TTL_SECONDS)
        ).timestamp()
    )
    return MotionVideoResolution(
        url=private_download_url(f"{domain}/{object_key}", expires_at=expires_at),
        unavailable=False,
    )


def build_demo_motion_video_manifest() -> list[dict[str, str]]:
    manifest = []
    for source_key, object_key in MOTION_ACTION_VIDEO_OBJECT_KEYS.items():
        resolution = resolve_motion_video_url(object_key)
        if resolution.unavailable:
            raise ValidationError("演示视频暂时不可用")
        manifest.append(
            {
                "source_key": source_key,
                "video_url": resolution.url,
            }
        )
    return manifest
