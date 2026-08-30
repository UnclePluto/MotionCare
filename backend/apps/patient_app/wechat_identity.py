from collections.abc import Mapping

import httpx
from django.conf import settings


class WechatLoginCodeInvalid(Exception):
    pass


class WechatIdentityUnavailable(Exception):
    pass


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
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.get(
                "https://api.weixin.qq.com/sns/jscode2session",
                params={
                    "appid": settings.WECHAT_MINIAPP_APP_ID,
                    "secret": settings.WECHAT_MINIAPP_APP_SECRET,
                    "js_code": wx_code,
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
