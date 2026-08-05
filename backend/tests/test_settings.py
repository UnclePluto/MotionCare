from django.conf import settings
from dotenv import dotenv_values


def test_local_vite_origins_are_trusted_for_csrf():
    assert "http://127.0.0.1:5173" in settings.CSRF_TRUSTED_ORIGINS
    assert "http://localhost:5173" in settings.CSRF_TRUSTED_ORIGINS


def test_reverse_proxy_and_static_settings_are_production_ready():
    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert settings.STATIC_URL == "/static/"
    assert settings.STATIC_ROOT.name == "staticfiles"


def test_training_video_limits_support_raw_fifteen_second_forty_minute_sessions():
    assert settings.TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES == 80 * 1024 * 1024
    assert settings.TRAINING_VIDEO_MAX_DURATION_SECONDS == 2400
    assert settings.TRAINING_VIDEO_MAX_SEGMENTS == 200
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
