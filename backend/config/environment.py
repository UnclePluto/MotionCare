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
