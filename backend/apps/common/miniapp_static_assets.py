import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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
EXPECTED_ASSET_KEYS = frozenset(
    {
        "pattern_sun",
        "pattern_coconut",
        "pattern_boat",
        "pattern_lighthouse",
        "pattern_shell",
        "category_pineapple",
        "category_bird",
        "category_train",
        "category_drum",
        "category_phone",
        "sound_bird",
        "sound_train",
        "sound_phone",
        "sound_laugh",
        "sound_drum",
        "puzzle_beach",
        "puzzle_garden",
        "puzzle_lighthouse",
        "motion-aerobic-high-knee",
        "motion-balance-sit-stand",
        "motion-resistance-row",
        "motion-resistance-leg-kickback",
        "motion-resistance-shoulder-press",
    }
)
ALLOWED_CONTENT_TYPES = frozenset({"image/webp", "audio/mp4"})
REQUIRED_ENTRY_FIELDS = frozenset(
    {"kind", "key", "contentType", "sizeBytes", "sha256", "relativePath"}
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


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
    *, source_root: Path, relative_path_value: object
) -> tuple[Path, str]:
    if not isinstance(relative_path_value, str) or not relative_path_value:
        raise CommandError("固定素材路径无效")
    if "\\" in relative_path_value:
        raise CommandError("固定素材路径无效")

    raw_parts = relative_path_value.split("/")
    relative_path = PurePosixPath(relative_path_value)
    if (
        relative_path.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or not relative_path.parts
        or relative_path.parts[0] != source_root.name
    ):
        raise CommandError("固定素材路径必须位于指定版本目录")

    try:
        candidate = (source_root.parent / Path(*relative_path.parts)).resolve(strict=True)
        candidate.relative_to(source_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CommandError("固定素材路径越界或不存在") from exc
    if not candidate.is_file():
        raise CommandError("固定素材路径不是普通文件")
    return candidate, relative_path.as_posix()


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
        if not isinstance(key, str) or not key:
            raise CommandError("固定素材清单 key 无效")
        if kind not in {"game-image", "motion-instruction-audio"}:
            raise CommandError(f"固定素材 kind 无效：{key}")
        expected_content_type = (
            "audio/mp4" if kind == "motion-instruction-audio" else "image/webp"
        )
        if content_type not in ALLOWED_CONTENT_TYPES or content_type != expected_content_type:
            raise CommandError(f"固定素材媒体类型不允许：{key}")
        if type(size_bytes) is not int or size_bytes < 0:
            raise CommandError(f"固定素材字节数无效：{key}")
        if not isinstance(expected_sha256, str) or not SHA256_PATTERN.fullmatch(
            expected_sha256
        ):
            raise CommandError(f"固定素材 SHA-256 无效：{key}")

        path, relative_path = _resolve_asset_path(
            source_root=source_root,
            relative_path_value=entry["relativePath"],
        )
        if relative_path in seen_paths:
            raise CommandError(f"固定素材路径重复：{key}")
        seen_paths.add(relative_path)
        if path.stat().st_size != size_bytes:
            raise CommandError(f"固定素材字节数不匹配：{key}")
        if _sha256(path) != expected_sha256:
            raise CommandError(f"固定素材 SHA-256 不匹配：{key}")
        if f".{expected_sha256[:12]}." not in path.name:
            raise CommandError(f"固定素材文件名缺少内容哈希：{key}")

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
