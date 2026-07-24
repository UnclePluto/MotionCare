from datetime import UTC, datetime, time, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

from django.db.models import Max
from django.db.models import Q
from django.http import Http404

from apps.wearables.models import (
    WearableBinding,
    WearableDailySummary,
    WearableMeasurement,
    WearableSyncRun,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
MEASUREMENT_METRICS = {"heart_rate", "blood_pressure", "blood_oxygen"}
BUCKET_MINUTES = {"5m": 5, "15m": 15, "30m": 30, "1h": 60}


def day_bounds(record_date):
    start = datetime.combine(record_date, time.min, tzinfo=SHANGHAI_TZ)
    return start, start + timedelta(days=1)


def _utc(value):
    return value.astimezone(UTC)


def _serialize_datetime(value):
    return value.astimezone(SHANGHAI_TZ).isoformat()


def resolve_patient_scope(user, *, patient_id, project_patient_id=None):
    from apps.training.tracking import accessible_project_patients

    accessible = accessible_project_patients(user)
    if not accessible.filter(patient_id=patient_id).exists():
        raise Http404
    if project_patient_id is None:
        return None
    project_patient = accessible.filter(pk=project_patient_id, patient_id=patient_id).first()
    if project_patient is None:
        raise Http404
    return project_patient


def project_window(project_patient, *, start, end):
    request_start, request_end = day_bounds(start)[0], day_bounds(end)[1]
    if project_patient is None:
        return request_start, request_end
    window_start = max(request_start, project_patient.enrolled_at.astimezone(SHANGHAI_TZ))
    completed_at = project_patient.project.completed_at
    window_end = min(
        request_end,
        completed_at.astimezone(SHANGHAI_TZ) if completed_at else request_end,
    )
    return window_start, window_end


def _full_days(start, end):
    day = start.date()
    final_day = end.date()
    result = []
    while day <= final_day:
        day_start, day_end = day_bounds(day)
        if day_start >= start and day_end <= end:
            result.append(day)
        day += timedelta(days=1)
    return result


def measurements(*, user, patient_id, project_patient_id, metric_type, start, end, bucket):
    project_patient = resolve_patient_scope(
        user, patient_id=patient_id, project_patient_id=project_patient_id
    )
    range_start, range_end = project_window(project_patient, start=start, end=end)
    queryset = WearableMeasurement.objects.filter(
        patient_id=patient_id,
        metric_type=metric_type,
        attribution_status=WearableMeasurement.AttributionStatus.ATTRIBUTED,
        measured_at__gte=_utc(range_start),
        measured_at__lt=_utc(range_end),
    ).order_by("measured_at", "id")
    if bucket == "raw":
        fields = {
            "heart_rate": ("heart_rate",),
            "blood_pressure": ("systolic", "diastolic"),
            "blood_oxygen": ("blood_oxygen",),
        }[metric_type]
        return {
            "metric_type": metric_type,
            "bucket": bucket,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "items": [
                {"measured_at": _serialize_datetime(point.measured_at), **{field: getattr(point, field) for field in fields}}
                for point in queryset
            ],
        }

    minutes = BUCKET_MINUTES[bucket]
    buckets = {}
    for point in queryset:
        local = point.measured_at.astimezone(SHANGHAI_TZ)
        minute = local.hour * 60 + local.minute
        floored = minute - minute % minutes
        bucket_start = local.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)
        buckets.setdefault(bucket_start, []).append(point)
    items = []
    for bucket_start, points in buckets.items():
        item = {
            "start": bucket_start.isoformat(),
            "end": (bucket_start + timedelta(minutes=minutes)).isoformat(),
            "count": len(points),
        }
        if metric_type == "heart_rate":
            item["heart_rate_avg"] = round(mean(point.heart_rate for point in points), 2)
        elif metric_type == "blood_pressure":
            item["systolic_avg"] = round(mean(point.systolic for point in points), 2)
            item["diastolic_avg"] = round(mean(point.diastolic for point in points), 2)
        else:
            item["blood_oxygen_avg"] = round(mean(point.blood_oxygen for point in points), 2)
        items.append(item)
    return {"metric_type": metric_type, "bucket": bucket, "start": start.isoformat(), "end": end.isoformat(), "items": items}


def daily_summaries(*, user, patient_id, project_patient_id, start, end):
    project_patient = resolve_patient_scope(
        user, patient_id=patient_id, project_patient_id=project_patient_id
    )
    window_start, window_end = project_window(project_patient, start=start, end=end)
    days = _full_days(window_start, window_end)
    summaries = WearableDailySummary.objects.filter(patient_id=patient_id, record_date__in=days).order_by("record_date")
    fields = (
        "heart_rate_avg", "heart_rate_min", "heart_rate_max", "heart_rate_count",
        "systolic_avg", "diastolic_avg", "blood_pressure_count",
        "blood_oxygen_avg", "blood_oxygen_min", "blood_oxygen_max", "blood_oxygen_count",
        "steps", "steps_attribution_status", "heart_rate_sync_status", "blood_pressure_sync_status",
        "blood_oxygen_sync_status", "steps_sync_status",
    )
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "items": [
            {"record_date": summary.record_date.isoformat(), **{field: (float(getattr(summary, field)) if field.endswith("_avg") and getattr(summary, field) is not None else getattr(summary, field)) for field in fields}}
            for summary in summaries
        ],
    }


def sync_status(*, user, patient_id):
    resolve_patient_scope(user, patient_id=patient_id)
    binding = WearableBinding.objects.select_related("device").filter(patient_id=patient_id, unbound_at__isnull=True).first()
    if binding is None:
        return {"is_bound": False, "device_short_code": None, "last_sync_at": None, "metrics": []}
    runs = WearableSyncRun.objects.filter(device=binding.device, status=WearableSyncRun.Status.SUCCEEDED)
    last_sync = runs.aggregate(last_sync_at=Max("created_at"))["last_sync_at"]
    latest = []
    for metric_type in ("heart_rate", "blood_pressure", "blood_oxygen", "steps"):
        run = runs.filter(metric_type=metric_type).order_by("-created_at", "-id").first()
        latest.append({
            "metric_type": metric_type,
            "status": run.status if run else None,
            "last_sync_at": _serialize_datetime(run.created_at) if run else None,
        })
    return {
        "is_bound": True,
        "device_short_code": binding.device.short_code,
        "last_sync_at": _serialize_datetime(last_sync) if last_sync else None,
        "metrics": latest,
    }


def _summary_metric(summary, metric_type):
    if metric_type == "heart_rate":
        return summary.heart_rate_avg, summary.heart_rate_min, summary.heart_rate_max, summary.heart_rate_count
    if metric_type == "blood_pressure":
        return summary.systolic_avg, None, None, summary.blood_pressure_count
    if metric_type == "blood_oxygen":
        return summary.blood_oxygen_avg, summary.blood_oxygen_min, summary.blood_oxygen_max, summary.blood_oxygen_count
    return summary.steps, None, None, 1 if summary.steps is not None and summary.steps_attribution_status == WearableDailySummary.AttributionStatus.ATTRIBUTED else 0


def project_summary(*, user, project_id, metric_type, start, end):
    from apps.training.tracking import accessible_project_patients

    project_patients = accessible_project_patients(user).filter(project_id=project_id)
    if not project_patients.exists():
        raise Http404
    groups = {}
    for project_patient in project_patients.select_related("group", "project", "patient"):
        group_id = project_patient.group_id
        groups.setdefault(group_id, {"group": {"id": group_id, "name": project_patient.group.name if project_patient.group else None}, "project_patients": []})["project_patients"].append(project_patient)
    response_groups = []
    for group in groups.values():
        eligible_days = 0
        values, minimums, maximums = [], [], []
        measurement_count = 0
        valid_data_days = 0
        for project_patient in group["project_patients"]:
            window_start, window_end = project_window(project_patient, start=start, end=end)
            days = _full_days(window_start, window_end)
            eligible_days += len(days)
            for summary in WearableDailySummary.objects.filter(patient_id=project_patient.patient_id, record_date__in=days):
                value, minimum, maximum, count = _summary_metric(summary, metric_type)
                if value is None or not count:
                    continue
                valid_data_days += 1
                values.append(float(value))
                measurement_count += count
                if minimum is not None:
                    minimums.append(minimum)
                if maximum is not None:
                    maximums.append(maximum)
        response_groups.append({
            "group": group["group"], "patient_count": len(group["project_patients"]),
            "eligible_days": eligible_days, "valid_data_days": valid_data_days,
            "mean": round(sum(values) / len(values), 2) if values else None,
            "min": min(minimums) if minimums else None,
            "max": max(maximums) if maximums else None,
            "measurement_count": measurement_count,
            "missing_rate": round((eligible_days - valid_data_days) / eligible_days * 100, 2) if eligible_days else None,
        })
    return {"project_id": project_id, "metric_type": metric_type, "start": start.isoformat(), "end": end.isoformat(), "groups": response_groups}


def last_30_days_data_completeness(patient_id, *, today):
    days = [today - timedelta(days=offset) for offset in range(30, 0, -1)]
    eligible = []
    for record_date in days:
        day_start, day_end = day_bounds(record_date)
        bindings = WearableBinding.objects.filter(
            patient_id=patient_id,
            bound_at__lte=_utc(day_start),
        ).filter(Q(unbound_at__isnull=True) | Q(unbound_at__gte=_utc(day_end)))
        if bindings.count() == 1:
            eligible.append(record_date)
    if not eligible:
        return None
    # Kept as Python evaluation so all database backends share the same NULL semantics.
    numerator = sum(
        1
        for summary in WearableDailySummary.objects.filter(patient_id=patient_id, record_date__in=eligible)
        if summary.heart_rate_count > 0
        or summary.blood_pressure_count > 0
        or summary.blood_oxygen_count > 0
        or (
            summary.steps is not None
            and summary.steps_attribution_status == WearableDailySummary.AttributionStatus.ATTRIBUTED
        )
    )
    return round(numerator / len(eligible) * 100, 2)


def tracking_wearable_summary(patient_id, *, today):
    binding = (
        WearableBinding.objects.select_related("device")
        .filter(patient_id=patient_id, unbound_at__isnull=True)
        .first()
    )
    if binding is None:
        return {
            "is_bound": False,
            "device_short_code": None,
            "last_sync_at": None,
            "last_30_days_data_completeness": last_30_days_data_completeness(
                patient_id, today=today
            ),
        }
    last_sync_at = WearableSyncRun.objects.filter(
        device=binding.device, status=WearableSyncRun.Status.SUCCEEDED
    ).aggregate(last_sync_at=Max("created_at"))["last_sync_at"]
    return {
        "is_bound": True,
        "device_short_code": binding.device.short_code,
        "last_sync_at": _serialize_datetime(last_sync_at) if last_sync_at else None,
        "last_30_days_data_completeness": last_30_days_data_completeness(
            patient_id, today=today
        ),
    }
