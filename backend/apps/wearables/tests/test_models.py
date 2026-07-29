from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.patients.models import Patient
from apps.wearables.models import WearableBinding, WearableDevice


@pytest.mark.django_db
def test_device_external_identity_and_short_code_are_unique():
    WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-001",
        identifier_type="device_id",
        short_code="0826",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            WearableDevice.objects.create(
                provider="miwitracker",
                external_device_id="dev-001",
                identifier_type="device_id",
                short_code="1735",
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            WearableDevice.objects.create(
                provider="miwitracker",
                external_device_id="dev-002",
                identifier_type="device_id",
                short_code="0826",
            )


@pytest.mark.django_db
@pytest.mark.parametrize("short_code", ["826", "08A6"])
def test_device_short_code_must_be_four_digits_for_orm_writes(short_code):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            WearableDevice.objects.create(
                provider="miwitracker",
                external_device_id=f"dev-{short_code}",
                identifier_type="device_id",
                short_code=short_code,
            )


@pytest.mark.django_db
def test_patient_and_device_each_have_only_one_active_binding(patient, doctor):
    first = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-001",
        identifier_type="device_id",
        short_code="0826",
    )
    second = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-002",
        identifier_type="device_id",
        short_code="1735",
    )
    WearableBinding.objects.create(
        patient=patient,
        device=first,
        bound_at=timezone.now(),
        bound_by=doctor,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            WearableBinding.objects.create(
                patient=patient,
                device=second,
                bound_at=timezone.now(),
                bound_by=doctor,
            )

    other_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.UNKNOWN,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            WearableBinding.objects.create(
                patient=other_patient,
                device=first,
                bound_at=timezone.now(),
                bound_by=doctor,
            )


@pytest.mark.django_db
def test_binding_end_must_be_after_bound_at(patient, doctor):
    device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-001",
        identifier_type="device_id",
        short_code="0826",
    )
    bound_at = timezone.now()

    for unbound_at in (bound_at, bound_at - timedelta(seconds=1)):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                WearableBinding.objects.create(
                    patient=patient,
                    device=device,
                    bound_at=bound_at,
                    unbound_at=unbound_at,
                    bound_by=doctor,
                )


@pytest.mark.django_db
def test_patient_and_device_can_be_rebound_after_unbinding(patient, doctor):
    first = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-001",
        identifier_type="device_id",
        short_code="0826",
    )
    second = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-002",
        identifier_type="device_id",
        short_code="1735",
    )
    bound_at = timezone.now()
    WearableBinding.objects.create(
        patient=patient,
        device=first,
        bound_at=bound_at,
        unbound_at=bound_at + timedelta(seconds=1),
        bound_by=doctor,
        unbound_by=doctor,
    )

    WearableBinding.objects.create(
        patient=patient,
        device=second,
        bound_at=bound_at + timedelta(seconds=2),
        bound_by=doctor,
    )
    other_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.UNKNOWN,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )
    WearableBinding.objects.create(
        patient=other_patient,
        device=first,
        bound_at=bound_at + timedelta(seconds=2),
        bound_by=doctor,
    )
