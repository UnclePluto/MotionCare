from collections import defaultdict

import pytest

from apps.patient_app.throttles import RedisFixedWindowRateThrottle


class FakeRedis:
    def __init__(self):
        self.counts = defaultdict(int)
        self.keys = []

    def eval(self, script, key_count, base_key, window_seconds):
        assert "TIME" in script
        assert key_count == 1
        assert int(window_seconds) == 60
        self.keys.append(base_key)
        self.counts[base_key] += 1
        return self.counts[base_key]


@pytest.fixture(autouse=True)
def static_asset_settings(settings):
    settings.QINIU_ACCESS_KEY = "test-access-key"
    settings.QINIU_SECRET_KEY = "test-secret-key"
    settings.MINIAPP_STATIC_ASSET_BASE_URL = (
        "https://cdn.example.com/motioncare/static-assets"
    )
    settings.MINIAPP_STATIC_ASSET_URL_TTL_SECONDS = 600


@pytest.fixture
def isolated_rate_limit(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(
        RedisFixedWindowRateThrottle,
        "redis_client_factory",
        staticmethod(lambda _url: redis),
    )
    return redis


def test_static_manifest_rejects_request_61_without_signing(
    client, isolated_rate_limit, monkeypatch
):
    signed_calls = 0

    def build_manifest(version):
        nonlocal signed_calls
        signed_calls += 1
        return {"asset_version": version, "issued_at": 1, "expires_at": 601, "assets": []}

    monkeypatch.setattr(
        "apps.patient_app.static_asset_views.build_signed_static_asset_manifest",
        build_manifest,
    )

    responses = [
        client.get(
            "/api/patient-app/static-assets/?version=v-3aafe09211fd",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_REAL_IP="198.51.100.8",
        )
        for _ in range(61)
    ]

    assert [response.status_code for response in responses[:60]] == [200] * 60
    assert responses[60].status_code == 429
    assert signed_calls == 60
    assert len(set(isolated_rate_limit.keys)) == 1


def test_static_manifest_ignores_forged_x_forwarded_for(
    client, isolated_rate_limit, monkeypatch
):
    monkeypatch.setattr(
        "apps.patient_app.static_asset_views.build_signed_static_asset_manifest",
        lambda version: {"asset_version": version, "assets": []},
    )

    for request_number in range(60):
        response = client.get(
            "/api/patient-app/static-assets/?version=v-3aafe09211fd",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_REAL_IP="198.51.100.19",
            HTTP_X_FORWARDED_FOR=f"203.0.113.{request_number % 250}",
        )
        assert response.status_code == 200

    rejected = client.get(
        "/api/patient-app/static-assets/?version=v-3aafe09211fd",
        REMOTE_ADDR="127.0.0.1",
        HTTP_X_REAL_IP="198.51.100.19",
        HTTP_X_FORWARDED_FOR="192.0.2.200",
    )

    assert rejected.status_code == 429
    assert len(set(isolated_rate_limit.keys)) == 1


def test_static_manifest_returns_safe_503_when_redis_is_unavailable(client, monkeypatch):
    def fail_to_connect(_url):
        raise RuntimeError("redis://user:secret@example/token")

    monkeypatch.setattr(
        RedisFixedWindowRateThrottle,
        "redis_client_factory",
        staticmethod(fail_to_connect),
    )

    response = client.get(
        "/api/patient-app/static-assets/?version=v-3aafe09211fd"
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "训练素材服务繁忙，请稍后重试"}
    assert "secret" not in response.content.decode()
