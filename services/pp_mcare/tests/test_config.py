import json
import inspect
import stat
import tomllib
from dataclasses import fields
from pathlib import Path
from unittest.mock import patch

import pytest
from motion_analysis_contract import PROTOCOL_VERSION, WorkerCapability

import pp_mcare.config as config_module
from pp_mcare.config import ConfigurationError, Settings


EXPECTED_CAPABILITY = WorkerCapability(
    action_source_key="motion-resistance-shoulder-press",
    algorithm_version="PP-TinyPose_128x96",
    rule_version="shoulder-press-v2",
    parameter_version="shoulder-press-v2-defaults",
)


def valid_env(tmp_path):
    return {
        "PP_MCARE_API_BASE_URL": "https://motioncare.example",
        "PP_MCARE_SERVICE_TOKEN": "machine-secret-123",
        "PP_MCARE_WORKER_ID": "worker-prod-1",
        "PP_MCARE_WORK_ROOT": str(tmp_path / "jobs"),
        "PP_MCARE_MODEL_CACHE": str(tmp_path / "models"),
    }


def from_env(tmp_path, environ, *, operation_hook=None):
    with (
        patch.object(config_module, "_TRUSTED_PATH_BASE", tmp_path),
        patch.object(config_module, "_DIRECTORY_OPERATION_HOOK", operation_hook),
    ):
        return Settings.from_env(environ)


def direct_settings(tmp_path, **overrides):
    values = {
        "api_base_url": "https://motioncare.example",
        "service_token": "machine-secret-123",
        "worker_id": "worker-prod-1",
        "work_root": tmp_path / "jobs",
        "model_cache": tmp_path / "models",
    }
    values.update(overrides)
    with patch.object(config_module, "_TRUSTED_PATH_BASE", tmp_path):
        return Settings(**values)


def test_settings_builds_exact_approved_capability_and_private_work_root(tmp_path):
    settings = from_env(tmp_path, valid_env(tmp_path))

    assert settings.api_base_url == "https://motioncare.example"
    assert settings.protocol_version == PROTOCOL_VERSION
    assert settings.capabilities == (EXPECTED_CAPABILITY,)
    assert settings.poll_interval_seconds == 900
    assert settings.network_attempts == 3
    assert stat.S_IMODE(settings.work_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(settings.model_cache.stat().st_mode) == 0o700


@pytest.mark.parametrize(
    "name",
    [
        "QINIU_ACCESS_KEY",
        "QINIU_SECRET_KEY",
        "DATABASE_URL",
        "REDIS_URL",
        "DJANGO_SECRET_KEY",
    ],
)
@pytest.mark.parametrize("value", ["forbidden", ""])
def test_settings_rejects_long_term_business_secrets_even_when_empty(tmp_path, name, value):
    env = valid_env(tmp_path) | {name: value}

    with pytest.raises(ConfigurationError) as error:
        from_env(tmp_path, env)

    assert value not in str(error.value) if value else True
    assert "machine-secret-123" not in str(error.value)


def test_settings_ignores_unrelated_environment_but_rejects_unknown_worker_key(tmp_path):
    settings = from_env(
        tmp_path,
        valid_env(tmp_path) | {"PATH": "/usr/bin", "LANG": "zh_CN"},
    )
    assert settings.worker_id == "worker-prod-1"

    with pytest.raises(ConfigurationError):
        from_env(
            tmp_path,
            valid_env(tmp_path) | {"PP_MCARE_DATABASE_URL": "postgres://bad"},
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://motioncare.example",
        "https://user:password@motioncare.example",
        "https://motioncare.example/api",
        "https://motioncare.example?token=secret",
        "https://motioncare.example#fragment",
        "https://motioncare.example\\@evil.example",
        "https://",
    ],
)
def test_settings_rejects_non_https_credentials_and_ambiguous_base_urls(tmp_path, base_url):
    env = valid_env(tmp_path) | {"PP_MCARE_API_BASE_URL": base_url}

    with pytest.raises(ConfigurationError) as error:
        from_env(tmp_path, env)

    rendered = repr(error.value)
    assert "machine-secret-123" not in rendered
    assert "token=secret" not in rendered


@pytest.mark.parametrize("worker_id", ["", " worker-1", "worker-1 ", "worker 1", "worker/1"])
def test_settings_rejects_noncanonical_worker_id(tmp_path, worker_id):
    with pytest.raises(ConfigurationError):
        from_env(tmp_path, valid_env(tmp_path) | {"PP_MCARE_WORKER_ID": worker_id})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PP_MCARE_POLL_INTERVAL_SECONDS", ""),
        ("PP_MCARE_POLL_INTERVAL_SECONDS", " 900"),
        ("PP_MCARE_POLL_INTERVAL_SECONDS", "0"),
        ("PP_MCARE_NETWORK_ATTEMPTS", "4"),
        ("PP_MCARE_NETWORK_ATTEMPTS", "3.0"),
        ("PP_MCARE_CONNECT_TIMEOUT_SECONDS", "0"),
        ("PP_MCARE_READ_TIMEOUT_SECONDS", "-1"),
    ],
)
def test_settings_parses_environment_numbers_fail_closed(tmp_path, name, value):
    with pytest.raises(ConfigurationError):
        from_env(tmp_path, valid_env(tmp_path) | {name: value})


@pytest.mark.parametrize(
    "capabilities",
    [
        [],
        [
            {
                "action_source_key": "motion-resistance-shoulder-press",
                "algorithm_version": "PP-TinyPose_128x96",
                "rule_version": "shoulder-press-v2 ",
                "parameter_version": "shoulder-press-v2-defaults",
            }
        ],
        [EXPECTED_CAPABILITY.to_dict(), EXPECTED_CAPABILITY.to_dict()],
        [{**EXPECTED_CAPABILITY.to_dict(), "protocol_version": "2"}],
        [{**EXPECTED_CAPABILITY.to_dict(), "algorithm_version": "PP-TinyPose_192x256"}],
    ],
)
def test_settings_rejects_empty_duplicate_whitespace_or_wrong_explicit_capabilities(
    tmp_path,
    capabilities,
):
    env = valid_env(tmp_path) | {
        "PP_MCARE_CAPABILITIES": json.dumps(capabilities, separators=(",", ":")),
    }

    with pytest.raises(ConfigurationError):
        from_env(tmp_path, env)


def test_settings_accepts_only_the_exact_explicit_approved_capability(tmp_path):
    env = valid_env(tmp_path) | {
        "PP_MCARE_CAPABILITIES": json.dumps([EXPECTED_CAPABILITY.to_dict()]),
    }

    assert from_env(tmp_path, env).capabilities == (EXPECTED_CAPABILITY,)


def test_settings_repr_never_contains_machine_token(tmp_path):
    settings = from_env(tmp_path, valid_env(tmp_path))

    assert "machine-secret-123" not in repr(settings)
    assert "<redacted>" in repr(settings)


@pytest.mark.parametrize("field_name", ["PP_MCARE_WORK_ROOT", "PP_MCARE_MODEL_CACHE"])
def test_settings_rejects_parent_and_leaf_symlinks(tmp_path, field_name):
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    parent_link = trusted / "linked-parent"
    parent_link.symlink_to(outside, target_is_directory=True)
    env = valid_env(trusted)
    env[field_name] = str(parent_link / "child")

    with pytest.raises(ConfigurationError):
        from_env(trusted, env)

    leaf_link = trusted / "leaf-link"
    leaf_link.symlink_to(outside, target_is_directory=True)
    env[field_name] = str(leaf_link)
    with pytest.raises(ConfigurationError):
        from_env(trusted, env)


@pytest.mark.parametrize("field_name", ["PP_MCARE_WORK_ROOT", "PP_MCARE_MODEL_CACHE"])
def test_settings_rejects_file_placeholder_at_directory_path(tmp_path, field_name):
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    placeholder = trusted / "not-a-directory"
    placeholder.write_text("private")
    env = valid_env(trusted)
    env[field_name] = str(placeholder)

    with pytest.raises(ConfigurationError):
        from_env(trusted, env)


def test_settings_rejects_path_outside_explicit_trusted_base(tmp_path):
    trusted = tmp_path / "trusted"
    env = valid_env(trusted)
    env["PP_MCARE_MODEL_CACHE"] = str(tmp_path / "outside" / "models")

    with pytest.raises(ConfigurationError):
        from_env(trusted, env)


def test_settings_detects_mkdir_replacement_race_without_following_link(tmp_path):
    trusted = tmp_path / "trusted"
    outside = tmp_path / "outside"
    outside.mkdir()
    raced_leaf = trusted / "jobs"

    def replace_created_directory(path):
        if path == raced_leaf:
            path.rmdir()
            path.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ConfigurationError):
        from_env(
            trusted,
            valid_env(trusted),
            operation_hook=replace_created_directory,
        )

    assert raced_leaf.is_symlink()
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"api_base_url": "http://motioncare.example"},
        {"service_token": "bad token"},
        {"worker_id": "worker/unsafe"},
        {"poll_interval_seconds": 0},
        {"network_attempts": 4},
        {"connect_timeout_seconds": True},
        {"read_timeout_seconds": -1},
        {"write_timeout_seconds": 0},
        {"pool_timeout_seconds": 0},
        {"protocol_version": "2"},
        {"capabilities": ()},
        {
            "capabilities": (
                WorkerCapability(
                    action_source_key="motion-resistance-shoulder-press",
                    algorithm_version="wrong",
                    rule_version="shoulder-press-v2",
                    parameter_version="shoulder-press-v2-defaults",
                ),
            )
        },
    ],
)
def test_direct_settings_constructor_cannot_bypass_validation(tmp_path, overrides):
    with pytest.raises(ConfigurationError):
        direct_settings(tmp_path, **overrides)


def test_direct_settings_constructor_rejects_path_outside_trusted_root(tmp_path):
    with pytest.raises(ConfigurationError):
        direct_settings(tmp_path, model_cache=tmp_path.parent / "outside-models")


def test_package_metadata_targets_python_312_and_paddlex_supported_cv_bundle():
    pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject_path.read_text())["project"]
    inference = project["optional-dependencies"]["inference"]

    assert project["requires-python"] == ">=3.12,<3.13"
    assert "paddlepaddle==3.3.0" in inference
    assert "paddlex[cv]==3.7.2" in inference
    assert not any(requirement.lower().startswith("opencv-") for requirement in inference)
    assert "numpy>=1.26,<2.4" in project["optional-dependencies"]["dev"]


def test_trusted_root_and_race_hook_are_not_public_settings_inputs(tmp_path):
    forbidden = {"_trusted_path_base", "_path_operation_hook"}

    assert forbidden.isdisjoint(inspect.signature(Settings).parameters)
    assert forbidden.isdisjoint(inspect.signature(Settings.from_env).parameters)
    assert forbidden.isdisjoint(field.name for field in fields(Settings))
    assert config_module._TRUSTED_PATH_BASE == Path("/opt/motioncare-analysis")

    configured = from_env(tmp_path, valid_env(tmp_path))
    assert all(name not in repr(configured) for name in forbidden)

    for name in forbidden:
        with pytest.raises(TypeError):
            Settings(
                api_base_url="https://motioncare.example",
                service_token="machine-secret-123",
                worker_id="worker-prod-1",
                **{name: tmp_path},
            )
        with pytest.raises(TypeError):
            Settings.from_env(valid_env(tmp_path), **{name: tmp_path})
