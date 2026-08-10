import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from dotenv import dotenv_values

from config.environment import env_bool


def test_env_bool_defaults_to_false_when_variable_is_unset(monkeypatch):
    monkeypatch.delenv("TRAINING_HEALTH_ENFORCE_ROW_SCOPE", raising=False)

    assert env_bool("TRAINING_HEALTH_ENFORCE_ROW_SCOPE") is False


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("  TrUe  ", True),
        ("false", False),
        ("FALSE", False),
        ("  FaLsE  ", False),
    ],
)
def test_env_bool_accepts_trimmed_case_insensitive_boolean_values(
    monkeypatch,
    raw_value,
    expected,
):
    monkeypatch.setenv("TRAINING_HEALTH_ENFORCE_ROW_SCOPE", raw_value)

    assert env_bool("TRAINING_HEALTH_ENFORCE_ROW_SCOPE") is expected


@pytest.mark.parametrize("raw_value", ["", "   ", "tru", "1", "yes"])
def test_env_bool_rejects_unknown_values(monkeypatch, raw_value):
    variable_name = "TRAINING_HEALTH_ENFORCE_ROW_SCOPE"
    monkeypatch.setenv(variable_name, raw_value)

    with pytest.raises(ImproperlyConfigured) as exc_info:
        env_bool(variable_name)

    message = str(exc_info.value)
    assert variable_name in message
    assert "true" in message
    assert "false" in message


def test_env_bool_does_not_echo_unknown_environment_value(monkeypatch):
    variable_name = "TRAINING_HEALTH_ENFORCE_ROW_SCOPE"
    sensitive_value = "secret-looking-value"
    monkeypatch.setenv(variable_name, sensitive_value)

    with pytest.raises(ImproperlyConfigured) as exc_info:
        env_bool(variable_name)

    assert sensitive_value not in str(exc_info.value)


def test_local_vite_origins_are_trusted_for_csrf():
    assert "http://127.0.0.1:5173" in settings.CSRF_TRUSTED_ORIGINS
    assert "http://localhost:5173" in settings.CSRF_TRUSTED_ORIGINS


def test_reverse_proxy_and_static_settings_are_production_ready():
    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert settings.STATIC_URL == "/static/"
    assert settings.STATIC_ROOT.name == "staticfiles"


def test_training_video_limits_support_raw_five_second_forty_minute_sessions():
    assert settings.TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES == 80 * 1024 * 1024
    assert settings.TRAINING_VIDEO_MAX_DURATION_SECONDS == 2400
    assert settings.TRAINING_VIDEO_MAX_SEGMENTS == 600
    assert settings.MOTION_ANALYSIS_DOWNLOAD_DEADLINE_SECONDS == 900
    assert settings.MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS == 7200
    assert not hasattr(settings, "TRAINING_VIDEO_MAX_SIZE_BYTES")


def test_wearable_sync_uses_shanghai_timezone_and_https_provider():
    assert settings.TIME_ZONE == "Asia/Shanghai"
    assert settings.CELERY_TIMEZONE == "Asia/Shanghai"
    assert "apps.wearables" in settings.INSTALLED_APPS
    assert settings.MIWITRACKER_BASE_URL.startswith("https://")


def test_wearable_provider_examples_declare_only_safe_placeholders():
    for example_path in (
        settings.ROOT_DIR / ".env.example",
        settings.ROOT_DIR / "deploy" / "env.production.example",
    ):
        values = dotenv_values(example_path)

        assert values["MIWITRACKER_BASE_URL"].startswith("https://")
        assert values["MIWITRACKER_APP_ID"] == ""
        assert values["MIWITRACKER_KEY"] == ""
