from django.conf import settings


def test_local_vite_origins_are_trusted_for_csrf():
    assert "http://127.0.0.1:5173" in settings.CSRF_TRUSTED_ORIGINS
    assert "http://localhost:5173" in settings.CSRF_TRUSTED_ORIGINS
