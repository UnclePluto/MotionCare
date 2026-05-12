"""Load CRF field registry JSON from the repository root (cached)."""

from __future__ import annotations

import json
from pathlib import Path

_REGISTRY: dict | None = None


def _registry_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "specs" / "patient-rehab-system" / "crf" / "registry.v1.json"


def load_crf_registry(force_reload: bool = False) -> dict:
    """Return the full CRF registry dict. Loaded once per process unless force_reload."""
    global _REGISTRY

    if not force_reload and _REGISTRY is not None:
        return _REGISTRY

    path = _registry_path()
    if not path.is_file():
        raise FileNotFoundError(f"CRF registry JSON not found at: {path}")

    with path.open(encoding="utf-8") as f:
        _REGISTRY = json.load(f)

    return _REGISTRY
