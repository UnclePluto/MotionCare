import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from apps.wearables.models import WearableDailySource, WearableDailySummary, WearableMeasurement
from apps.wearables.services.summaries import recalculate_daily_summary


def _measurement(*, patient, device, metric_type, measured_at, **values):
    return WearableMeasurement.objects.create(
        provider=device.provider,
        device=device,
        patient=patient,
        metric_type=metric_type,
        measured_at=measured_at,
        attribution_status=WearableMeasurement.AttributionStatus.ATTRIBUTED,
        source_fingerprint=hashlib.sha256(
            f"{metric_type}-{measured_at.isoformat()}-{values}".encode()
        ).hexdigest(),
        raw_payload={},
        **values,
    )


@pytest.mark.django_db
def test_recalculate_daily_summary_aggregates_attributed_raw_data(patient, wearable_device):
    record_date = date(2026, 7, 22)
    for hour, heart_rate in enumerate((60, 72, 84)):
        _measurement(
            patient=patient,
            device=wearable_device,
            metric_type="heart_rate",
            measured_at=datetime(2026, 7, 22, hour, tzinfo=UTC),
            heart_rate=heart_rate,
        )
    for hour, systolic, diastolic in ((3, 120, 80), (4, 118, 76)):
        _measurement(
            patient=patient,
            device=wearable_device,
            metric_type="blood_pressure",
            measured_at=datetime(2026, 7, 22, hour, tzinfo=UTC),
            systolic=systolic,
            diastolic=diastolic,
        )
    for hour, blood_oxygen in ((5, 96), (6, 98)):
        _measurement(
            patient=patient,
            device=wearable_device,
            metric_type="blood_oxygen",
            measured_at=datetime(2026, 7, 22, hour, tzinfo=UTC),
            blood_oxygen=blood_oxygen,
        )
    WearableDailySource.objects.create(
        provider=wearable_device.provider,
        device=wearable_device,
        patient=patient,
        record_date=record_date,
        steps=5821,
        attribution_status=WearableDailySource.AttributionStatus.ATTRIBUTED,
        raw_payload={},
    )

    summary = recalculate_daily_summary(patient.id, record_date)

    assert summary.heart_rate_avg == Decimal("72.00")
    assert (summary.heart_rate_min, summary.heart_rate_max, summary.heart_rate_count) == (60, 84, 3)
    assert summary.systolic_avg == Decimal("119.00")
    assert summary.diastolic_avg == Decimal("78.00")
    assert summary.blood_pressure_count == 2
    assert summary.blood_oxygen_avg == Decimal("97.00")
    assert summary.steps == 5821
    assert summary.steps_attribution_status == WearableDailySummary.AttributionStatus.ATTRIBUTED


@pytest.mark.django_db
def test_summary_uses_shanghai_record_date_and_excludes_other_statuses(patient, wearable_device):
    record_date = date(2026, 7, 22)
    _measurement(
        patient=patient,
        device=wearable_device,
        metric_type="heart_rate",
        measured_at=datetime(2026, 7, 21, 16, tzinfo=UTC),
        heart_rate=72,
    )
    _measurement(
        patient=patient,
        device=wearable_device,
        metric_type="heart_rate",
        measured_at=datetime(2026, 7, 21, 15, 59, tzinfo=UTC),
        heart_rate=60,
    )
    excluded = _measurement(
        patient=patient,
        device=wearable_device,
        metric_type="heart_rate",
        measured_at=datetime(2026, 7, 22, 1, tzinfo=UTC),
        heart_rate=84,
    )
    excluded.attribution_status = WearableMeasurement.AttributionStatus.AMBIGUOUS
    excluded.save(update_fields=["attribution_status"])

    summary = recalculate_daily_summary(patient.id, record_date)

    assert (summary.heart_rate_avg, summary.heart_rate_count) == (Decimal("72.00"), 1)


@pytest.mark.django_db
def test_summary_clears_empty_metrics_and_does_not_duplicate_on_recalculation(
    patient, wearable_device
):
    record_date = date(2026, 7, 22)
    _measurement(
        patient=patient,
        device=wearable_device,
        metric_type="heart_rate",
        measured_at=datetime(2026, 7, 22, 1, tzinfo=UTC),
        heart_rate=72,
    )

    first = recalculate_daily_summary(patient.id, record_date)
    second = recalculate_daily_summary(patient.id, record_date)

    assert first.pk == second.pk
    assert WearableDailySummary.objects.filter(patient=patient, record_date=record_date).count() == 1
    assert (second.systolic_avg, second.diastolic_avg, second.blood_pressure_count) == (
        None,
        None,
        0,
    )
    assert (
        second.blood_oxygen_avg,
        second.blood_oxygen_min,
        second.blood_oxygen_max,
        second.blood_oxygen_count,
    ) == (None, None, None, 0)
    assert second.steps is None
    assert second.steps_attribution_status == WearableDailySummary.AttributionStatus.OUTSIDE_BINDING
