import hashlib
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from django.conf import settings
from django.core.cache import cache

from .base import (
    ProviderCommandResult,
    ProviderDailySteps,
    ProviderDeviceStatus,
    ProviderError,
    ProviderMeasurement,
)


def build_token_password(key: str, app_id: str, timestamp: int) -> str:
    return hashlib.md5(f"{key}{app_id}{timestamp}".encode()).hexdigest()


class MiwitrackerClient:
    TOKEN_PATH = "/api/token/get_token"
    HEART_RATE_PATH = "/api/heartrate/get_heartrate_bytime"
    BLOOD_PRESSURE_PATH = "/api/bloodpressure/get_bloodpressure_bytime"
    BLOOD_OXYGEN_PATH = "/api/bloodoxygen/get_bloodoxygen_bytime"
    DAILY_STEPS_PATH = "/api/steps/get_steps_forday"
    DEVICE_STATUS_PATH = "/api/location/get_location_info"
    COMMAND_PATH = "/api/command/sendcommand"
    TOKEN_CACHE_TTL_SECONDS = 50 * 60

    def __init__(
        self,
        *,
        base_url: str | None = None,
        app_id: str | None = None,
        key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = self._normalize_base_url(base_url or settings.MIWITRACKER_BASE_URL)
        self.app_id = app_id if app_id is not None else settings.MIWITRACKER_APP_ID
        self.key = key if key is not None else settings.MIWITRACKER_KEY
        self.timeout = httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=5.0)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @property
    def _token_cache_key(self) -> str:
        token_scope = f"{self.base_url}\0{self.app_id}"
        scope_fingerprint = hashlib.sha256(token_scope.encode()).hexdigest()
        return f"wearables:miwitracker:access-token:{scope_fingerprint}"

    def get_access_token(self) -> str:
        cached_token = cache.get(self._token_cache_key)
        if cached_token:
            return str(cached_token)

        if not self.app_id or not self.key:
            raise ProviderError("Miwitracker 凭据未配置")

        timestamp = int(time.time())
        response = self._post(
            self.TOKEN_PATH,
            {
                "AppId": self.app_id,
                "Timestamp": timestamp,
                "Password": build_token_password(self.key, self.app_id, timestamp),
            },
        )
        payload = self._decode_response(response)
        self._raise_for_vendor_error(payload)
        token = payload.get("Result", {}).get("AccessToken")
        if not token:
            raise ProviderError("厂商响应未包含 AccessToken")

        cache.set(self._token_cache_key, token, self.TOKEN_CACHE_TTL_SECONDS)
        return str(token)

    def get_heart_rates(
        self, external_device_id: str, begin_at: datetime, end_at: datetime
    ) -> list[ProviderMeasurement]:
        payload = self._authenticated_post(
            self.HEART_RATE_PATH,
            self._time_window_payload(external_device_id, begin_at, end_at),
        )
        return self.parse_heart_rates(payload.get("Result") or [])

    def get_blood_pressures(
        self, external_device_id: str, begin_at: datetime, end_at: datetime
    ) -> list[ProviderMeasurement]:
        payload = self._authenticated_post(
            self.BLOOD_PRESSURE_PATH,
            self._time_window_payload(external_device_id, begin_at, end_at),
        )
        return self.parse_blood_pressures(payload.get("Result") or [])

    def get_blood_oxygen(
        self, external_device_id: str, begin_at: datetime, end_at: datetime
    ) -> list[ProviderMeasurement]:
        payload = self._authenticated_post(
            self.BLOOD_OXYGEN_PATH,
            self._time_window_payload(external_device_id, begin_at, end_at),
        )
        return self.parse_blood_oxygen(payload.get("Result") or [])

    def get_daily_steps(
        self, external_device_id: str, begin_date: date, end_date: date
    ) -> list[ProviderDailySteps]:
        payload = self._authenticated_post(
            self.DAILY_STEPS_PATH,
            {
                "Imei": external_device_id,
                "BeginTime": begin_date.isoformat(),
                "EndTime": end_date.isoformat(),
            },
        )
        return self.parse_daily_steps(payload.get("Items") or [])

    def get_device_status(self, external_device_id: str) -> ProviderDeviceStatus:
        payload = self._authenticated_post(
            self.DEVICE_STATUS_PATH,
            {"Imei": external_device_id, "MapType": "Google"},
        )
        result = payload.get("Result") or {}
        safe_payload = {
            key: result[key]
            for key in ("Imei", "Model", "Status", "Battery", "SignalTime", "GpsTime")
            if key in result
        }
        return ProviderDeviceStatus(
            external_device_id=result.get("Imei"),
            model=result.get("Model"),
            status=str(result["Status"]) if result.get("Status") is not None else None,
            battery_level=self._optional_int(result.get("Battery")),
            last_communication_at=self._parse_optional_datetime(
                result.get("SignalTime") or result.get("GpsTime")
            ),
            raw_payload=safe_payload,
        )

    def send_command(
        self,
        external_device_id: str,
        command_code: str,
        command_value: str = "",
        request_id: str | None = None,
    ) -> ProviderCommandResult:
        payload = self._authenticated_post(
            self.COMMAND_PATH,
            {
                "Imei": external_device_id,
                "Time": str(int(time.time())),
                "CommandCode": command_code,
                "CommandValue": command_value,
                "ReqId": request_id or str(uuid.uuid4()),
            },
        )
        return ProviderCommandResult(
            code=self._response_code(payload),
            message=str(payload.get("Message", "")),
            raw_payload=payload,
        )

    def parse_heart_rates(self, items: list[dict[str, Any]]) -> list[ProviderMeasurement]:
        return [
            ProviderMeasurement(
                metric_type="heart_rate",
                measured_at=self._parse_datetime(item["HrTime"]),
                values={"heart_rate": self._measurement_int(item["HeartRate"])},
                raw_payload=dict(item),
            )
            for item in items
        ]

    def parse_blood_pressures(self, items: list[dict[str, Any]]) -> list[ProviderMeasurement]:
        return [
            ProviderMeasurement(
                metric_type="blood_pressure",
                measured_at=self._parse_datetime(item["BpTime"]),
                values={
                    "systolic": self._measurement_int(item["Systolic"]),
                    "diastolic": self._measurement_int(item["Diastolic"]),
                },
                raw_payload=dict(item),
            )
            for item in items
        ]

    def parse_blood_oxygen(self, items: list[dict[str, Any]]) -> list[ProviderMeasurement]:
        return [
            ProviderMeasurement(
                metric_type="blood_oxygen",
                measured_at=self._parse_datetime(item["BloodOxygenTime"]),
                values={"blood_oxygen": self._measurement_int(item["BloodOxygen"])},
                raw_payload=dict(item),
            )
            for item in items
        ]

    def parse_daily_steps(self, items: list[dict[str, Any]]) -> list[ProviderDailySteps]:
        return [
            ProviderDailySteps(
                record_date=date.fromisoformat(str(item["Date"])[:10]),
                steps=self._optional_int(item.get("Steps")),
                distance=self._optional_decimal(item.get("Distance")),
                calorie=self._optional_decimal(item.get("Calorie")),
                raw_payload=dict(item),
            )
            for item in items
        ]

    def _authenticated_post(
        self,
        path: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        for attempt in range(2):
            token = self.get_access_token()
            request_body = {"AccessToken": token, **body}
            response = self._post(path, request_body, headers={"Authorization": token})
            if response.status_code == 401:
                error = ProviderError("厂商鉴权失败", code=401)
            else:
                payload = self._decode_response(response)
                if self._is_unauthorized_vendor_error(payload):
                    error = ProviderError(
                        str(payload.get("Message") or "厂商鉴权失败"),
                        code=self._response_code(payload),
                    )
                else:
                    self._raise_for_vendor_error(payload)
                    return payload

            if attempt == 0:
                cache.delete(self._token_cache_key)
                continue
            raise error

        raise AssertionError("不可达")

    def _post(
        self, path: str, payload: dict[str, Any], headers: dict[str, str] | None = None
    ) -> httpx.Response:
        try:
            response = self._client.post(path, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError("厂商请求超时") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("厂商请求失败") from exc

        if response.status_code >= 400 and response.status_code != 401:
            raise ProviderError("厂商请求失败", code=response.status_code)
        return response

    @staticmethod
    def _decode_response(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("厂商响应不是有效 JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderError("厂商响应格式错误")
        return payload

    @staticmethod
    def _response_code(payload: dict[str, Any]) -> int:
        try:
            return int(payload.get("Code", 0))
        except (TypeError, ValueError) as exc:
            raise ProviderError("厂商响应 Code 格式错误") from exc

    @classmethod
    def _raise_for_vendor_error(cls, payload: dict[str, Any]) -> None:
        code = cls._response_code(payload)
        if code != 0:
            raise ProviderError(str(payload.get("Message") or "厂商请求失败"), code=code)

    @classmethod
    def _is_unauthorized_vendor_error(cls, payload: dict[str, Any]) -> bool:
        code = cls._response_code(payload)
        message = str(payload.get("Message") or "").lower()
        return code == 401 or any(
            marker in message for marker in ("unauthorized", "无权限", "没有权限", "权限不足")
        )

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.hostname:
            return value.rstrip("/")
        netloc = parsed.hostname.lower()
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path.rstrip("/"), "", ""))

    @staticmethod
    def _time_window_payload(
        external_device_id: str, begin_at: datetime, end_at: datetime
    ) -> dict[str, str]:
        return {
            "Imei": external_device_id,
            "BeginTime": MiwitrackerClient._format_utc_datetime(begin_at),
            "EndTime": MiwitrackerClient._format_utc_datetime(end_at),
        }

    @staticmethod
    def _format_utc_datetime(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _parse_optional_datetime(cls, value: Any) -> datetime | None:
        return cls._parse_datetime(str(value)) if value else None

    @staticmethod
    def _measurement_int(value: Any) -> int:
        return int(Decimal(str(value)))

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return MiwitrackerClient._measurement_int(value) if value is not None else None

    @staticmethod
    def _optional_decimal(value: Any) -> Decimal | None:
        return Decimal(str(value)) if value is not None else None
