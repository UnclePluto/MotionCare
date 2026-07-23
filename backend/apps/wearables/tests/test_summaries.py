import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from apps.patients.models import Patient
from apps.wearables.models import (
    WearableBinding,
    WearableDailySource,
    WearableDailySummary,
    WearableMeasurement,
)
from apps.wearables.providers import ProviderDailySteps
from apps.wearables.services.attribution import attribute_daily_steps
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


def _daily_steps(record_date):
    return ProviderDailySteps(
        record_date=record_date,
        steps=5821,
        distance=None,
        calorie=None,
        raw_payload={"Date": record_date.isoformat(), "Steps": 5821},
    )


def _other_patient(doctor):
    return Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.UNKNOWN,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )


@pytest.mark.django_db
def test_recalculate_daily_summary_aggregates_attributed_raw_data(
    patient, doctor, wearable_device
):
    record_date = date(2026, 7, 22)
    binding = WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 20, tzinfo=UTC),
        bound_by=doctor,
    )
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
        binding=binding,
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


@pytest.mark.django_db
def test_recalculate_revalidates_steps_after_midday_unbinding(patient, doctor, wearable_device):
    record_date = date(2026, 7, 22)
    binding = WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 20, tzinfo=UTC),
        bound_by=doctor,
    )
    source = attribute_daily_steps(wearable_device, _daily_steps(record_date))
    assert source.attribution_status == WearableDailySource.AttributionStatus.ATTRIBUTED

    binding.unbound_at = datetime(2026, 7, 22, 7, tzinfo=UTC)
    binding.unbound_by = doctor
    binding.save(update_fields=["unbound_at", "unbound_by", "updated_at"])

    summary = recalculate_daily_summary(patient.id, record_date)
    source.refresh_from_db()

    assert source.binding is None
    assert source.patient is None
    assert source.attribution_status == WearableDailySource.AttributionStatus.AMBIGUOUS
    assert summary.steps is None


@pytest.mark.django_db
def test_recalculate_revalidates_steps_after_midday_device_swap(
    patient, doctor, wearable_device
):
    record_date = date(2026, 7, 22)
    other_patient = _other_patient(doctor)
    first_binding = WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 20, tzinfo=UTC),
        bound_by=doctor,
    )
    source = attribute_daily_steps(wearable_device, _daily_steps(record_date))
    assert source.attribution_status == WearableDailySource.AttributionStatus.ATTRIBUTED

    swap_at = datetime(2026, 7, 22, 7, tzinfo=UTC)
    first_binding.unbound_at = swap_at
    first_binding.unbound_by = doctor
    first_binding.save(update_fields=["unbound_at", "unbound_by", "updated_at"])
    WearableBinding.objects.create(
        patient=other_patient,
        device=wearable_device,
        bound_at=swap_at,
        bound_by=doctor,
    )

    new_summary = recalculate_daily_summary(other_patient.id, record_date)
    source.refresh_from_db()

    assert source.binding is None
    assert source.patient is None
    assert source.attribution_status == WearableDailySource.AttributionStatus.AMBIGUOUS
    assert new_summary.steps is None

    old_summary = recalculate_daily_summary(patient.id, record_date)

    assert old_summary.steps is None


@pytest.mark.django_db
def test_locked_recalculation_reads_other_metric_added_after_lock(
    monkeypatch, patient, doctor, wearable_device
):
    record_date = date(2026, 7, 22)
    binding = WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 20, tzinfo=UTC),
        bound_by=doctor,
    )
    WearableDailySource.objects.create(
        provider=wearable_device.provider,
        device=wearable_device,
        binding=binding,
        patient=patient,
        record_date=record_date,
        steps=5821,
        attribution_status=WearableDailySource.AttributionStatus.ATTRIBUTED,
        raw_payload={},
    )
    from apps.wearables.services import summaries

    original_lock = summaries._lock_summary_scope

    def add_heart_rate_after_lock(patient_id):
        original_lock(patient_id)
        _measurement(
            patient=patient,
            device=wearable_device,
            metric_type="heart_rate",
            measured_at=datetime(2026, 7, 22, 2, tzinfo=UTC),
            heart_rate=72,
        )

    monkeypatch.setattr(summaries, "_lock_summary_scope", add_heart_rate_after_lock)

    summary = recalculate_daily_summary(patient.id, record_date)

    assert summary.steps == 5821
    assert (summary.heart_rate_avg, summary.heart_rate_count) == (Decimal("72.00"), 1)
