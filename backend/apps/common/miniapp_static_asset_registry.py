import json
from pathlib import Path

from apps.common.miniapp_static_assets import CANONICAL_ASSET_SPECS


MANIFEST_ROOT = Path(__file__).with_name("miniapp_static_asset_manifests")
REGISTERED_STATIC_ASSET_MANIFESTS: dict[str, Path] = {
    "v-3aafe09211fd": MANIFEST_ROOT / "v-3aafe09211fd.json",
}


def _validate_registered_manifest(payload: object, version: str) -> dict:
    if not isinstance(payload, dict) or payload.get("assetVersion") != version:
        raise ValueError("已登记固定素材清单版本无效")

    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != len(CANONICAL_ASSET_SPECS):
        raise ValueError("已登记固定素材清单项目数无效")
    if any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("已登记固定素材清单项目格式无效")

    keys = [entry.get("key") for entry in entries]
    if any(not isinstance(key, str) for key in keys):
        raise ValueError("已登记固定素材清单 key 无效")
    if len(set(keys)) != len(keys) or set(keys) != set(CANONICAL_ASSET_SPECS):
        raise ValueError("已登记固定素材清单 key 无效")

    for entry in entries:
        key = entry["key"]
        expected_kind, expected_content_type, extension = CANONICAL_ASSET_SPECS[key]
        sha256 = entry.get("sha256")
        size_bytes = entry.get("sizeBytes")
        if entry.get("kind") != expected_kind or entry.get("contentType") != expected_content_type:
            raise ValueError(f"已登记固定素材类型无效：{key}")
        if type(size_bytes) is not int or size_bytes < 0:
            raise ValueError(f"已登记固定素材字节数无效：{key}")
        if (
            not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
        ):
            raise ValueError(f"已登记固定素材 SHA-256 无效：{key}")
        expected_path = f"{version}/{key}.{sha256[:12]}.{extension}"
        if entry.get("relativePath") != expected_path:
            raise ValueError(f"已登记固定素材路径无效：{key}")

    return payload


def load_registered_static_assets(version: str) -> dict:
    try:
        manifest_path = REGISTERED_STATIC_ASSET_MANIFESTS[version]
    except (KeyError, TypeError):
        raise KeyError(version) from None

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"已登记固定素材清单无法读取：{version}") from exc
    return _validate_registered_manifest(payload, version)
