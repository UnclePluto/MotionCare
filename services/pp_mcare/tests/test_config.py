import json
import stat

import pytest
from motion_analysis_contract import PROTOCOL_VERSION, WorkerCapability

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


def test_settings_builds_exact_approved_capability_and_private_work_root(tmp_path):
    settings = Settings.from_env(valid_env(tmp_path))

    assert settings.api_base_url == "https://motioncare.example"
    assert settings.protocol_version == PROTOCOL_VERSION
    assert settings.capabilities == (EXPECTED_CAPABILITY,)
    assert settings.poll_interval_seconds == 900
    assert settings.network_attempts == 3
    assert stat.S_IMODE(settings.work_root.stat().st_mode) == 0o700


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
        Settings.from_env(env)

    assert value not in str(error.value) if value else True
    assert "machine-secret-123" not in str(error.value)


def test_settings_ignores_unrelated_environment_but_rejects_unknown_worker_key(tmp_path):
    settings = Settings.from_env(valid_env(tmp_path) | {"PATH": "/usr/bin", "LANG": "zh_CN"})
    assert settings.worker_id == "worker-prod-1"

    with pytest.raises(ConfigurationError):
        Settings.from_env(valid_env(tmp_path) | {"PP_MCARE_DATABASE_URL": "postgres://bad"})


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
        Settings.from_env(env)

    rendered = repr(error.value)
    assert "machine-secret-123" not in rendered
    assert "token=secret" not in rendered


@pytest.mark.parametrize("worker_id", ["", " worker-1", "worker-1 ", "worker 1", "worker/1"])
def test_settings_rejects_noncanonical_worker_id(tmp_path, worker_id):
    with pytest.raises(ConfigurationError):
        Settings.from_env(valid_env(tmp_path) | {"PP_MCARE_WORKER_ID": worker_id})


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
        Settings.from_env(valid_env(tmp_path) | {name: value})


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
        Settings.from_env(env)


def test_settings_accepts_only_the_exact_explicit_approved_capability(tmp_path):
    env = valid_env(tmp_path) | {
        "PP_MCARE_CAPABILITIES": json.dumps([EXPECTED_CAPABILITY.to_dict()]),
    }

    assert Settings.from_env(env).capabilities == (EXPECTED_CAPABILITY,)


def test_settings_repr_never_contains_machine_token(tmp_path):
    settings = Settings.from_env(valid_env(tmp_path))

    assert "machine-secret-123" not in repr(settings)
    assert "<redacted>" in repr(settings)
