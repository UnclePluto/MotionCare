"""Load and verify the controlled CRF runtime assets without database access."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings

_REGISTRY: dict | None = None
_TEMPLATE_REVISION = "1.1"
_SOURCE_DOCX_SHA256 = "f031dd59a1e169548fe651555d19c41306cc51e6bfcf7eb933edcee86924102a"


class CrfAssetError(RuntimeError):
    """A required CRF runtime asset is unavailable or incompatible."""


def _registry_path() -> Path:
    return Path(settings.CRF_REGISTRY_PATH)


def _read_asset(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CrfAssetError(f"CRF {label} 无法读取：{path}（{exc}）") from exc


def _read_registry(path: Path) -> tuple[dict, bytes]:
    content = _read_asset(path, "字段资产")
    try:
        registry = json.loads(content)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CrfAssetError(f"CRF 字段资产 JSON 无效：{path}") from exc
    if not isinstance(registry, dict):
        raise CrfAssetError(f"CRF 字段资产必须是对象：{path}")
    return registry, content


def _verify_assets(registry_path: Path, template_path: Path) -> tuple[dict, dict]:
    registry, registry_content = _read_registry(registry_path)
    template_content = _read_asset(template_path, "原表")
    if registry.get("template_revision") != _TEMPLATE_REVISION:
        raise CrfAssetError(f"CRF 模板版本须为 {_TEMPLATE_REVISION}：{registry_path}")
    if registry.get("source_docx_sha256") != _SOURCE_DOCX_SHA256:
        raise CrfAssetError(f"CRF 字段资产的原表哈希不符：{registry_path}")
    template_sha256 = hashlib.sha256(template_content).hexdigest()
    if template_sha256 != _SOURCE_DOCX_SHA256:
        raise CrfAssetError(f"CRF 原表哈希不符：{template_path}")
    source = load_crf_source_slots(registry_path=registry_path)
    return registry, {
        "source_slots_path": str(registry_path.parent / "source_slots.v1.json"),
        "source_slot_count": len(source["slots"]),
        "template_revision": registry["template_revision"],
        "registry_path": str(registry_path),
        "template_path": str(template_path),
        "registry_exists": True,
        "template_exists": True,
        "registry_sha256": hashlib.sha256(registry_content).hexdigest(),
        "template_sha256": template_sha256,
    }


def check_crf_assets(
    *, registry_path: Path | None = None, template_path: Path | None = None
) -> dict:
    """Verify asset identity and return actual file metadata; never query the database."""
    _, result = _verify_assets(
        Path(registry_path) if registry_path is not None else _registry_path(),
        Path(template_path) if template_path is not None else Path(settings.CRF_TEMPLATE_PATH),
    )
    return result


def load_crf_registry(force_reload: bool = False) -> dict:
    """Return the verified registry, cached unless force_reload is requested."""
    global _REGISTRY
    if not force_reload and _REGISTRY is not None:
        return _REGISTRY
    registry, _ = _verify_assets(_registry_path(), Path(settings.CRF_TEMPLATE_PATH))
    _REGISTRY = registry
    return _REGISTRY


def load_crf_source_slots(*, registry_path: Path | None = None) -> dict:
    """Load the independently reviewed source manifest next to the chosen registry."""
    path = (
        Path(registry_path) if registry_path is not None else _registry_path()
    ).parent / "source_slots.v1.json"
    content = _read_asset(path, "原表填写位清单")
    # Pin the reviewed manifest itself, not merely its self-declared template hash.
    if (
        hashlib.sha256(content).hexdigest()
        != "0252a44a5ee47a6d73f36e3ef09d71393ded6f70ba82ee199c2dc8487402c9c5"
    ):
        raise CrfAssetError(f"CRF 原表填写位清单身份不符：{path}")
    return json.loads(content)
