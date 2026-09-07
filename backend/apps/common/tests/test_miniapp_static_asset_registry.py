import json

import pytest

from apps.common import miniapp_static_asset_registry
from apps.common.miniapp_static_asset_registry import load_registered_static_assets


@pytest.mark.parametrize(
    "version",
    [
        "../training",
        "/etc/passwd",
        "v-000000000000",
        "v-3aafe09211fd/../x",
    ],
)
def test_unregistered_version_is_not_a_filesystem_path(version):
    with pytest.raises(KeyError):
        load_registered_static_assets(version)


def test_current_manifest_contains_only_product_assets():
    result = load_registered_static_assets("v-3aafe09211fd")
    assert result["assetVersion"] == "v-3aafe09211fd"
    assert len(result["entries"]) == 23
    assert len({entry["key"] for entry in result["entries"]}) == 23
    assert {entry["kind"] for entry in result["entries"]} == {
        "game-image",
        "motion-instruction-audio",
    }


@pytest.mark.parametrize("invalid_key", [["pattern_sun"], {"key": "pattern_sun"}])
def test_registered_manifest_with_non_string_key_is_invalid(
    invalid_key, tmp_path, monkeypatch
):
    payload = load_registered_static_assets("v-3aafe09211fd")
    payload["entries"][0]["key"] = invalid_key
    payload["assetVersion"] = "v-damaged"
    manifest_path = tmp_path / "damaged.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setitem(
        miniapp_static_asset_registry.REGISTERED_STATIC_ASSET_MANIFESTS,
        "v-damaged",
        manifest_path,
    )

    with pytest.raises(ValueError):
        load_registered_static_assets("v-damaged")
