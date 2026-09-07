import time

from django.conf import settings

from apps.common.miniapp_static_asset_registry import load_registered_static_assets
from apps.training.qiniu import private_download_url


def build_signed_static_asset_manifest(version: str, *, now: int | None = None) -> dict:
    manifest = load_registered_static_assets(version)
    base = settings.MINIAPP_STATIC_ASSET_BASE_URL
    if not base or not settings.QINIU_ACCESS_KEY or not settings.QINIU_SECRET_KEY:
        raise ValueError("固定素材签名配置不可用")

    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + settings.MINIAPP_STATIC_ASSET_URL_TTL_SECONDS
    assets = []
    for entry in manifest["entries"]:
        assets.append(
            {
                "key": entry["key"],
                "relative_path": entry["relativePath"],
                "url": private_download_url(
                    base + "/" + entry["relativePath"], expires_at=expires_at
                ),
                "content_type": entry["contentType"],
                "size_bytes": entry["sizeBytes"],
                "sha256": entry["sha256"],
            }
        )
    return {
        "asset_version": version,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "assets": assets,
    }
