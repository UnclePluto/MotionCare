from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from apps.wearables.capabilities import get_capability_profile
from apps.wearables.models import WearableBinding, WearableCommandLog, WearableDevice
from apps.wearables.providers import MiwitrackerClient, ProviderError


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
_SENSITIVE_TOKENS = {
    "authorization",
    "password",
    "secret",
    "token",
    "credential",
    "credentials",
}
_KEY_CREDENTIAL_QUALIFIERS = {"api", "access", "secret", "private", "client"}
_DROP = object()
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


def _key_tokens(value: object) -> set[str]:
    key = str(value)
    key = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", key)
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
    return {token.lower() for token in re.findall(r"[A-Za-z0-9]+", key)}


def _is_sensitive_parameter_key(key: object) -> bool:
    tokens = _key_tokens(key)
    if tokens & _SENSITIVE_TOKENS:
        return True
    return "key" in tokens and (tokens == {"key"} or bool(tokens & _KEY_CREDENTIAL_QUALIFIERS))


def _safe_parameter_value(value: Any):
    if isinstance(value, dict):
        return _safe_parameters(value)
    if isinstance(value, list):
        return [
            safe_value
            for item in value
            if (safe_value := _safe_parameter_value(item)) is not _DROP
        ]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _DROP


def _safe_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(parameters, dict):
        return {}
    safe = {}
    for key, value in parameters.items():
        if _is_sensitive_parameter_key(key):
            continue
        safe_value = _safe_parameter_value(value)
        if safe_value is not _DROP:
            safe[str(key)] = safe_value
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
        try:
            provider.close()
        except Exception:
            pass


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
    if result.external_device_id != device.external_device_id:
        raise ProviderError("厂商返回的设备标识不匹配")
    detected_model = result.model.strip() if isinstance(result.model, str) else ""
    model_max_length = WearableDevice._meta.get_field("model").max_length
    if detected_model and len(detected_model) > model_max_length:
        raise ProviderError("厂商返回的设备型号超出长度限制")
    online = _is_online(result.status)
    checked_at = timezone.now()
    update_fields = [
        "last_device_status",
        "last_battery_level",
        "last_communication_at",
        "last_status_checked_at",
        "updated_at",
    ]
    if not device.model.strip() and detected_model:
        device.model = detected_model
        update_fields.append("model")
    device.last_device_status = "online" if online else "offline"
    device.last_battery_level = result.battery_level
    device.last_communication_at = result.last_communication_at
    device.last_status_checked_at = checked_at
    device.save(update_fields=update_fields)
    capability = get_capability_profile(device.provider, device.model)
    return {
        "device_id": device.id,
        "model": device.model,
        "online": online,
        "battery_level": result.battery_level,
        "last_communication_at": result.last_communication_at.isoformat()
        if result.last_communication_at
        else None,
        "capabilities": {"ring": bool(capability.ring)},
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
        if result.code == 0 and command_type in _MEASUREMENT_COMMANDS:
            command.status = WearableCommandLog.Status.QUEUED
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
