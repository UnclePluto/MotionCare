import hashlib
import json
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.checks import run_checks
from django.core.management import call_command

from apps.crf import registry_loader
from apps.crf.registry_validate import (
    validate_patient_baseline_payload,
    validate_visit_form_data_patch,
)

SOURCE_SHA256 = "f031dd59a1e169548fe651555d19c41306cc51e6bfcf7eb933edcee86924102a"


def test_missing_registry_identifies_exact_path(tmp_path):
    missing = tmp_path / "missing-registry.json"
    with pytest.raises(registry_loader.CrfAssetError, match=str(missing)):
        registry_loader.check_crf_assets(registry_path=missing)


def test_runtime_assets_load_without_database(django_db_blocker):
    with django_db_blocker.block():
        assets = registry_loader.check_crf_assets()
        registry = registry_loader.load_crf_registry(force_reload=True)
        assert registry["template_revision"] == "1.1"
        assert assets["template_revision"] == "1.1"
        assert assets["registry_exists"] is True
        assert assets["template_exists"] is True
        assert assets["template_sha256"] == SOURCE_SHA256
        assert (
            assets["registry_sha256"]
            == hashlib.sha256(Path(assets["registry_path"]).read_bytes()).hexdigest()
        )
        assert validate_patient_baseline_payload({"subject_id": "MC-ASSET-CHECK"}) == {}
        assert validate_visit_form_data_patch({}, "T0") == {}


def test_missing_template_identifies_exact_path(tmp_path):
    missing = tmp_path / "missing-template.docx"
    with pytest.raises(registry_loader.CrfAssetError, match=str(missing)):
        registry_loader.check_crf_assets(template_path=missing)


@pytest.mark.parametrize(
    ("key", "wrong_value"),
    [("template_revision", "1.0"), ("source_docx_sha256", "0" * 64)],
)
def test_registry_with_incompatible_template_is_rejected(tmp_path, key, wrong_value):
    registry = json.loads(registry_loader._registry_path().read_text(encoding="utf-8"))
    registry[key] = wrong_value
    path = tmp_path / "incompatible-registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(registry_loader.CrfAssetError, match=str(path)):
        registry_loader.check_crf_assets(registry_path=path)


def test_modified_template_is_rejected(tmp_path):
    template = tmp_path / "modified-template.docx"
    template.write_bytes(Path(settings.CRF_TEMPLATE_PATH).read_bytes() + b"modified")
    with pytest.raises(registry_loader.CrfAssetError, match=str(template)):
        registry_loader.check_crf_assets(template_path=template)


def test_malformed_registry_identifies_exact_path(tmp_path):
    registry = tmp_path / "invalid-registry.json"
    registry.write_text("not json", encoding="utf-8")
    with pytest.raises(registry_loader.CrfAssetError, match=str(registry)):
        registry_loader.check_crf_assets(registry_path=registry)


def test_loader_uses_configured_registry_path(settings, tmp_path):
    settings.CRF_REGISTRY_PATH = tmp_path / "missing-runtime-registry.json"
    with pytest.raises(registry_loader.CrfAssetError, match=str(settings.CRF_REGISTRY_PATH)):
        registry_loader.load_crf_registry(force_reload=True)


def test_management_command_checks_assets_without_database(django_db_blocker):
    output = StringIO()
    with django_db_blocker.block():
        call_command("check_crf_assets", stdout=output)
    result = json.loads(output.getvalue())
    assert result["template_revision"] == "1.1"
    assert result["template_sha256"] == SOURCE_SHA256


def test_system_check_reports_missing_registry(settings, tmp_path):
    settings.CRF_REGISTRY_PATH = tmp_path / "missing-runtime-registry.json"
    errors = run_checks(tags=["crf_assets"])
    assert len(errors) == 1
    assert errors[0].id == "crf.E001"
    assert str(settings.CRF_REGISTRY_PATH) in errors[0].msg


def test_application_startup_rejects_missing_assets(tmp_path):
    import os
    import subprocess
    import sys

    missing = tmp_path / "missing-startup-registry.json"
    environment = os.environ | {
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "CRF_REGISTRY_PATH": str(missing),
        "DATABASE_URL": "postgresql://unreachable:unreachable@127.0.0.1:1/unreachable",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert str(missing) in result.stderr


def test_missing_source_manifest_is_rejected_at_startup_check(tmp_path):
    registry = tmp_path / "registry.v1.json"
    registry.write_bytes(Path(settings.CRF_REGISTRY_PATH).read_bytes())
    with pytest.raises(registry_loader.CrfAssetError, match="source_slots.v1.json"):
        registry_loader.check_crf_assets(registry_path=registry)


def test_source_manifest_is_read_from_registry_directory_and_verified(tmp_path):
    registry = tmp_path / "registry.v1.json"
    registry.write_bytes(Path(settings.CRF_REGISTRY_PATH).read_bytes())
    source = tmp_path / "source_slots.v1.json"
    source.write_bytes((Path(settings.CRF_REGISTRY_PATH).parent / source.name).read_bytes())
    result = registry_loader.load_crf_source_slots(registry_path=registry)
    assert len(result["slots"]) == 561
    assert result["index_space"] == "xml_tc"
    value = json.loads(source.read_text())
    value["slots"][0]["row_index"] += 1
    source.write_text(json.dumps(value))
    with pytest.raises(registry_loader.CrfAssetError, match="source_slots.v1.json"):
        registry_loader.check_crf_assets(registry_path=registry)
