import pytest
from django.db import IntegrityError

from apps.health.models import DailyHealthRecord


@pytest.mark.django_db
def test_daily_health_unique_per_patient_and_date(patient):
    DailyHealthRecord.objects.create(patient=patient, record_date="2026-05-06", steps=1000)

    with pytest.raises(IntegrityError):
        DailyHealthRecord.objects.create(patient=patient, record_date="2026-05-06", steps=2000)

