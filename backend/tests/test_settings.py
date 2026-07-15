from django.conf import settings


def test_local_vite_origins_are_trusted_for_csrf():
    assert "http://127.0.0.1:5173" in settings.CSRF_TRUSTED_ORIGINS
    assert "http://localhost:5173" in settings.CSRF_TRUSTED_ORIGINS


def test_reverse_proxy_and_static_settings_are_production_ready():
    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert settings.STATIC_URL == "/static/"
    assert settings.STATIC_ROOT.name == "staticfiles"
