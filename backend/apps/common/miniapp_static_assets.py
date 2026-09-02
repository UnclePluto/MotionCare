import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import qiniu
from django.conf import settings
from django.core.management.base import CommandError

from apps.training.qiniu import stat_object_metadata_or_none


__all__ = [
    "PreparedStaticAsset",
    "PublishedStaticAsset",
    "publish_miniapp_static_assets",
    "upload_static_asset",
    "validate_miniapp_static_assets",
]


logger = logging.getLogger(__name__)

OBJECT_PREFIX = "motioncare/static-assets"
CANONICAL_ASSET_SPECS = {
    "pattern_sun": ("game-image", "image/webp", "webp"),
    "pattern_coconut": ("game-image", "image/webp", "webp"),
    "pattern_boat": ("game-image", "image/webp", "webp"),
    "pattern_lighthouse": ("game-image", "image/webp", "webp"),
    "pattern_shell": ("game-image", "image/webp", "webp"),
    "category_pineapple": ("game-image", "image/webp", "webp"),
    "category_bird": ("game-image", "image/webp", "webp"),
    "category_train": ("game-image", "image/webp", "webp"),
    "category_drum": ("game-image", "image/webp", "webp"),
    "category_phone": ("game-image", "image/webp", "webp"),
    "sound_bird": ("game-image", "image/webp", "webp"),
    "sound_train": ("game-image", "image/webp", "webp"),
    "sound_phone": ("game-image", "image/webp", "webp"),
    "sound_laugh": ("game-image", "image/webp", "webp"),
    "sound_drum": ("game-image", "image/webp", "webp"),
    "puzzle_beach": ("game-image", "image/webp", "webp"),
    "puzzle_garden": ("game-image", "image/webp", "webp"),
    "puzzle_lighthouse": ("game-image", "image/webp", "webp"),
    "motion-aerobic-high-knee": (
        "motion-instruction-audio",
        "audio/mp4",
        "m4a",
    ),
    "motion-balance-sit-stand": (
        "motion-instruction-audio",
        "audio/mp4",
        "m4a",
    ),
    "motion-resistance-row": (
        "motion-instruction-audio",
        "audio/mp4",
        "m4a",
    ),
    "motion-resistance-leg-kickback": (
        "motion-instruction-audio",
        "audio/mp4",
        "m4a",
    ),
    "motion-resistance-shoulder-press": (
        "motion-instruction-audio",
        "audio/mp4",
        "m4a",
    ),
}
EXPECTED_ASSET_KEYS = frozenset(CANONICAL_ASSET_SPECS)
REQUIRED_ENTRY_FIELDS = frozenset(
    {"kind", "key", "contentType", "sizeBytes", "sha256", "relativePath"}
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ASSET_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class PreparedStaticAsset:
    key: str
    object_key: str
    path: Path
    content_type: str
    size_bytes: int
    sha256: str
    qiniu_hash: str


@dataclass(frozen=True)
class PublishedStaticAsset:
    key: str
    object_key: str
    size_bytes: int
    status: Literal["existing", "uploaded"]


def _load_manifest(source_root: Path) -> dict:
    manifest_path = source_root / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CommandError("固定素材清单无法读取") from exc
    if not isinstance(payload, dict):
        raise CommandError("固定素材清单格式无效")
    return payload


def _resolve_asset_path(
    *,
    source_root: Path,
    relative_path_value: object,
    key: str,
    sha256: str,
    extension: str,
) -> tuple[Path, str]:
    if not isinstance(relative_path_value, str) or not relative_path_value:
        raise CommandError("固定素材路径无效")
    expected_relative_path = (
        f"{source_root.name}/{key}.{sha256[:12]}.{extension}"
    )
    if relative_path_value != expected_relative_path:
        raise CommandError("固定素材路径不符合规范路径")

    try:
        candidate = (source_root.parent / expected_relative_path).resolve(strict=True)
        candidate.relative_to(source_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CommandError("固定素材路径越界或不存在") from exc
    if not candidate.is_file():
        raise CommandError("固定素材路径不是普通文件")
    return candidate, expected_relative_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CommandError("固定素材文件无法读取") from exc
    return digest.hexdigest()


def _qiniu_hash(path: Path, *, key: str) -> str:
    try:
        return qiniu.etag(str(path))
    except Exception:
        raise CommandError(f"固定素材无法计算七牛 Hash：{key}") from None


def validate_miniapp_static_assets(source_root: Path) -> list[PreparedStaticAsset]:
    try:
        source_root = Path(source_root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CommandError("固定素材版本目录不存在") from exc
    if not source_root.is_dir():
        raise CommandError("固定素材版本目录无效")
    if not ASSET_VERSION_PATTERN.fullmatch(source_root.name):
        raise CommandError("固定素材版本目录名无效")

    manifest = _load_manifest(source_root)
    if manifest.get("assetVersion") != source_root.name:
        raise CommandError("固定素材清单版本与目录名不一致")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or len(entries) != len(EXPECTED_ASSET_KEYS):
        raise CommandError("固定素材清单必须包含 23 项")
    if any(not isinstance(entry, dict) for entry in entries):
        raise CommandError("固定素材清单项格式无效")
    if any(REQUIRED_ENTRY_FIELDS.difference(entry) for entry in entries):
        raise CommandError("固定素材清单项缺少字段")

    manifest_keys = [entry["key"] for entry in entries]
    if any(not isinstance(key, str) or not key for key in manifest_keys):
        raise CommandError("固定素材清单 key 无效")
    if len(set(manifest_keys)) != len(manifest_keys) or set(manifest_keys) != EXPECTED_ASSET_KEYS:
        raise CommandError("固定素材清单必须包含 23 项规范素材")

    prepared: list[PreparedStaticAsset] = []
    seen_paths: set[str] = set()
    for entry in entries:
        key = entry["key"]
        kind = entry["kind"]
        content_type = entry["contentType"]
        size_bytes = entry["sizeBytes"]
        expected_sha256 = entry["sha256"]
        expected_kind, expected_content_type, extension = CANONICAL_ASSET_SPECS[key]
        if kind != expected_kind or content_type != expected_content_type:
            raise CommandError(f"固定素材规范类型或媒体类型不匹配：{key}")
        if type(size_bytes) is not int or size_bytes < 0:
            raise CommandError(f"固定素材字节数无效：{key}")
        if not isinstance(expected_sha256, str) or not SHA256_PATTERN.fullmatch(
            expected_sha256
        ):
            raise CommandError(f"固定素材 SHA-256 无效：{key}")

        path, relative_path = _resolve_asset_path(
            source_root=source_root,
            relative_path_value=entry["relativePath"],
            key=key,
            sha256=expected_sha256,
            extension=extension,
        )
        if relative_path in seen_paths:
            raise CommandError(f"固定素材路径重复：{key}")
        seen_paths.add(relative_path)
        if path.stat().st_size != size_bytes:
            raise CommandError(f"固定素材字节数不匹配：{key}")
        if _sha256(path) != expected_sha256:
            raise CommandError(f"固定素材 SHA-256 不匹配：{key}")
        prepared.append(
            PreparedStaticAsset(
                key=key,
                object_key=f"{OBJECT_PREFIX}/{relative_path}",
                path=path,
                content_type=content_type,
                size_bytes=size_bytes,
                sha256=expected_sha256,
                qiniu_hash=_qiniu_hash(path, key=key),
            )
        )
    return prepared


def _normalized_content_type(value: object) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def _remote_metadata_matches(metadata: dict, asset: PreparedStaticAsset) -> bool:
    return (
        metadata.get("hash") == asset.qiniu_hash
        and metadata.get("fsize") == asset.size_bytes
        and _normalized_content_type(metadata.get("mimeType")) == asset.content_type
    )


def _stat_remote(asset: PreparedStaticAsset) -> dict | None:
    try:
        return stat_object_metadata_or_none(
            bucket=settings.QINIU_BUCKET,
            key=asset.object_key,
        )
    except Exception:
        logger.warning("固定素材远端操作失败：%s", asset.object_key)
        raise CommandError(f"固定素材远端操作失败：{asset.object_key}") from None


def upload_static_asset(
    *,
    path: Path,
    object_key: str,
    content_type: str,
    expected_qiniu_hash: str,
) -> None:
    try:
        auth = qiniu.Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
        token = auth.upload_token(
            settings.QINIU_BUCKET,
            object_key,
            3600,
            policy={"insertOnly": 1},
        )
        result, response = qiniu.put_file(
            token,
            object_key,
            str(path),
            check_crc=True,
            mime_type=content_type,
        )
    except Exception:
        logger.warning("固定素材远端操作失败：%s", object_key)
        raise CommandError(f"固定素材远端操作失败：{object_key}") from None
    if (
        getattr(response, "status_code", None) != 200
        or not isinstance(result, dict)
        or result.get("key") != object_key
        or result.get("hash") != expected_qiniu_hash
    ):
        logger.warning("固定素材远端操作失败：%s", object_key)
        raise CommandError(f"固定素材远端操作失败：{object_key}")


def publish_miniapp_static_assets(source_root: Path) -> list[PublishedStaticAsset]:
    prepared = validate_miniapp_static_assets(source_root)
    published: list[PublishedStaticAsset] = []
    for asset in prepared:
        metadata = _stat_remote(asset)
        if metadata is not None:
            if not _remote_metadata_matches(metadata, asset):
                raise CommandError(f"远端固定素材冲突：{asset.object_key}")
            status: Literal["existing", "uploaded"] = "existing"
        else:
            try:
                upload_static_asset(
                    path=asset.path,
                    object_key=asset.object_key,
                    content_type=asset.content_type,
                    expected_qiniu_hash=asset.qiniu_hash,
                )
            except Exception:
                metadata = _stat_remote(asset)
                if metadata is None:
                    logger.warning("固定素材远端操作失败：%s", asset.object_key)
                    raise CommandError(
                        f"固定素材远端操作失败：{asset.object_key}"
                    ) from None
                if not _remote_metadata_matches(metadata, asset):
                    raise CommandError(f"远端固定素材冲突：{asset.object_key}")
                status = "existing"
            else:
                metadata = _stat_remote(asset)
                if metadata is None:
                    raise CommandError(f"固定素材上传后不存在：{asset.object_key}")
                if not _remote_metadata_matches(metadata, asset):
                    raise CommandError(f"远端固定素材冲突：{asset.object_key}")
                status = "uploaded"

        published.append(
            PublishedStaticAsset(
                key=asset.key,
                object_key=asset.object_key,
                size_bytes=asset.size_bytes,
                status=status,
            )
        )
    return published
