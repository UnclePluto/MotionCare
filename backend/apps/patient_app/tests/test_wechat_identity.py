import httpx
import pytest
from django.test import override_settings

from apps.patient_app.wechat_identity import (
    WechatIdentityUnavailable,
    WechatLoginCodeInvalid,
    exchange_login_code,
)


@pytest.fixture(autouse=True)
def wechat_identity_timeouts(settings):
    settings.WECHAT_MINIAPP_CONNECT_TIMEOUT_SECONDS = 1
    settings.WECHAT_MINIAPP_READ_TIMEOUT_SECONDS = 1


@override_settings(
    WECHAT_MINIAPP_AUTH_MODE="wechat",
    WECHAT_MINIAPP_APP_ID="wx-test",
    WECHAT_MINIAPP_APP_SECRET="secret-test",
)
def test_exchange_login_code_returns_only_openid():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"openid": "openid-001", "session_key": "private-session-key"},
            request=request,
        )
    )

    assert exchange_login_code("single-use-code", transport=transport) == "openid-001"


@pytest.mark.parametrize(
    ("handler", "exception_type"),
    [
        (
            lambda request: httpx.Response(
                200, json={"errcode": 40029, "errmsg": "invalid code"}, request=request
            ),
            WechatLoginCodeInvalid,
        ),
        (
            lambda request: httpx.Response(
                200, json={"errcode": 45011, "errmsg": "rate limit"}, request=request
            ),
            WechatIdentityUnavailable,
        ),
        (
            lambda request: httpx.Response(
                200, json={"errcode": -1, "errmsg": "system busy"}, request=request
            ),
            WechatIdentityUnavailable,
        ),
        (
            lambda request: httpx.Response(200, text="not json", request=request),
            WechatIdentityUnavailable,
        ),
        (
            lambda request: httpx.Response(200, json=["openid-001"], request=request),
            WechatIdentityUnavailable,
        ),
        (
            lambda request: httpx.Response(
                200, json={"session_key": "private-session-key"}, request=request
            ),
            WechatIdentityUnavailable,
        ),
        (
            lambda request: httpx.Response(500, text="private-session-key", request=request),
            WechatIdentityUnavailable,
        ),
        (
            lambda request: (_ for _ in ()).throw(httpx.TimeoutException("single-use-code")),
            WechatIdentityUnavailable,
        ),
    ],
)
@override_settings(
    WECHAT_MINIAPP_AUTH_MODE="wechat",
    WECHAT_MINIAPP_APP_ID="wx-test",
    WECHAT_MINIAPP_APP_SECRET="secret-test",
)
def test_exchange_login_code_maps_provider_failures_without_sensitive_values(handler, exception_type):
    transport = httpx.MockTransport(handler)

    with pytest.raises(exception_type) as exc_info:
        exchange_login_code("single-use-code", transport=transport)

    message = str(exc_info.value)
    assert "secret-test" not in message
    assert "private-session-key" not in message
    assert "single-use-code" not in message


@override_settings(
    WECHAT_MINIAPP_AUTH_MODE="mock",
    WECHAT_MINIAPP_MOCK_OPENID="local-openid",
)
def test_exchange_login_code_uses_configured_mock_openid():
    assert exchange_login_code("single-use-code") == "local-openid"
