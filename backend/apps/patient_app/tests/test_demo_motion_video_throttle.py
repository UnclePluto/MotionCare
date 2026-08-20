from collections import defaultdict

import pytest
from django.core.cache import cache

from apps.patient_app.throttles import DemoMotionVideoRateThrottle


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


@pytest.fixture
def isolated_rate_limit(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(
        DemoMotionVideoRateThrottle,
        "redis_client_factory",
        staticmethod(lambda _url: redis),
    )
    cache.clear()
    return redis


@pytest.mark.django_db
def test_demo_manifest_uses_shared_atomic_redis_counter_and_rejects_request_61(
    client,
    isolated_rate_limit,
    monkeypatch,
):
    monkeypatch.setattr(
        "apps.patient_app.views.build_demo_motion_video_manifest",
        lambda: [],
    )

    responses = [
        client.get(
            "/api/patient-app/demo-motion-videos/",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_REAL_IP="198.51.100.8",
        )
        for _ in range(61)
    ]

    assert [response.status_code for response in responses[:60]] == [200] * 60
    assert responses[60].status_code == 429
    assert len(set(isolated_rate_limit.keys)) == 1
    assert isolated_rate_limit.keys[0].endswith(
        ":198.51.100.8"
    ) is False  # Redis key stores only a digest of the trusted address.


@pytest.mark.django_db
def test_demo_manifest_ignores_forged_x_forwarded_for_values(
    client,
    isolated_rate_limit,
    monkeypatch,
):
    monkeypatch.setattr(
        "apps.patient_app.views.build_demo_motion_video_manifest",
        lambda: [],
    )

    for request_number in range(60):
        response = client.get(
            "/api/patient-app/demo-motion-videos/",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_REAL_IP="198.51.100.19",
            HTTP_X_FORWARDED_FOR=f"203.0.113.{request_number % 250}",
        )
        assert response.status_code == 200

    rejected = client.get(
        "/api/patient-app/demo-motion-videos/",
        REMOTE_ADDR="127.0.0.1",
        HTTP_X_REAL_IP="198.51.100.19",
        HTTP_X_FORWARDED_FOR="192.0.2.200",
    )

    assert rejected.status_code == 429
    assert len(set(isolated_rate_limit.keys)) == 1


@pytest.mark.django_db
def test_demo_manifest_returns_safe_503_when_redis_is_unavailable(
    client,
    monkeypatch,
):
    def fail_to_connect(_url):
        raise RuntimeError("redis://user:secret@example/token")

    monkeypatch.setattr(
        DemoMotionVideoRateThrottle,
        "redis_client_factory",
        staticmethod(fail_to_connect),
    )

    response = client.get("/api/patient-app/demo-motion-videos/")

    assert response.status_code == 503
    assert response.json() == {"detail": "演示视频服务繁忙，请稍后重试"}
    assert "secret" not in response.content.decode()
