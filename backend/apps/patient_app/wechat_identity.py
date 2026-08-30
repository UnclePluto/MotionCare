from collections.abc import Mapping

import httpx
from django.conf import settings


class WechatLoginCodeInvalid(Exception):
    pass


class WechatIdentityUnavailable(Exception):
    pass


class _WechatCode2SessionTransport(httpx.BaseTransport):
    def __init__(
        self,
        transport: httpx.BaseTransport,
        *,
        app_secret: str,
        wx_code: str,
    ) -> None:
        self._transport = transport
        self._sensitive_params = {
            "secret": app_secret,
            "js_code": wx_code,
        }

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        upstream_request = httpx.Request(
            request.method,
            request.url.copy_merge_params(self._sensitive_params),
            headers=request.headers,
            content=request.content,
            extensions=request.extensions,
        )
        return self._transport.handle_request(upstream_request)

    def close(self) -> None:
        self._transport.close()


def exchange_login_code(wx_code: str, *, transport: httpx.BaseTransport | None = None) -> str:
    if settings.WECHAT_MINIAPP_AUTH_MODE == "mock":
        return settings.WECHAT_MINIAPP_MOCK_OPENID

    timeout = httpx.Timeout(
        connect=settings.WECHAT_MINIAPP_CONNECT_TIMEOUT_SECONDS,
        read=settings.WECHAT_MINIAPP_READ_TIMEOUT_SECONDS,
        write=settings.WECHAT_MINIAPP_READ_TIMEOUT_SECONDS,
        pool=settings.WECHAT_MINIAPP_CONNECT_TIMEOUT_SECONDS,
    )
    try:
        upstream_transport = transport or httpx.HTTPTransport()
        with httpx.Client(
            timeout=timeout,
            transport=_WechatCode2SessionTransport(
                upstream_transport,
                app_secret=settings.WECHAT_MINIAPP_APP_SECRET,
                wx_code=wx_code,
            ),
        ) as client:
            response = client.get(
                "https://api.weixin.qq.com/sns/jscode2session",
                params={
                    "appid": settings.WECHAT_MINIAPP_APP_ID,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise WechatIdentityUnavailable("微信身份服务不可用") from None

    if not isinstance(payload, Mapping):
        raise WechatIdentityUnavailable("微信身份服务不可用")
    if payload.get("errcode") == 40029:
        raise WechatLoginCodeInvalid("微信登录凭证无效")
    openid = payload.get("openid")
    if payload.get("errcode") not in (None, 0) or not isinstance(openid, str):
        raise WechatIdentityUnavailable("微信身份服务不可用")
    if not openid or len(openid) > 128:
        raise WechatIdentityUnavailable("微信身份服务不可用")
    return openid
