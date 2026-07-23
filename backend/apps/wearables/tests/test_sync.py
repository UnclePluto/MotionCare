from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings

from apps.wearables.models import (
    WearableBinding,
    WearableDailySummary,
    WearableMeasurement,
    WearableSyncCursor,
    WearableSyncRun,
)
from apps.wearables.providers import ProviderDailySteps, ProviderError, ProviderMeasurement
from apps.wearables.services.sync import calculate_sync_window
from apps.wearables.tasks import _advance_cursor, schedule_daily_wearable_sync, sync_device_metric


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
TARGET_END = datetime(2026, 7, 23, tzinfo=SHANGHAI_TZ)
TARGET_END_UTC = TARGET_END.astimezone(UTC)
SEVEN_DAYS_AGO = TARGET_END_UTC - timedelta(days=7)


class StubProvider:
    def __init__(self, *, measurements=None, steps=None, errors=None):
        self.measurements = measurements or {}
        self.steps = steps or []
        self.errors = errors or {}

    def _measurements(self, metric_type):
        error = self.errors.get(metric_type)
        if error:
            raise error
        return self.measurements.get(metric_type, [])

    def get_heart_rates(self, external_device_id, begin_at, end_at):
        return self._measurements("heart_rate")

    def get_blood_pressures(self, external_device_id, begin_at, end_at):
        return self._measurements("blood_pressure")

    def get_blood_oxygen(self, external_device_id, begin_at, end_at):
        return self._measurements("blood_oxygen")

    def get_daily_steps(self, external_device_id, begin_date, end_date):
        error = self.errors.get("steps")
        if error:
            raise error
        return self.steps


def _bind(device, patient, doctor, *, bound_at, unbound_at=None):
    return WearableBinding.objects.create(
        patient=patient,
        device=device,
        bound_at=bound_at,
        unbound_at=unbound_at,
        bound_by=doctor,
        unbound_by=doctor if unbound_at else None,
    )


def _run_sync(device, metric_type):
    return sync_device_metric.apply(
        args=[device.id, metric_type, TARGET_END.isoformat()],
        throw=False,
    )


def test_wearable_beat_schedule_uses_shanghai_three_am():
    entry = settings.CELERY_BEAT_SCHEDULE["schedule-daily-wearable-sync"]

    assert entry["task"] == "apps.wearables.tasks.schedule_daily_wearable_sync"
    assert entry["schedule"].hour == {3}
    assert entry["schedule"].minute == {0}
    assert settings.CELERY_TIMEZONE == "Asia/Shanghai"
    assert settings.CELERY_ENABLE_UTC is True


@pytest.mark.django_db
def test_window_without_cursor_caps_twenty_day_binding_at_seven_days(patient, doctor, wearable_device):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
    )

    start, end = calculate_sync_window(
        device=wearable_device,
        metric_type="heart_rate",
        target_end=TARGET_END,
    )

    assert (start, end) == (SEVEN_DAYS_AGO, TARGET_END_UTC)


@pytest.mark.django_db
def test_window_overlaps_the_day_before_the_last_success(patient, doctor, wearable_device):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
    )
    WearableSyncCursor.objects.create(
        device=wearable_device,
        metric_type="heart_rate",
        last_success_window_end=TARGET_END_UTC - timedelta(days=2),
    )

    start, end = calculate_sync_window(
        device=wearable_device,
        metric_type="heart_rate",
        target_end=TARGET_END,
    )

    assert (start, end) == (TARGET_END_UTC - timedelta(days=3), TARGET_END_UTC)


@pytest.mark.django_db
def test_window_includes_an_unresolved_failure_from_six_days_ago(patient, doctor, wearable_device):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
    )
    failed_start = TARGET_END_UTC - timedelta(days=6)
    WearableSyncRun.objects.create(
        device=wearable_device,
        metric_type="heart_rate",
        window_start=failed_start,
        window_end=TARGET_END_UTC - timedelta(days=5),
        status=WearableSyncRun.Status.FAILED,
    )

    start, _ = calculate_sync_window(
        device=wearable_device,
        metric_type="heart_rate",
        target_end=TARGET_END,
    )

    assert start == failed_start


@pytest.mark.django_db
def test_window_never_rewinds_beyond_seven_days_for_old_failure(patient, doctor, wearable_device):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
    )
    WearableSyncRun.objects.create(
        device=wearable_device,
        metric_type="heart_rate",
        window_start=TARGET_END_UTC - timedelta(days=10),
        window_end=TARGET_END_UTC - timedelta(days=9),
        status=WearableSyncRun.Status.FAILED,
    )

    start, _ = calculate_sync_window(
        device=wearable_device,
        metric_type="heart_rate",
        target_end=TARGET_END,
    )

    assert start == SEVEN_DAYS_AGO


@pytest.mark.django_db
def test_scheduler_dispatches_all_metrics_for_recently_unbound_device(
    monkeypatch, patient, doctor, wearable_device
):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
        unbound_at=TARGET_END_UTC - timedelta(days=2),
    )
    delay = Mock()
    monkeypatch.setattr("apps.wearables.tasks.sync_device_metric.delay", delay)
    monkeypatch.setattr("apps.wearables.tasks.timezone.now", lambda: TARGET_END + timedelta(hours=3))

    dispatched = schedule_daily_wearable_sync.apply().get()

    assert dispatched == 4
    assert [call.args[1] for call in delay.call_args_list] == [
        "heart_rate",
        "blood_pressure",
        "blood_oxygen",
        "steps",
    ]
    assert all(call.args[0] == wearable_device.id for call in delay.call_args_list)
    dispatched_target_ends = {
        datetime.fromisoformat(call.args[2]).astimezone(SHANGHAI_TZ) for call in delay.call_args_list
    }
    assert dispatched_target_ends == {TARGET_END}


@pytest.mark.django_db
def test_empty_success_records_run_and_advances_cursor(monkeypatch, patient, doctor, wearable_device):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
    )
    monkeypatch.setattr("apps.wearables.tasks._get_provider", lambda device: StubProvider())

    result = _run_sync(wearable_device, "heart_rate")

    assert result.successful()
    run = WearableSyncRun.objects.get(device=wearable_device, metric_type="heart_rate")
    cursor = WearableSyncCursor.objects.get(device=wearable_device, metric_type="heart_rate")
    assert (run.status, run.returned_count) == (WearableSyncRun.Status.SUCCEEDED, 0)
    assert cursor.last_success_window_end == TARGET_END_UTC


@pytest.mark.django_db
def test_metric_failures_do_not_prevent_other_metrics_from_succeeding(
    monkeypatch, patient, doctor, wearable_device
):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
    )
    provider = StubProvider(
        errors={"blood_pressure": ProviderError("上游不可用", code=503)},
    )
    monkeypatch.setattr("apps.wearables.tasks._get_provider", lambda device: provider)

    for metric_type in ("heart_rate", "blood_oxygen", "steps"):
        assert _run_sync(wearable_device, metric_type).successful()
    failed = _run_sync(wearable_device, "blood_pressure")

    assert not failed.successful()
    assert set(
        WearableSyncCursor.objects.filter(device=wearable_device).values_list("metric_type", flat=True)
    ) == {"heart_rate", "blood_oxygen", "steps"}
    failed_run = WearableSyncRun.objects.filter(
        device=wearable_device, metric_type="blood_pressure"
    ).order_by("-id").first()
    assert failed_run.status == WearableSyncRun.Status.FAILED
    assert failed_run.error_code == "503"


@pytest.mark.django_db
def test_sync_is_idempotent_and_recalculates_each_affected_shanghai_date(
    monkeypatch, patient, doctor, wearable_device
):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
    )
    provider = StubProvider(
        measurements={
            "heart_rate": [
                ProviderMeasurement(
                    metric_type="heart_rate",
                    measured_at=datetime(2026, 7, 21, 15, 59, tzinfo=UTC),
                    values={"heart_rate": 65},
                    raw_payload={"id": "before-shanghai-midnight"},
                ),
                ProviderMeasurement(
                    metric_type="heart_rate",
                    measured_at=datetime(2026, 7, 21, 16, tzinfo=UTC),
                    values={"heart_rate": 72},
                    raw_payload={"id": "at-shanghai-midnight"},
                ),
            ]
        }
    )
    monkeypatch.setattr("apps.wearables.tasks._get_provider", lambda device: provider)

    assert _run_sync(wearable_device, "heart_rate").successful()
    assert _run_sync(wearable_device, "heart_rate").successful()

    assert WearableMeasurement.objects.filter(device=wearable_device).count() == 2
    assert set(
        WearableDailySummary.objects.filter(patient=patient).values_list("record_date", flat=True)
    ) == {datetime(2026, 7, 21).date(), datetime(2026, 7, 22).date()}


@pytest.mark.django_db
def test_future_cursor_uses_a_nonempty_overlap_window_and_never_moves_backwards(
    monkeypatch, patient, doctor, wearable_device
):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
    )
    future_cursor = TARGET_END_UTC + timedelta(days=1)
    WearableSyncCursor.objects.create(
        device=wearable_device,
        metric_type="heart_rate",
        last_success_window_end=future_cursor,
    )
    monkeypatch.setattr("apps.wearables.tasks._get_provider", lambda device: StubProvider())

    start, end = calculate_sync_window(
        device=wearable_device,
        metric_type="heart_rate",
        target_end=TARGET_END,
    )
    assert (start, end) == (TARGET_END_UTC - timedelta(days=1), TARGET_END_UTC)

    assert _run_sync(wearable_device, "heart_rate").successful()

    assert WearableSyncCursor.objects.get(
        device=wearable_device, metric_type="heart_rate"
    ).last_success_window_end == future_cursor


@pytest.mark.django_db
@pytest.mark.parametrize(
    "cursor_end",
    [TARGET_END_UTC, TARGET_END_UTC + timedelta(days=1), TARGET_END_UTC + timedelta(days=20)],
)
def test_equal_or_future_cursor_always_produces_nonempty_window_without_binding(
    wearable_device, cursor_end
):
    WearableSyncCursor.objects.create(
        device=wearable_device,
        metric_type="heart_rate",
        last_success_window_end=cursor_end,
    )

    start, end = calculate_sync_window(
        device=wearable_device,
        metric_type="heart_rate",
        target_end=TARGET_END,
    )

    assert (start, end) == (TARGET_END_UTC - timedelta(days=1), TARGET_END_UTC)
    assert start < end


@pytest.mark.django_db
def test_covered_failure_no_longer_expands_window(patient, doctor, wearable_device):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
    )
    failure_start = TARGET_END_UTC - timedelta(days=6)
    failure_end = TARGET_END_UTC - timedelta(days=5)
    WearableSyncRun.objects.create(
        device=wearable_device,
        metric_type="heart_rate",
        window_start=failure_start,
        window_end=failure_end,
        status=WearableSyncRun.Status.FAILED,
    )
    WearableSyncRun.objects.create(
        device=wearable_device,
        metric_type="heart_rate",
        window_start=failure_start,
        window_end=TARGET_END_UTC - timedelta(days=4),
        status=WearableSyncRun.Status.SUCCEEDED,
    )
    WearableSyncCursor.objects.create(
        device=wearable_device,
        metric_type="heart_rate",
        last_success_window_end=TARGET_END_UTC - timedelta(days=2),
    )

    start, _ = calculate_sync_window(
        device=wearable_device,
        metric_type="heart_rate",
        target_end=TARGET_END,
    )

    assert start == TARGET_END_UTC - timedelta(days=3)


@pytest.mark.django_db
def test_cursor_advance_cannot_overwrite_a_newer_interleaved_write(monkeypatch, wearable_device):
    old_end = TARGET_END_UTC - timedelta(days=2)
    new_end = TARGET_END_UTC
    cursor = WearableSyncCursor.objects.create(
        device=wearable_device,
        metric_type="heart_rate",
        last_success_window_end=old_end - timedelta(days=1),
    )
    stale_cursor = WearableSyncCursor.objects.get(pk=cursor.pk)
    original_get_or_create = WearableSyncCursor.objects.get_or_create
    original_select_for_update = WearableSyncCursor.objects.select_for_update

    def stale_get_or_create(*args, **kwargs):
        WearableSyncCursor.objects.filter(pk=cursor.pk).update(last_success_window_end=new_end)
        return stale_cursor, False

    def interleaving_select_for_update(*args, **kwargs):
        WearableSyncCursor.objects.filter(pk=cursor.pk).update(last_success_window_end=new_end)
        return original_select_for_update(*args, **kwargs)

    monkeypatch.setattr(WearableSyncCursor.objects, "get_or_create", stale_get_or_create)
    monkeypatch.setattr(
        WearableSyncCursor.objects, "select_for_update", interleaving_select_for_update
    )

    _advance_cursor(wearable_device, "heart_rate", old_end)

    assert WearableSyncCursor.objects.get(pk=cursor.pk).last_success_window_end == new_end
    monkeypatch.setattr(WearableSyncCursor.objects, "get_or_create", original_get_or_create)


@pytest.mark.django_db
def test_failure_logs_every_retry_and_never_advances_cursor(monkeypatch, patient, doctor, wearable_device):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
    )
    monkeypatch.setattr(
        "apps.wearables.tasks._get_provider",
        lambda device: StubProvider(errors={"heart_rate": ProviderError("超时", code=504)}),
    )

    retry_calls = []
    original_retry = sync_device_metric.retry

    def record_retry(*args, **kwargs):
        retry_calls.append(kwargs)
        return original_retry(*args, **kwargs)

    monkeypatch.setattr(sync_device_metric, "retry", record_retry)
    result = _run_sync(wearable_device, "heart_rate")

    assert not result.successful()
    runs = list(
        WearableSyncRun.objects.filter(device=wearable_device, metric_type="heart_rate").order_by(
            "retry_count"
        )
    )
    assert [run.retry_count for run in runs] == [0, 1, 2, 3]
    assert all(run.status == WearableSyncRun.Status.FAILED for run in runs)
    assert not WearableSyncCursor.objects.filter(
        device=wearable_device, metric_type="heart_rate"
    ).exists()
    assert [call["countdown"] for call in retry_calls] == [60, 120, 240, 480]
    assert all(call["max_retries"] == 3 for call in retry_calls)


@pytest.mark.django_db
def test_steps_sync_uses_daily_provider_data_and_recalculates_summary(
    monkeypatch, patient, doctor, wearable_device
):
    _bind(
        wearable_device,
        patient,
        doctor,
        bound_at=TARGET_END_UTC - timedelta(days=20),
    )
    monkeypatch.setattr(
        "apps.wearables.tasks._get_provider",
        lambda device: StubProvider(
            steps=[
                ProviderDailySteps(
                    record_date=datetime(2026, 7, 22).date(),
                    steps=5821,
                    distance=Decimal("4.2"),
                    calorie=Decimal("200"),
                    raw_payload={"Date": "2026-07-22", "Steps": 5821},
                )
            ]
        ),
    )

    assert _run_sync(wearable_device, "steps").successful()

    summary = WearableDailySummary.objects.get(patient=patient, record_date=datetime(2026, 7, 22).date())
    assert summary.steps == 5821
