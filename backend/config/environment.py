import os

from django.core.exceptions import ImproperlyConfigured

def env_bool(name, *, default=False):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ImproperlyConfigured(f"{name} 只允许设置为 true 或 false。")


def validate_wechat_miniapp_settings(
    *,
    debug: bool,
    auth_mode: str,
    app_id: str,
    app_secret: str,
    mock_openid: str,
) -> None:
    if auth_mode not in {"wechat", "mock"}:
        raise ImproperlyConfigured("WECHAT_MINIAPP_AUTH_MODE 必须是 wechat 或 mock")
    if auth_mode == "mock" and (not debug or not mock_openid):
        raise ImproperlyConfigured("微信模拟身份仅允许在 DEBUG 环境使用")
    if not debug and auth_mode != "wechat":
        raise ImproperlyConfigured("生产环境必须使用微信真实身份模式")
    if auth_mode == "wechat" and (not app_id or not app_secret):
        raise ImproperlyConfigured("微信真实身份模式缺少 AppID 或 AppSecret")
