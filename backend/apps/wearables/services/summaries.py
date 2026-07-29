from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Avg, Count, Max, Min, Sum
from django.utils import timezone

from apps.patients.models import Patient
from apps.wearables.models import WearableDailySource, WearableDailySummary, WearableMeasurement
from apps.wearables.services.attribution import revalidate_daily_steps_for_patient

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _day_bounds_utc(record_date):
    day_start = datetime.combine(record_date, time.min, tzinfo=SHANGHAI_TZ)
    day_end = day_start + timedelta(days=1)
    return day_start.astimezone(UTC), day_end.astimezone(UTC)


def _measurements_for_day(patient_id, record_date, metric_type, value_fields):
    day_start, day_end = _day_bounds_utc(record_date)
    filters = {
        "patient_id": patient_id,
        "metric_type": metric_type,
        "attribution_status": WearableMeasurement.AttributionStatus.ATTRIBUTED,
        "measured_at__gte": day_start,
        "measured_at__lt": day_end,
    }
    filters.update({f"{field}__isnull": False for field in value_fields})
    return WearableMeasurement.objects.filter(**filters)


def _lock_summary_scope(patient_id):
    Patient.objects.select_for_update().get(pk=patient_id)


def recalculate_daily_summary(patient_id, record_date):
    """根据上海业务自然日内已归属的原始数据重算患者日汇总。"""
    with transaction.atomic():
        _lock_summary_scope(patient_id)
        revalidate_daily_steps_for_patient(patient_id, record_date)
        heart_rate = _measurements_for_day(patient_id, record_date, "heart_rate", ["heart_rate"])
        blood_pressure = _measurements_for_day(
            patient_id, record_date, "blood_pressure", ["systolic", "diastolic"]
        )
        blood_oxygen = _measurements_for_day(
            patient_id, record_date, "blood_oxygen", ["blood_oxygen"]
        )

        heart_rate_values = heart_rate.aggregate(
            heart_rate_avg=Avg("heart_rate"),
            heart_rate_min=Min("heart_rate"),
            heart_rate_max=Max("heart_rate"),
            heart_rate_count=Count("heart_rate"),
        )
        blood_pressure_values = blood_pressure.aggregate(
            systolic_avg=Avg("systolic"),
            diastolic_avg=Avg("diastolic"),
            blood_pressure_count=Count("systolic"),
        )
        blood_oxygen_values = blood_oxygen.aggregate(
            blood_oxygen_avg=Avg("blood_oxygen"),
            blood_oxygen_min=Min("blood_oxygen"),
            blood_oxygen_max=Max("blood_oxygen"),
            blood_oxygen_count=Count("blood_oxygen"),
        )
        steps_sources = WearableDailySource.objects.filter(
            patient_id=patient_id,
            record_date=record_date,
            attribution_status=WearableDailySource.AttributionStatus.ATTRIBUTED,
        )
        steps_values = steps_sources.aggregate(steps=Sum("steps"))

        summary, _ = WearableDailySummary.objects.update_or_create(
            patient_id=patient_id,
            record_date=record_date,
            defaults={
                **heart_rate_values,
                **blood_pressure_values,
                **blood_oxygen_values,
                "steps": steps_values["steps"],
                "steps_attribution_status": (
                    WearableDailySummary.AttributionStatus.ATTRIBUTED
                    if steps_sources.exists()
                    else WearableDailySummary.AttributionStatus.OUTSIDE_BINDING
                ),
                "calculated_at": timezone.now(),
            },
        )
    return summary
