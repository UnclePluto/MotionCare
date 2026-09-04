import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.common import miniapp_static_assets as assets


EXPECTED_KEYS = [
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
]

CANONICAL_ASSET_SPECS = {
    key: (
        ("motion-instruction-audio", "audio/mp4", "m4a")
        if key.startswith("motion-")
        else ("game-image", "image/webp", "webp")
    )
    for key in EXPECTED_KEYS
}


def _write_manifest(source_root: Path, payload: dict) -> None:
    (source_root / "manifest.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def static_asset_fixture(tmp_path: Path) -> Path:
    source_root = tmp_path / "v-fixture"
    source_root.mkdir()
    entries = []
    for index, key in enumerate(EXPECTED_KEYS):
        kind, content_type, suffix = CANONICAL_ASSET_SPECS[key]
        body = f"fixture-{index}-{key}".encode()
        filename = f"{key}.{hashlib.sha256(body).hexdigest()[:12]}.{suffix}"
        (source_root / filename).write_bytes(body)
        entries.append(
            {
                "kind": kind,
                "key": key,
                "contentType": content_type,
                "sizeBytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "relativePath": f"{source_root.name}/{filename}",
            }
        )
    _write_manifest(
        source_root,
        {"assetVersion": source_root.name, "entries": entries},
    )
    return source_root


def _manifest(source_root: Path) -> dict:
    return json.loads((source_root / "manifest.json").read_text(encoding="utf-8"))


def _matching_metadata(*, object_hash: str = "local-etag", size: int) -> dict:
    return {"hash": object_hash, "fsize": size, "mimeType": "image/webp"}


def test_manifest_requires_all_23_canonical_assets(tmp_path):
    source_root = static_asset_fixture(tmp_path)
    manifest = _manifest(source_root)
    manifest["entries"].pop()
    _write_manifest(source_root, manifest)

    with pytest.raises(CommandError, match="23 项"):
        assets.validate_miniapp_static_assets(source_root)


@pytest.mark.parametrize(
    "missing_field", ["kind", "key", "contentType", "sizeBytes", "sha256", "relativePath"]
)
def test_manifest_entry_requires_every_publish_field(tmp_path, missing_field):
    source_root = static_asset_fixture(tmp_path)
    manifest = _manifest(source_root)
    manifest["entries"][0].pop(missing_field)
    _write_manifest(source_root, manifest)

    with pytest.raises(CommandError, match="清单项缺少字段"):
        assets.validate_miniapp_static_assets(source_root)


@pytest.mark.parametrize(
    "relative_path",
    [
        "/tmp/outside.webp",
        "../outside.webp",
        "v-fixture/../outside.webp",
        "other-version/asset.webp",
    ],
)
def test_manifest_rejects_absolute_traversal_and_wrong_version_paths(
    tmp_path, relative_path
):
    source_root = static_asset_fixture(tmp_path)
    manifest = _manifest(source_root)
    manifest["entries"][0]["relativePath"] = relative_path
    _write_manifest(source_root, manifest)

    with pytest.raises(CommandError, match="素材路径"):
        assets.validate_miniapp_static_assets(source_root)


def test_manifest_rejects_a_symlink_that_escapes_the_version_directory(tmp_path):
    source_root = static_asset_fixture(tmp_path)
    manifest = _manifest(source_root)
    relative_path = manifest["entries"][0]["relativePath"]
    asset_path = source_root.parent / relative_path
    asset_path.unlink()
    outside = tmp_path / "outside.webp"
    outside.write_bytes(b"outside")
    asset_path.symlink_to(outside)

    with pytest.raises(CommandError, match="素材路径"):
        assets.validate_miniapp_static_assets(source_root)


def test_manifest_sha256_must_match_local_response_bytes(tmp_path):
    source_root = static_asset_fixture(tmp_path)
    manifest = _manifest(source_root)
    original_path = source_root.parent / manifest["entries"][0]["relativePath"]
    manifest["entries"][0]["sha256"] = "0" * 64
    manifest["entries"][0]["relativePath"] = (
        f"{source_root.name}/{manifest['entries'][0]['key']}.{'0' * 12}.webp"
    )
    original_path.rename(source_root.parent / manifest["entries"][0]["relativePath"])
    _write_manifest(source_root, manifest)

    with pytest.raises(CommandError, match="SHA-256"):
        assets.validate_miniapp_static_assets(source_root)


def test_manifest_size_must_match_local_response_bytes(tmp_path):
    source_root = static_asset_fixture(tmp_path)
    manifest = _manifest(source_root)
    manifest["entries"][0]["sizeBytes"] += 1
    _write_manifest(source_root, manifest)

    with pytest.raises(CommandError, match="字节数"):
        assets.validate_miniapp_static_assets(source_root)


def test_manifest_rejects_an_unapproved_media_type(tmp_path):
    source_root = static_asset_fixture(tmp_path)
    manifest = _manifest(source_root)
    manifest["entries"][0]["contentType"] = "image/png"
    _write_manifest(source_root, manifest)

    with pytest.raises(CommandError, match="媒体类型"):
        assets.validate_miniapp_static_assets(source_root)


def test_manifest_rejects_a_canonical_key_classified_as_the_other_asset_type(
    tmp_path,
):
    source_root = static_asset_fixture(tmp_path)
    manifest = _manifest(source_root)
    manifest["entries"][0]["kind"] = "motion-instruction-audio"
    manifest["entries"][0]["contentType"] = "audio/mp4"
    _write_manifest(source_root, manifest)

    with pytest.raises(CommandError, match="规范类型"):
        assets.validate_miniapp_static_assets(source_root)


def test_manifest_rejects_a_duplicate_key_even_when_entry_count_stays_23(tmp_path):
    source_root = static_asset_fixture(tmp_path)
    manifest = _manifest(source_root)
    manifest["entries"][-1]["key"] = manifest["entries"][0]["key"]
    _write_manifest(source_root, manifest)

    with pytest.raises(CommandError, match="23 项规范素材"):
        assets.validate_miniapp_static_assets(source_root)


def test_manifest_rejects_an_unknown_key_even_when_entry_count_stays_23(tmp_path):
    source_root = static_asset_fixture(tmp_path)
    manifest = _manifest(source_root)
    manifest["entries"][-1]["key"] = "unknown-static-asset"
    _write_manifest(source_root, manifest)

    with pytest.raises(CommandError, match="23 项规范素材"):
        assets.validate_miniapp_static_assets(source_root)


def _move_first_fixture_asset(source_root: Path, relative_path: str) -> None:
    manifest = _manifest(source_root)
    original_path = source_root.parent / manifest["entries"][0]["relativePath"]
    replacement_path = source_root.parent / relative_path
    replacement_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.rename(replacement_path)
    manifest["entries"][0]["relativePath"] = relative_path
    _write_manifest(source_root, manifest)


@pytest.mark.parametrize(
    "relative_path_builder",
    [
        lambda version, key, prefix: f"{version}/nested/{key}.{prefix}.webp",
        lambda version, _key, prefix: f"{version}/wrong-business-key.{prefix}.webp",
        lambda version, key, prefix: f"{version}/{key}.extra.{prefix}.webp",
        lambda version, key, prefix: f"{version}/{key}.000000000000.{prefix}.webp",
        lambda version, key, prefix: f"{version}/{key}.{prefix}.m4a",
        lambda version, key, prefix: f"{version}/./{key}.{prefix}.webp",
        lambda version, key, prefix: f"{version}/%2e/{key}.{prefix}.webp",
        lambda version, key, prefix: f"{version}/%252e/{key}.{prefix}.webp",
        lambda version, key, prefix: f"{version}/%2e%2e/{key}.{prefix}.webp",
        lambda version, key, prefix: f"{version}/%252e%252e/{key}.{prefix}.webp",
        lambda version, key, prefix: f"{version}/{key}%2fescape.{prefix}.webp",
        lambda version, key, prefix: f"{version}/{key}%252fescape.{prefix}.webp",
        lambda version, key, prefix: f"{version}/{key}%ZZ.{prefix}.webp",
    ],
)
def test_manifest_requires_the_exact_canonical_two_segment_relative_path(
    tmp_path, relative_path_builder
):
    source_root = static_asset_fixture(tmp_path)
    manifest = _manifest(source_root)
    first = manifest["entries"][0]
    relative_path = relative_path_builder(
        source_root.name,
        first["key"],
        first["sha256"][:12],
    )
    _move_first_fixture_asset(source_root, relative_path)

    with pytest.raises(CommandError, match="规范路径"):
        assets.validate_miniapp_static_assets(source_root)


def test_relative_path_is_resolved_from_source_root_parent_without_repeating_version(
    tmp_path,
):
    source_root = static_asset_fixture(tmp_path)

    prepared = assets.validate_miniapp_static_assets(source_root)

    assert prepared[0].path.parent == source_root.resolve()
    assert prepared[0].object_key.startswith(
        f"motioncare/static-assets/{source_root.name}/"
    )
    assert f"/{source_root.name}/{source_root.name}/" not in prepared[0].object_key


def test_matching_remote_objects_are_reported_as_existing_without_upload(
    tmp_path, monkeypatch
):
    source_root = static_asset_fixture(tmp_path)
    entries_by_path = {
        entry["relativePath"]: entry for entry in _manifest(source_root)["entries"]
    }

    def matching_stat(*, bucket, key):
        relative_path = key.removeprefix("motioncare/static-assets/")
        entry = entries_by_path[relative_path]
        return {
            "hash": "local-etag",
            "fsize": entry["sizeBytes"],
            "mimeType": entry["contentType"],
        }

    stat = Mock(side_effect=matching_stat)
    upload = Mock()
    monkeypatch.setattr(assets.qiniu, "etag", lambda path: "local-etag")
    monkeypatch.setattr(assets, "stat_object_metadata_or_none", stat)
    monkeypatch.setattr(assets, "upload_static_asset", upload)

    published = assets.publish_miniapp_static_assets(source_root)

    assert [item.status for item in published] == ["existing"] * 23
    upload.assert_not_called()


def test_missing_remote_objects_are_uploaded_with_insert_only_and_revalidated(
    tmp_path, monkeypatch
):
    source_root = static_asset_fixture(tmp_path)
    entries = _manifest(source_root)["entries"]
    metadata = [
        {
            "hash": "local-etag",
            "fsize": entry["sizeBytes"],
            "mimeType": entry["contentType"],
        }
        for entry in entries
    ]
    stat = Mock(side_effect=[value for item in metadata for value in (None, item)])
    upload = Mock()
    monkeypatch.setattr(assets.qiniu, "etag", lambda path: "local-etag")
    monkeypatch.setattr(assets, "stat_object_metadata_or_none", stat)
    monkeypatch.setattr(assets, "upload_static_asset", upload)

    published = assets.publish_miniapp_static_assets(source_root)

    assert [item.status for item in published] == ["uploaded"] * 23
    assert [call.kwargs["content_type"] for call in upload.call_args_list] == [
        entry["contentType"] for entry in entries
    ]
    assert stat.call_count == 46


def test_concurrent_insert_only_publish_accepts_the_new_matching_remote_object(
    tmp_path, monkeypatch
):
    source_root = static_asset_fixture(tmp_path)
    entries_by_path = {
        entry["relativePath"]: entry for entry in _manifest(source_root)["entries"]
    }
    first_key = f"motioncare/static-assets/{next(iter(entries_by_path))}"
    first_calls = 0

    def stat_after_concurrent_publish(*, bucket, key):
        nonlocal first_calls
        if key == first_key:
            first_calls += 1
            if first_calls == 1:
                return None
        relative_path = key.removeprefix("motioncare/static-assets/")
        entry = entries_by_path[relative_path]
        return {
            "hash": "local-etag",
            "fsize": entry["sizeBytes"],
            "mimeType": entry["contentType"],
        }

    monkeypatch.setattr(assets.qiniu, "etag", lambda path: "local-etag")
    monkeypatch.setattr(
        assets, "stat_object_metadata_or_none", Mock(side_effect=stat_after_concurrent_publish)
    )
    monkeypatch.setattr(
        assets,
        "upload_static_asset",
        Mock(side_effect=CommandError("insertOnly conflict")),
    )

    published = assets.publish_miniapp_static_assets(source_root)

    assert [item.status for item in published] == ["existing"] * 23


@pytest.mark.parametrize(
    "remote_override",
    [
        {"hash": "other-etag"},
        {"fsize": 123},
        {"mimeType": "image/png"},
    ],
)
def test_conflicting_remote_object_is_rejected_without_overwrite(
    tmp_path, monkeypatch, remote_override
):
    source_root = static_asset_fixture(tmp_path)
    first_size = _manifest(source_root)["entries"][0]["sizeBytes"]
    remote = _matching_metadata(size=first_size) | remote_override
    upload = Mock()
    monkeypatch.setattr(assets.qiniu, "etag", lambda path: "local-etag")
    monkeypatch.setattr(
        assets, "stat_object_metadata_or_none", Mock(return_value=remote)
    )
    monkeypatch.setattr(assets, "upload_static_asset", upload)

    with pytest.raises(CommandError, match="远端固定素材冲突"):
        assets.publish_miniapp_static_assets(source_root)

    upload.assert_not_called()


@pytest.mark.parametrize("failure_point", ["initial_stat", "upload", "post_upload_stat"])
def test_qiniu_errors_do_not_leak_access_or_secret_keys(
    tmp_path, monkeypatch, caplog, failure_point
):
    source_root = static_asset_fixture(tmp_path)
    secret = "AK-private SK-private"
    stat = Mock()
    upload = Mock()
    if failure_point == "initial_stat":
        stat.side_effect = RuntimeError(secret)
    elif failure_point == "upload":
        stat.return_value = None
        upload.side_effect = RuntimeError(secret)
    else:
        stat.side_effect = [None, RuntimeError(secret)]
    monkeypatch.setattr(assets.qiniu, "etag", lambda path: "local-etag")
    monkeypatch.setattr(assets, "stat_object_metadata_or_none", stat)
    monkeypatch.setattr(assets, "upload_static_asset", upload)

    with pytest.raises(CommandError, match="固定素材远端操作失败") as exc_info:
        assets.publish_miniapp_static_assets(source_root)

    assert secret not in str(exc_info.value)
    assert secret not in caplog.text


def test_upload_uses_insert_only_and_explicit_manifest_media_type(
    tmp_path, monkeypatch, settings
):
    source_root = static_asset_fixture(tmp_path)
    prepared = assets.validate_miniapp_static_assets(source_root)[0]
    settings.QINIU_ACCESS_KEY = "test-ak"
    settings.QINIU_SECRET_KEY = "test-sk"
    settings.QINIU_BUCKET = "test-bucket"
    upload_token = Mock(return_value="test-token")
    auth = Mock(upload_token=upload_token)
    monkeypatch.setattr(assets.qiniu, "Auth", Mock(return_value=auth))
    put_file = Mock(
        return_value=(
            {"key": prepared.object_key, "hash": prepared.qiniu_hash},
            Mock(status_code=200),
        )
    )
    monkeypatch.setattr(assets.qiniu, "put_file", put_file)

    assets.upload_static_asset(
        path=prepared.path,
        object_key=prepared.object_key,
        content_type=prepared.content_type,
        expected_qiniu_hash=prepared.qiniu_hash,
    )

    upload_token.assert_called_once_with(
        "test-bucket",
        prepared.object_key,
        3600,
        policy={"insertOnly": 1},
    )
    assert put_file.call_args.kwargs["mime_type"] == "image/webp"


def test_check_only_validates_locally_without_qiniu_network_operations(
    tmp_path, monkeypatch, capsys
):
    source_root = static_asset_fixture(tmp_path)
    stat = Mock()
    upload = Mock()
    monkeypatch.setattr(assets, "stat_object_metadata_or_none", stat)
    monkeypatch.setattr(assets, "upload_static_asset", upload)

    call_command(
        "publish_miniapp_static_assets",
        "--source-root",
        str(source_root),
        "--check-only",
    )

    output = capsys.readouterr().out
    assert output.count("本地已校验") == 23
    stat.assert_not_called()
    upload.assert_not_called()


def test_public_api_has_no_destructive_storage_operation():
    assert set(assets.__all__) == {
        "PreparedStaticAsset",
        "PublishedStaticAsset",
        "publish_miniapp_static_assets",
        "upload_static_asset",
        "validate_miniapp_static_assets",
    }
    assert all(
        destructive_word not in exported_name.lower()
        for exported_name in assets.__all__
        for destructive_word in ("delete", "remove", "overwrite")
    )
