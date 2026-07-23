from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from celery import shared_task
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.wearables.models import (
    WearableBinding,
    WearableDevice,
    WearableSyncCursor,
    WearableSyncRun,
)
from apps.wearables.providers import MiwitrackerClient, ProviderError
from apps.wearables.services.attribution import attribute_daily_steps, attribute_measurement
from apps.wearables.services.summaries import recalculate_daily_summary
from apps.wearables.services.sync import calculate_sync_window


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
METRIC_TYPES = ("heart_rate", "blood_pressure", "blood_oxygen", "steps")


def _get_provider(device: WearableDevice):
    if device.provider == "miwitracker":
        return MiwitrackerClient()
    raise ProviderError(f"不支持的穿戴设备厂商：{device.provider}")


def _target_end(value: str | None) -> datetime:
    if value is None:
        now = timezone.now().astimezone(SHANGHAI_TZ)
        return datetime.combine(now.date(), time.min, tzinfo=SHANGHAI_TZ).astimezone(UTC)
    parsed = datetime.fromisoformat(value)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone=SHANGHAI_TZ)
    return parsed.astimezone(UTC)


def _record_date_for_timestamp(value: datetime) -> date:
    return value.astimezone(SHANGHAI_TZ).date()


def _provider_points(provider, device: WearableDevice, metric_type: str, start: datetime, end: datetime):
    if metric_type == "heart_rate":
        return provider.get_heart_rates(device.external_device_id, start, end)
    if metric_type == "blood_pressure":
        return provider.get_blood_pressures(device.external_device_id, start, end)
    if metric_type == "blood_oxygen":
        return provider.get_blood_oxygen(device.external_device_id, start, end)
    if metric_type == "steps":
        end_date = (end - timedelta(microseconds=1)).astimezone(SHANGHAI_TZ).date()
        return provider.get_daily_steps(
            device.external_device_id,
            start.astimezone(SHANGHAI_TZ).date(),
            end_date,
        )
    raise ValueError(f"不支持的同步指标：{metric_type}")


def _binding_patient_ids_for_date(device: WearableDevice, record_date: date) -> set[int]:
    day_start = datetime.combine(record_date, time.min, tzinfo=SHANGHAI_TZ).astimezone(UTC)
    day_end = day_start + timedelta(days=1)
    return set(
        WearableBinding.objects.filter(device=device, bound_at__lt=day_end)
        .filter(Q(unbound_at__isnull=True) | Q(unbound_at__gt=day_start))
        .values_list("patient_id", flat=True)
    )


def _recalculate_affected_summaries(device: WearableDevice, metric_type: str, record_dates: set[date]):
    status_field = f"{metric_type}_sync_status"
    for record_date in record_dates:
        for patient_id in _binding_patient_ids_for_date(device, record_date):
            summary = recalculate_daily_summary(patient_id, record_date)
            setattr(summary, status_field, summary.SyncStatus.SUCCEEDED)
            summary.save(update_fields=[status_field, "updated_at"])


def _advance_cursor(device: WearableDevice, metric_type: str, window_end: datetime):
    with transaction.atomic():
        cursor = (
            WearableSyncCursor.objects.select_for_update()
            .filter(device=device, metric_type=metric_type)
            .first()
        )
        if cursor is None:
            try:
                with transaction.atomic():
                    WearableSyncCursor.objects.create(
                        device=device,
                        metric_type=metric_type,
                        last_success_window_end=window_end,
                    )
                return
            except IntegrityError:
                cursor = (
                    WearableSyncCursor.objects.select_for_update()
                    .filter(device=device, metric_type=metric_type)
                    .get()
                )
        WearableSyncCursor.objects.filter(pk=cursor.pk).filter(
            Q(last_success_window_end__isnull=True) | Q(last_success_window_end__lt=window_end)
        ).update(last_success_window_end=window_end, updated_at=timezone.now())


@shared_task(bind=True)
def sync_device_metric(self, device_id: int, metric_type: str, target_end_iso: str | None = None):
    """同步单设备、单指标；失败仅重试本指标。"""
    device = WearableDevice.objects.get(pk=device_id)
    target_end = _target_end(target_end_iso)
    window_start, window_end = calculate_sync_window(
        device=device,
        metric_type=metric_type,
        target_end=target_end,
    )
    run = WearableSyncRun.objects.create(
        device=device,
        metric_type=metric_type,
        scheduled_at=timezone.now(),
        window_start=window_start,
        window_end=window_end,
        status=WearableSyncRun.Status.RUNNING,
        retry_count=self.request.retries,
    )
    provider = None
    try:
        provider = _get_provider(device)
        points = _provider_points(provider, device, metric_type, window_start, window_end)
        record_dates = set()
        for point in points:
            if metric_type == "steps":
                attribute_daily_steps(device, point)
                record_dates.add(point.record_date)
            else:
                attribute_measurement(device, point)
                record_dates.add(_record_date_for_timestamp(point.measured_at))
        _recalculate_affected_summaries(device, metric_type, record_dates)
        _advance_cursor(device, metric_type, window_end)
        run.status = WearableSyncRun.Status.SUCCEEDED
        run.returned_count = len(points)
        run.save(update_fields=["status", "returned_count", "updated_at"])
        return run.id
    except Exception as exc:
        run.status = WearableSyncRun.Status.FAILED
        run.error_code = str(exc.code) if isinstance(exc, ProviderError) and exc.code else ""
        run.error_message = str(exc)[:2000]
        run.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        raise self.retry(
            exc=exc,
            countdown=60 * 2**self.request.retries,
            max_retries=3,
        )
    finally:
        if provider and hasattr(provider, "close"):
            provider.close()


@shared_task
def schedule_daily_wearable_sync():
    """为仍有效或最近七天解绑的设备派发四个独立指标任务。"""
    target_end = _target_end(None)
    lookback_start = target_end - timedelta(days=7)
    devices = (
        WearableDevice.objects.filter(enabled=True, bindings__bound_at__lt=target_end)
        .filter(Q(bindings__unbound_at__isnull=True) | Q(bindings__unbound_at__gte=lookback_start))
        .distinct()
    )
    dispatched = 0
    for device in devices:
        for metric_type in METRIC_TYPES:
            sync_device_metric.delay(device.id, metric_type, target_end.isoformat())
            dispatched += 1
    return dispatched
