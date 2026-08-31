from collections import defaultdict
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.patient_app import throttles


class FakeRedis:
    def __init__(self):
        self.counts = defaultdict(int)
        self.keys = []

    def eval(self, script, key_count, base_key, window_seconds):
        assert "TIME" in script
        assert key_count == 1
        assert int(window_seconds) in {60, 900}
        self.keys.append(base_key)
        self.counts[base_key] += 1
        return self.counts[base_key]


@pytest.fixture
def isolated_auth_rate_limit(monkeypatch):
    redis = FakeRedis()
    throttle_base = getattr(
        throttles,
        "RedisFixedWindowRateThrottle",
        throttles.DemoMotionVideoRateThrottle,
    )
    monkeypatch.setattr(
        throttle_base,
        "redis_client_factory",
        staticmethod(lambda _url: redis),
    )
    return redis


@pytest.mark.django_db
def test_wechat_session_uses_shared_counter_and_rejects_request_61(
    isolated_auth_rate_limit,
    monkeypatch,
):
    monkeypatch.setattr(
        "apps.patient_app.views.exchange_login_code",
        lambda wx_code: "openid-001",
    )
    monkeypatch.setattr(
        "apps.patient_app.views.recover_patient_app_session",
        lambda **kwargs: SimpleNamespace(status="unbound", token=None, session=None),
    )
    client = APIClient()

    responses = [
        client.post(
            "/api/patient-app/wechat-session/",
            {"wx_code": "private-wx-code"},
            format="json",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_REAL_IP="198.51.100.8",
            HTTP_AUTHORIZATION="Bearer private-token",
        )
        for _ in range(61)
    ]

    assert [response.status_code for response in responses[:60]] == [200] * 60
    assert responses[60].status_code == 429
    keys = " ".join(isolated_auth_rate_limit.keys)
    assert "198.51.100.8" not in keys
    assert "private-wx-code" not in keys
    assert "private-token" not in keys


@pytest.mark.django_db
def test_bind_uses_shared_counter_and_rejects_request_31(
    project_patient,
    isolated_auth_rate_limit,
    monkeypatch,
):
    monkeypatch.setattr(
        "apps.patient_app.views.exchange_login_code",
        lambda wx_code: "openid-001",
    )
    monkeypatch.setattr(
        "apps.patient_app.views.bind_project_patient_with_code",
        lambda **kwargs: ("new-private-token", SimpleNamespace(project_patient=project_patient)),
    )
    client = APIClient()

    responses = [
        client.post(
            "/api/patient-app/bind/",
            {"code": "1234", "wx_code": "private-wx-code"},
            format="json",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_REAL_IP="198.51.100.8",
        )
        for _ in range(31)
    ]

    assert [response.status_code for response in responses[:30]] == [200] * 30
    assert responses[30].status_code == 429
    keys = " ".join(isolated_auth_rate_limit.keys)
    assert "198.51.100.8" not in keys
    assert "private-wx-code" not in keys
    assert "1234" not in keys


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/patient-app/wechat-session/", {"wx_code": "wx-code"}),
        ("/api/patient-app/bind/", {"code": "1234", "wx_code": "wx-code"}),
    ],
)
@pytest.mark.django_db
def test_auth_endpoints_return_safe_503_when_redis_is_unavailable(
    path,
    payload,
    monkeypatch,
):
    throttle_base = getattr(
        throttles,
        "RedisFixedWindowRateThrottle",
        throttles.DemoMotionVideoRateThrottle,
    )

    def fail_to_connect(_url):
        raise RuntimeError("redis://user:secret@example.invalid/private-token")

    monkeypatch.setattr(
        throttle_base,
        "redis_client_factory",
        staticmethod(fail_to_connect),
    )

    response = APIClient().post(path, payload, format="json")

    assert response.status_code == 503
    assert response.json() == {"detail": "登录服务繁忙，请稍后重试"}
    assert "secret" not in response.content.decode()
    assert "private-token" not in response.content.decode()
