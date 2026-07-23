from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any

from django.utils import timezone

from apps.wearables.capabilities import get_capability_profile
from apps.wearables.models import WearableBinding, WearableCommandLog, WearableDevice
from apps.wearables.providers import MiwitrackerClient


class UnsupportedCapability(Exception):
    pass


class DisabledDevice(Exception):
    pass


class ActiveBindingRequired(Exception):
    pass


_COMMAND_FIELDS = {
    "ring",
    "measure_heart_rate",
    "measure_blood_pressure",
    "measure_blood_oxygen",
    "configure_heart_rate_interval",
    "configure_blood_pressure_interval",
    "configure_blood_oxygen_interval",
    "configure_step_switch",
}
_MEASUREMENT_COMMANDS = {
    "measure_heart_rate": "heart_rate",
    "measure_blood_pressure": "blood_pressure",
    "measure_blood_oxygen": "blood_oxygen",
}
_SENSITIVE_PARAMETER_KEYS = {
    "accesstoken",
    "authorization",
    "key",
    "password",
    "secret",
    "token",
    "reqid",
    "requestid",
    "apikey",
}
_COMMAND_STATUS_BY_PROVIDER_CODE = {
    0: WearableCommandLog.Status.SUCCEEDED,
    1803: WearableCommandLog.Status.QUEUED,
    1800: WearableCommandLog.Status.OFFLINE,
    1801: WearableCommandLog.Status.TIMEOUT,
    1802: WearableCommandLog.Status.FAILED,
}


def _get_provider(device: WearableDevice):
    if device.provider == "miwitracker":
        return MiwitrackerClient()
    raise UnsupportedCapability(f"不支持的穿戴设备厂商：{device.provider}")


def _safe_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(parameters, dict):
        return {}
    safe = {}
    for key, value in parameters.items():
        if re.sub(r"[^a-z0-9]", "", str(key).lower()) in _SENSITIVE_PARAMETER_KEYS:
            continue
        if isinstance(value, dict):
            safe[str(key)] = _safe_parameters(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)] = value
    return safe


def _command_value(command_type: str, parameters: dict[str, Any]) -> str:
    if command_type in {"ring", *_MEASUREMENT_COMMANDS}:
        return ""
    if command_type == "configure_step_switch":
        enabled = parameters.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("步数开关必须为布尔值。")
        return "1" if enabled else "0"
    interval = parameters.get("interval_minutes")
    if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 1440:
        raise ValueError("采集间隔必须为 1 至 1440 分钟。")
    return str(interval)


def _is_online(status: str | None) -> bool:
    return str(status).strip().lower() in {"1", "online", "on", "true"}


def _close_provider(provider) -> None:
    if hasattr(provider, "close"):
        provider.close()


def _active_binding(device: WearableDevice) -> WearableBinding | None:
    return (
        WearableBinding.objects.select_related("patient")
        .filter(device=device, unbound_at__isnull=True)
        .first()
    )


def check_device_status(device: WearableDevice) -> dict[str, Any]:
    if not device.enabled:
        raise DisabledDevice("设备已停用。")
    provider = _get_provider(device)
    try:
        result = provider.get_device_status(device.external_device_id)
    finally:
        _close_provider(provider)
    online = _is_online(result.status)
    checked_at = timezone.now()
    device.last_device_status = "online" if online else "offline"
    device.last_battery_level = result.battery_level
    device.last_communication_at = result.last_communication_at
    device.last_status_checked_at = checked_at
    device.save(
        update_fields=[
            "last_device_status",
            "last_battery_level",
            "last_communication_at",
            "last_status_checked_at",
            "updated_at",
        ]
    )
    return {
        "device_id": device.id,
        "model": device.model,
        "online": online,
        "battery_level": result.battery_level,
        "last_communication_at": result.last_communication_at.isoformat()
        if result.last_communication_at
        else None,
    }


def send_device_command(
    device: WearableDevice,
    command_type: str,
    actor,
    *,
    parameters: dict[str, Any] | None = None,
    require_binding: bool = False,
) -> WearableCommandLog:
    if not device.enabled:
        raise DisabledDevice("设备已停用。")
    if command_type not in _COMMAND_FIELDS:
        raise UnsupportedCapability("不支持的远程命令。")
    if not isinstance(device.model, str) or not device.model.strip():
        raise UnsupportedCapability("该设备型号能力尚未验证。")
    capability = get_capability_profile(device.provider, device.model)
    command_code = getattr(capability, command_type)
    if not command_code:
        raise UnsupportedCapability("该设备型号能力尚未验证。")
    if require_binding and _active_binding(device) is None:
        raise ActiveBindingRequired("患者没有有效设备绑定。")

    request_payload = _safe_parameters(parameters)
    command_value = _command_value(command_type, request_payload)
    command = WearableCommandLog.objects.create(
        device=device,
        command_type=command_type,
        command_code=command_code,
        request_payload=request_payload,
        status=WearableCommandLog.Status.QUEUED,
        requested_by=actor,
    )
    provider = None
    try:
        provider = _get_provider(device)
        command.requested_at = timezone.now()
        command.save(update_fields=["requested_at", "updated_at"])
        result = provider.send_command(
            device.external_device_id,
            command_code,
            command_value=command_value,
            request_id=str(command.id),
        )
        command.provider_code = str(result.code)
        command.status = _COMMAND_STATUS_BY_PROVIDER_CODE.get(
            result.code, WearableCommandLog.Status.FAILED
        )
    except Exception:
        command.status = WearableCommandLog.Status.FAILED
    finally:
        if provider is not None:
            _close_provider(provider)

    if command.status != WearableCommandLog.Status.QUEUED:
        command.completed_at = timezone.now()
    elif command_type in _MEASUREMENT_COMMANDS:
        command.poll_deadline_at = command.requested_at + timedelta(seconds=60)
        command.next_poll_at = command.requested_at + timedelta(seconds=10)
    command.save(update_fields=["provider_code", "status", "completed_at", "updated_at"])
    if command.status == WearableCommandLog.Status.QUEUED and command_type in _MEASUREMENT_COMMANDS:
        command.save(update_fields=["poll_deadline_at", "next_poll_at", "updated_at"])
        from apps.wearables.tasks import poll_queued_measurement

        poll_queued_measurement.apply_async(args=[command.id], countdown=10)
    return command


def measurement_metric_for_command(command_type: str) -> str:
    return _MEASUREMENT_COMMANDS[command_type]


def measurement_points_since(
    provider,
    device: WearableDevice,
    metric_type: str,
    requested_at: datetime,
):
    end = timezone.now()
    if metric_type == "heart_rate":
        points = provider.get_heart_rates(device.external_device_id, requested_at, end)
    elif metric_type == "blood_pressure":
        points = provider.get_blood_pressures(device.external_device_id, requested_at, end)
    elif metric_type == "blood_oxygen":
        points = provider.get_blood_oxygen(device.external_device_id, requested_at, end)
    else:
        raise UnsupportedCapability("不支持的主动测量指标。")
    return [point for point in points if point.measured_at > requested_at]
