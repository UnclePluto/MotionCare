import pytest
from django.db import IntegrityError
from django.utils import timezone

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
        WearableDevice.objects.create(
            provider="miwitracker",
            external_device_id="dev-001",
            identifier_type="device_id",
            short_code="1735",
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
        WearableBinding.objects.create(
            patient=patient,
            device=second,
            bound_at=timezone.now(),
            bound_by=doctor,
        )
