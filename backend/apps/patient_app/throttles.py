import hashlib
import ipaddress

import redis
from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework.throttling import BaseThrottle


class DemoMotionVideoRateLimitUnavailable(APIException):
    status_code = 503
    default_detail = "演示视频服务繁忙，请稍后重试"
    default_code = "demo_motion_video_rate_limit_unavailable"


class DemoMotionVideoRateThrottle(BaseThrottle):
    """Redis-backed fixed-window throttle shared by every API worker."""

    redis_client_factory = staticmethod(redis.Redis.from_url)
    _increment_script = """
local now = tonumber(redis.call('TIME')[1])
local window = tonumber(ARGV[1])
local bucket = math.floor(now / window)
local key = KEYS[1] .. ':' .. bucket
local count = redis.call('INCR', key)
if count == 1 then
  redis.call('EXPIREAT', key, ((bucket + 1) * window) + 1)
end
return count
"""

    @staticmethod
    def _valid_ip(value):
        if not value:
            return None
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            return None

    def _trusted_client_ip(self, request):
        # OpenResty overwrites X-Real-IP and X-Forwarded-For. Never parse a
        # client-supplied forwarding chain here.
        return (
            self._valid_ip(request.META.get("HTTP_X_REAL_IP"))
            or self._valid_ip(request.META.get("REMOTE_ADDR"))
            or "unknown"
        )

    def allow_request(self, request, view):
        client_ip = self._trusted_client_ip(request)
        identity = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
        key = f"motioncare:rate-limit:demo-motion-videos:{identity}"
        try:
            client = self.redis_client_factory(
                settings.DEMO_MOTION_VIDEO_RATE_LIMIT_REDIS_URL
            )
            count = int(
                client.eval(
                    self._increment_script,
                    1,
                    key,
                    settings.DEMO_MOTION_VIDEO_RATE_LIMIT_WINDOW_SECONDS,
                )
            )
        except Exception as exc:
            raise DemoMotionVideoRateLimitUnavailable() from exc
        return count <= settings.DEMO_MOTION_VIDEO_RATE_LIMIT_REQUESTS
