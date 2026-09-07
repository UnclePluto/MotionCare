import pytest

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
