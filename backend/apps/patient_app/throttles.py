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


class PatientAppAuthRateLimitUnavailable(APIException):
    status_code = 503
    default_detail = "登录服务繁忙，请稍后重试"
    default_code = "patient_app_auth_rate_limit_unavailable"


class RedisFixedWindowRateThrottle(BaseThrottle):
    """Redis-backed fixed-window throttle shared by every API worker."""

    key_namespace: str
    redis_url_setting: str
    requests_setting: str
    window_setting: str
    unavailable_exception_class: type[APIException]

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
        key = f"motioncare:rate-limit:{self.key_namespace}:{identity}"
        try:
            client = self.redis_client_factory(getattr(settings, self.redis_url_setting))
            count = int(
                client.eval(
                    self._increment_script,
                    1,
                    key,
                    getattr(settings, self.window_setting),
                )
            )
        except Exception as exc:
            raise self.unavailable_exception_class() from exc
        return count <= getattr(settings, self.requests_setting)


class DemoMotionVideoRateThrottle(RedisFixedWindowRateThrottle):
    key_namespace = "demo-motion-videos"
    redis_url_setting = "DEMO_MOTION_VIDEO_RATE_LIMIT_REDIS_URL"
    requests_setting = "DEMO_MOTION_VIDEO_RATE_LIMIT_REQUESTS"
    window_setting = "DEMO_MOTION_VIDEO_RATE_LIMIT_WINDOW_SECONDS"
    unavailable_exception_class = DemoMotionVideoRateLimitUnavailable


class PatientAppWechatSessionRateThrottle(RedisFixedWindowRateThrottle):
    key_namespace = "patient-app-wechat-session"
    redis_url_setting = "PATIENT_APP_AUTH_RATE_LIMIT_REDIS_URL"
    requests_setting = "PATIENT_APP_WECHAT_SESSION_RATE_LIMIT_REQUESTS"
    window_setting = "PATIENT_APP_WECHAT_SESSION_RATE_LIMIT_WINDOW_SECONDS"
    unavailable_exception_class = PatientAppAuthRateLimitUnavailable


class PatientAppBindRateThrottle(RedisFixedWindowRateThrottle):
    key_namespace = "patient-app-bind"
    redis_url_setting = "PATIENT_APP_AUTH_RATE_LIMIT_REDIS_URL"
    requests_setting = "PATIENT_APP_BIND_RATE_LIMIT_REQUESTS"
    window_setting = "PATIENT_APP_BIND_RATE_LIMIT_WINDOW_SECONDS"
    unavailable_exception_class = PatientAppAuthRateLimitUnavailable
