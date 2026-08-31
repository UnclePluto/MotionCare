import logging

import httpx
import pytest
from django.test import override_settings

from apps.patient_app.wechat_identity import (
    WechatIdentityUnavailable,
    WechatLoginCodeInvalid,
    exchange_login_code,
)


@override_settings(
    WECHAT_MINIAPP_AUTH_MODE="wechat",
    WECHAT_MINIAPP_APP_ID="wx-test",
    WECHAT_MINIAPP_APP_SECRET="secret-test",
    WECHAT_MINIAPP_CONNECT_TIMEOUT_SECONDS=2.5,
    WECHAT_MINIAPP_READ_TIMEOUT_SECONDS=7.5,
)
def test_exchange_login_code_sends_contract_with_timeout_without_logging_secrets(caplog):
    captured_request = None

    def handler(request):
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={"openid": "openid-001", "session_key": "private-session-key"},
            request=request,
        )

    transport = httpx.MockTransport(
        handler
    )
    caplog.set_level(logging.INFO, logger="httpx")

    assert exchange_login_code("single-use-code", transport=transport) == "openid-001"
    assert captured_request is not None
    assert captured_request.method == "GET"
    assert dict(captured_request.url.params) == {
        "appid": "wx-test",
        "secret": "secret-test",
        "js_code": "single-use-code",
        "grant_type": "authorization_code",
    }
    assert captured_request.extensions["timeout"] == {
        "connect": 2.5,
        "read": 7.5,
        "write": 7.5,
        "pool": 2.5,
    }
    assert "secret-test" not in caplog.text
    assert "single-use-code" not in caplog.text
    assert "private-session-key" not in caplog.text


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
            lambda request: httpx.Response(200, json={"openid": ""}, request=request),
            WechatIdentityUnavailable,
        ),
        (
            lambda request: httpx.Response(
                200, json={"openid": "o" * 129}, request=request
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
def test_exchange_login_code_maps_provider_failures_without_sensitive_values(
    handler,
    exception_type,
    caplog,
):
    transport = httpx.MockTransport(handler)
    caplog.set_level(logging.INFO, logger="httpx")

    with pytest.raises(exception_type) as exc_info:
        exchange_login_code("single-use-code", transport=transport)

    message = str(exc_info.value)
    assert "secret-test" not in message
    assert "private-session-key" not in message
    assert "single-use-code" not in message
    assert "secret-test" not in caplog.text
    assert "single-use-code" not in caplog.text
    assert "private-session-key" not in caplog.text


@override_settings(
    WECHAT_MINIAPP_AUTH_MODE="mock",
    WECHAT_MINIAPP_MOCK_OPENID="local-openid",
)
def test_exchange_login_code_uses_configured_mock_openid():
    assert exchange_login_code("single-use-code") == "local-openid"
