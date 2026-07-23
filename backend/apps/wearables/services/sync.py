from datetime import UTC, datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.wearables.models import WearableBinding, WearableDevice, WearableSyncCursor, WearableSyncRun


SYNC_LOOKBACK = timedelta(days=7)
SYNC_OVERLAP = timedelta(days=1)


def _as_utc(value: datetime) -> datetime:
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone=UTC)
    return value.astimezone(UTC)


def _earliest_relevant_binding_start(device: WearableDevice, horizon_start: datetime, end: datetime):
    return (
        WearableBinding.objects.filter(device=device, bound_at__lt=end)
        .filter(Q(unbound_at__isnull=True) | Q(unbound_at__gte=horizon_start))
        .order_by("bound_at")
        .values_list("bound_at", flat=True)
        .first()
    )


def _earliest_unresolved_failure_start(
    *, device: WearableDevice, metric_type: str, horizon_start: datetime, end: datetime
):
    failures = WearableSyncRun.objects.filter(
        device=device,
        metric_type=metric_type,
        status=WearableSyncRun.Status.FAILED,
        window_start__lt=end,
        window_end__gt=horizon_start,
    ).order_by("window_start")
    for failure in failures:
        resolved = WearableSyncRun.objects.filter(
            device=device,
            metric_type=metric_type,
            status=WearableSyncRun.Status.SUCCEEDED,
            window_start__lte=failure.window_start,
            window_end__gte=failure.window_end,
        ).exists()
        if not resolved:
            return failure.window_start
    return None


def calculate_sync_window(
    *,
    device: WearableDevice,
    metric_type: str,
    target_end: datetime,
) -> tuple[datetime, datetime]:
    """为单设备、单指标计算最多七天的 UTC 补拉窗口。"""
    end = _as_utc(target_end)
    horizon_start = end - SYNC_LOOKBACK
    binding_start = _earliest_relevant_binding_start(device, horizon_start, end)
    cursor = WearableSyncCursor.objects.filter(device=device, metric_type=metric_type).first()
    cursor_start = (
        _as_utc(cursor.last_success_window_end) - SYNC_OVERLAP
        if cursor and cursor.last_success_window_end
        else horizon_start
    )
    failed_start = _earliest_unresolved_failure_start(
        device=device,
        metric_type=metric_type,
        horizon_start=horizon_start,
        end=end,
    )
    history_start = _as_utc(failed_start) if failed_start else cursor_start
    candidates = [horizon_start, history_start]
    if binding_start:
        candidates.append(_as_utc(binding_start))
    return max(candidates), end
