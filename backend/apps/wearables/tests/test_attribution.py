from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from apps.patients.models import Patient
from apps.wearables.models import WearableBinding, WearableDailySource, WearableMeasurement
from apps.wearables.providers import ProviderDailySteps, ProviderMeasurement
from apps.wearables.services.attribution import (
    attribute_daily_steps,
    attribute_measurement,
    resolve_binding,
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
def test_measurement_at_unbound_at_is_not_old_patient(patient, doctor, wearable_device):
    start = datetime(2026, 7, 20, tzinfo=UTC)
    end = datetime(2026, 7, 22, tzinfo=UTC)
    WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=start,
        unbound_at=end,
        bound_by=doctor,
        unbound_by=doctor,
    )

    assert resolve_binding(wearable_device, end) is None


@pytest.mark.django_db
def test_measurement_is_attributed_and_repeated_payload_is_idempotent(
    patient, doctor, wearable_device
):
    binding = WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 20, tzinfo=UTC),
        bound_by=doctor,
    )
    point = ProviderMeasurement(
        metric_type="heart_rate",
        measured_at=datetime(2026, 7, 22, 2, tzinfo=UTC),
        values={"heart_rate": 72},
        raw_payload={"HeartRate": 72},
    )

    first = attribute_measurement(wearable_device, point)
    second = attribute_measurement(wearable_device, point)

    assert first.pk == second.pk
    assert WearableMeasurement.objects.count() == 1
    assert first.binding_id == binding.id
    assert first.patient_id == patient.id
    assert first.attribution_status == WearableMeasurement.AttributionStatus.ATTRIBUTED
    assert len(first.source_fingerprint) == 64


@pytest.mark.django_db
def test_measurement_outside_binding_is_not_attached_to_current_patient(
    patient, doctor, wearable_device
):
    WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 22, 3, tzinfo=UTC),
        bound_by=doctor,
    )

    measurement = attribute_measurement(
        wearable_device,
        ProviderMeasurement(
            metric_type="blood_oxygen",
            measured_at=datetime(2026, 7, 22, 2, tzinfo=UTC),
            values={"blood_oxygen": 96},
            raw_payload={"BloodOxygen": 96},
        ),
    )

    assert measurement.binding is None
    assert measurement.patient is None
    assert measurement.attribution_status == WearableMeasurement.AttributionStatus.OUTSIDE_BINDING


@pytest.mark.django_db
def test_overlapping_historical_bindings_leave_measurement_ambiguous(
    patient, doctor, wearable_device
):
    other_patient = _other_patient(doctor)
    WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 20, tzinfo=UTC),
        unbound_at=datetime(2026, 7, 24, tzinfo=UTC),
        bound_by=doctor,
        unbound_by=doctor,
    )
    WearableBinding.objects.create(
        patient=other_patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 21, tzinfo=UTC),
        unbound_at=datetime(2026, 7, 25, tzinfo=UTC),
        bound_by=doctor,
        unbound_by=doctor,
    )

    measurement = attribute_measurement(
        wearable_device,
        ProviderMeasurement(
            metric_type="heart_rate",
            measured_at=datetime(2026, 7, 22, tzinfo=UTC),
            values={"heart_rate": 72},
            raw_payload={"HeartRate": 72},
        ),
    )

    assert measurement.binding is None
    assert measurement.patient is None
    assert measurement.attribution_status == WearableMeasurement.AttributionStatus.AMBIGUOUS


@pytest.mark.django_db
def test_daily_steps_use_shanghai_day_boundaries_converted_to_utc(
    patient, doctor, wearable_device
):
    binding = WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 21, 15, 59, tzinfo=UTC),
        unbound_at=datetime(2026, 7, 22, 16, tzinfo=UTC),
        bound_by=doctor,
        unbound_by=doctor,
    )

    source = attribute_daily_steps(
        wearable_device,
        ProviderDailySteps(
            record_date=date(2026, 7, 22),
            steps=5821,
            distance=Decimal("4.2"),
            calorie=Decimal("200.0"),
            raw_payload={"Date": "2026-07-22", "Steps": 5821},
        ),
    )

    assert source.binding_id == binding.id
    assert source.patient_id == patient.id
    assert source.attribution_status == WearableDailySource.AttributionStatus.ATTRIBUTED


@pytest.mark.django_db
def test_daily_steps_midday_binding_is_ambiguous(patient, doctor, wearable_device):
    WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 22, 2, tzinfo=UTC),
        bound_by=doctor,
    )

    source = attribute_daily_steps(
        wearable_device,
        ProviderDailySteps(
            record_date=date(2026, 7, 22),
            steps=5821,
            distance=None,
            calorie=None,
            raw_payload={"Date": "2026-07-22", "Steps": 5821},
        ),
    )

    assert source.binding is None
    assert source.patient is None
    assert source.attribution_status == WearableDailySource.AttributionStatus.AMBIGUOUS


@pytest.mark.django_db
def test_daily_steps_device_swap_is_ambiguous_for_both_patients(
    patient, doctor, wearable_device
):
    other_patient = _other_patient(doctor)
    swap_at = datetime(2026, 7, 22, 7, tzinfo=UTC)
    WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=datetime(2026, 7, 20, tzinfo=UTC),
        unbound_at=swap_at,
        bound_by=doctor,
        unbound_by=doctor,
    )
    WearableBinding.objects.create(
        patient=other_patient,
        device=wearable_device,
        bound_at=swap_at,
        bound_by=doctor,
    )

    source = attribute_daily_steps(
        wearable_device,
        ProviderDailySteps(
            record_date=date(2026, 7, 22),
            steps=5821,
            distance=None,
            calorie=None,
            raw_payload={"Date": "2026-07-22", "Steps": 5821},
        ),
    )

    assert source.binding is None
    assert source.patient is None
    assert source.attribution_status == WearableDailySource.AttributionStatus.AMBIGUOUS
