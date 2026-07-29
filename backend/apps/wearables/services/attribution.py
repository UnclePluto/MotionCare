import hashlib
import json
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q

from apps.wearables.models import WearableBinding, WearableDailySource, WearableMeasurement

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _matching_bindings(device, measured_at):
    return list(
        WearableBinding.objects.filter(device=device, bound_at__lte=measured_at)
        .filter(Q(unbound_at__isnull=True) | Q(unbound_at__gt=measured_at))
        .select_related("patient")
    )


def resolve_binding(device, measured_at):
    """返回测量时点唯一有效的绑定；无或多条匹配均返回空。"""
    matches = _matching_bindings(device, measured_at)
    return matches[0] if len(matches) == 1 else None


def _measurement_attribution(device, measured_at):
    matches = _matching_bindings(device, measured_at)
    if len(matches) == 1:
        return matches[0], WearableMeasurement.AttributionStatus.ATTRIBUTED
    if not matches:
        return None, WearableMeasurement.AttributionStatus.OUTSIDE_BINDING
    return None, WearableMeasurement.AttributionStatus.AMBIGUOUS


def _measurement_fingerprint(point):
    payload = {
        "metric_type": point.metric_type,
        "measured_at": point.measured_at.isoformat(),
        "values": point.values,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def attribute_measurement(device, point):
    """按测量时点归属厂商原始点，并使用稳定指纹幂等写入。"""
    binding, attribution_status = _measurement_attribution(device, point.measured_at)
    values = {
        "heart_rate": point.values.get("heart_rate"),
        "systolic": point.values.get("systolic"),
        "diastolic": point.values.get("diastolic"),
        "blood_oxygen": point.values.get("blood_oxygen"),
    }
    fingerprint = _measurement_fingerprint(point)
    measurement, _ = WearableMeasurement.objects.update_or_create(
        provider=device.provider,
        device=device,
        metric_type=point.metric_type,
        source_fingerprint=fingerprint,
        defaults={
            "binding": binding,
            "patient": binding.patient if binding else None,
            "measured_at": point.measured_at,
            "attribution_status": attribution_status,
            "raw_payload": point.raw_payload,
            **values,
        },
    )
    return measurement


def _day_bounds_utc(record_date):
    day_start = datetime.combine(record_date, time.min, tzinfo=SHANGHAI_TZ)
    next_day_start = day_start + timedelta(days=1)
    return day_start.astimezone(UTC), next_day_start.astimezone(UTC)


def _daily_steps_attribution(device, record_date):
    day_start, day_end = _day_bounds_utc(record_date)
    overlapping_bindings = list(
        WearableBinding.objects.filter(device=device, bound_at__lt=day_end)
        .filter(Q(unbound_at__isnull=True) | Q(unbound_at__gt=day_start))
        .select_related("patient")
    )
    if not overlapping_bindings:
        return None, WearableDailySource.AttributionStatus.OUTSIDE_BINDING

    if len(overlapping_bindings) == 1:
        binding = overlapping_bindings[0]
        if binding.bound_at <= day_start and (
            binding.unbound_at is None or binding.unbound_at >= day_end
        ):
            return binding, WearableDailySource.AttributionStatus.ATTRIBUTED
    return None, WearableDailySource.AttributionStatus.AMBIGUOUS


def attribute_daily_steps(device, point):
    """仅在设备完整覆盖上海业务自然日时归属整日步数。"""
    binding, attribution_status = _daily_steps_attribution(device, point.record_date)
    source, _ = WearableDailySource.objects.update_or_create(
        provider=device.provider,
        device=device,
        record_date=point.record_date,
        defaults={
            "steps": point.steps,
            "distance": point.distance,
            "calorie": point.calorie,
            "binding": binding,
            "patient": binding.patient if binding else None,
            "attribution_status": attribution_status,
            "raw_payload": point.raw_payload,
        },
    )
    return source


def revalidate_daily_steps_for_patient(patient_id, record_date):
    """在汇总前重验患者相关设备的当日步数源，持久化最新归属结果。"""
    day_start, day_end = _day_bounds_utc(record_date)
    related_device_ids = WearableBinding.objects.filter(
        patient_id=patient_id,
        bound_at__lt=day_end,
    ).filter(Q(unbound_at__isnull=True) | Q(unbound_at__gt=day_start)).values("device_id")
    sources = WearableDailySource.objects.filter(record_date=record_date).filter(
        Q(patient_id=patient_id)
        | Q(binding__patient_id=patient_id)
        | Q(device_id__in=related_device_ids)
    )
    for source in sources:
        binding, attribution_status = _daily_steps_attribution(source.device, source.record_date)
        source.binding = binding
        source.patient = binding.patient if binding else None
        source.attribution_status = attribution_status
        source.save(update_fields=["binding", "patient", "attribution_status", "updated_at"])
