import secrets

from apps.wearables.models import WearableDevice


class ShortCodeExhausted(Exception):
    """设备固定简码空间已耗尽。"""


def generate_device_short_code() -> str:
    """生成一个未被占用的四位设备固定简码。"""
    for _ in range(32):
        short_code = f"{secrets.randbelow(10_000):04d}"
        if not WearableDevice.objects.filter(short_code=short_code).exists():
            return short_code

    used_codes = set(WearableDevice.objects.values_list("short_code", flat=True))
    for value in range(10_000):
        short_code = f"{value:04d}"
        if short_code not in used_codes:
            return short_code
    raise ShortCodeExhausted("四位设备简码已用尽")
