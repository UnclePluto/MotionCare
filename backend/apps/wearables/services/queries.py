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


def measurements(
    *, user, patient_id, project_patient_id, metric_type, start, end, bucket, page, page_size
):
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
    )
    value_filters = {
        "heart_rate": {"heart_rate__isnull": False},
        "blood_pressure": {"systolic__isnull": False, "diastolic__isnull": False},
        "blood_oxygen": {"blood_oxygen__isnull": False},
    }
    queryset = queryset.filter(**value_filters[metric_type]).order_by("measured_at", "id")
    if bucket == "raw":
        fields = {
            "heart_rate": ("heart_rate",),
            "blood_pressure": ("systolic", "diastolic"),
            "blood_oxygen": ("blood_oxygen",),
        }[metric_type]
        total = queryset.count()
        start_index = (page - 1) * page_size
        if total and start_index >= total:
            raise ValueError("页码超出范围。")
        points = queryset[start_index : start_index + page_size]
        return {
            "metric_type": metric_type,
            "bucket": bucket,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "total": total,
            "page": page,
            "page_size": page_size,
            "next_page": page + 1 if start_index + page_size < total else None,
            "items": [
                {
                    "measured_at": _serialize_datetime(point.measured_at),
                    **{field: getattr(point, field) for field in fields},
                }
                for point in points
            ],
        }

    minutes = BUCKET_MINUTES[bucket]
    buckets = {}
    for point in queryset:
        local = point.measured_at.astimezone(SHANGHAI_TZ)
        minute = local.hour * 60 + local.minute
        floored = minute - minute % minutes
        bucket_start = local.replace(
            hour=floored // 60, minute=floored % 60, second=0, microsecond=0
        )
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
    return {
        "metric_type": metric_type,
        "bucket": bucket,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "items": items,
    }


def daily_summaries(*, user, patient_id, project_patient_id, start, end):
    project_patient = resolve_patient_scope(
        user, patient_id=patient_id, project_patient_id=project_patient_id
    )
    window_start, window_end = project_window(project_patient, start=start, end=end)
    days = _full_days(window_start, window_end)
    summaries = WearableDailySummary.objects.filter(
        patient_id=patient_id, record_date__in=days
    ).order_by("record_date")
    fields = (
        "heart_rate_avg",
        "heart_rate_min",
        "heart_rate_max",
        "heart_rate_count",
        "systolic_avg",
        "diastolic_avg",
        "blood_pressure_count",
        "blood_oxygen_avg",
        "blood_oxygen_min",
        "blood_oxygen_max",
        "blood_oxygen_count",
        "steps",
        "steps_attribution_status",
        "heart_rate_sync_status",
        "blood_pressure_sync_status",
        "blood_oxygen_sync_status",
        "steps_sync_status",
    )
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "items": [
            {
                "record_date": summary.record_date.isoformat(),
                **{
                    field: (
                        float(getattr(summary, field))
                        if field.endswith("_avg") and getattr(summary, field) is not None
                        else getattr(summary, field)
                    )
                    for field in fields
                },
            }
            for summary in summaries
        ],
    }


def sync_status(*, user, patient_id):
    resolve_patient_scope(user, patient_id=patient_id)
    binding = (
        WearableBinding.objects.select_related("device")
        .filter(patient_id=patient_id, unbound_at__isnull=True)
        .first()
    )
    if binding is None:
        return {"is_bound": False, "device_short_code": None, "last_sync_at": None, "metrics": []}
    runs = _runs_for_binding(binding)
    last_sync = runs.filter(status=WearableSyncRun.Status.SUCCEEDED).aggregate(
        last_sync_at=Max("created_at")
    )["last_sync_at"]
    latest = []
    for metric_type in ("heart_rate", "blood_pressure", "blood_oxygen", "steps"):
        run = runs.filter(metric_type=metric_type).order_by("-created_at", "-id").first()
        last_success_at = runs.filter(
            metric_type=metric_type, status=WearableSyncRun.Status.SUCCEEDED
        ).aggregate(value=Max("created_at"))["value"]
        latest.append(
            {
                "metric_type": metric_type,
                "status": run.status if run else None,
                "last_success_at": _serialize_datetime(last_success_at)
                if last_success_at
                else None,
            }
        )
    return {
        "is_bound": True,
        "device_short_code": binding.device.short_code,
        "last_sync_at": _serialize_datetime(last_sync) if last_sync else None,
        "metrics": latest,
    }


def _summary_metric(summary, metric_type):
    if metric_type == "heart_rate":
        return (
            summary.heart_rate_avg,
            summary.heart_rate_min,
            summary.heart_rate_max,
            summary.heart_rate_count,
        )
    if metric_type == "blood_pressure":
        return summary.systolic_avg, None, None, summary.blood_pressure_count
    if metric_type == "blood_oxygen":
        return (
            summary.blood_oxygen_avg,
            summary.blood_oxygen_min,
            summary.blood_oxygen_max,
            summary.blood_oxygen_count,
        )
    return (
        summary.steps,
        None,
        None,
        1
        if summary.steps is not None
        and summary.steps_attribution_status == WearableDailySummary.AttributionStatus.ATTRIBUTED
        else 0,
    )


def project_summary(*, user, project_id, metric_type, start, end):
    from apps.training.tracking import accessible_project_patients

    project_patients = accessible_project_patients(user).filter(project_id=project_id)
    if not project_patients.exists():
        raise Http404
    all_project_patients = list(project_patients.select_related("group", "project", "patient"))
    groups, patient_info = {}, {}
    for project_patient in all_project_patients:
        group_id = project_patient.group_id
        groups.setdefault(
            group_id,
            {
                "group": {
                    "id": group_id,
                    "name": project_patient.group.name if project_patient.group else None,
                },
                "patient_count": 0,
                "eligible_days": 0,
                "valid_days": set(),
                "values": [],
                "mins": [],
                "maxs": [],
                "diastolic": [],
            },
        )["patient_count"] += 1
        window_start, window_end = project_window(project_patient, start=start, end=end)
        full_days = set(_full_days(window_start, window_end))
        patient_info[project_patient.patient_id] = (group_id, window_start, window_end, full_days)
        groups[group_id]["eligible_days"] += len(full_days)
    patient_ids = list(patient_info)
    if metric_type in MEASUREMENT_METRICS:
        raw_queryset = WearableMeasurement.objects.filter(
            patient_id__in=patient_ids,
            metric_type=metric_type,
            attribution_status=WearableMeasurement.AttributionStatus.ATTRIBUTED,
            measured_at__gte=_utc(day_bounds(start)[0]),
            measured_at__lt=_utc(day_bounds(end)[1]),
        )
        if metric_type == "heart_rate":
            raw_queryset = raw_queryset.filter(heart_rate__isnull=False)
        for point in raw_queryset.order_by("patient_id", "measured_at", "id"):
            if metric_type == "blood_pressure" and (
                point.systolic is None or point.diastolic is None
            ):
                continue
            if metric_type == "blood_oxygen" and point.blood_oxygen is None:
                continue
            group_id, lower, upper, days = patient_info[point.patient_id]
            record_date = point.measured_at.astimezone(SHANGHAI_TZ).date()
            if not (_utc(lower) <= point.measured_at < _utc(upper)) or record_date not in days:
                continue
            acc = groups[group_id]
            value = (
                point.systolic if metric_type == "blood_pressure" else getattr(point, metric_type)
            )
            acc["values"].append(float(value))
            acc["mins"].append(value)
            acc["maxs"].append(value)
            acc["valid_days"].add((point.patient_id, record_date))
            if metric_type == "blood_pressure":
                acc["diastolic"].append(point.diastolic)
    else:
        for summary in WearableDailySummary.objects.filter(
            patient_id__in=patient_ids, record_date__gte=start, record_date__lte=end
        ):
            group_id, _, _, days = patient_info[summary.patient_id]
            if (
                summary.record_date not in days
                or summary.steps is None
                or summary.steps_attribution_status
                != WearableDailySummary.AttributionStatus.ATTRIBUTED
            ):
                continue
            acc = groups[group_id]
            acc["values"].append(float(summary.steps))
            acc["mins"].append(summary.steps)
            acc["maxs"].append(summary.steps)
            acc["valid_days"].add((summary.patient_id, summary.record_date))
    response_groups = []
    for group in groups.values():
        values, minimums, maximums = group["values"], group["mins"], group["maxs"]
        eligible_days, valid_data_days = group["eligible_days"], len(group["valid_days"])
        result = {
            "group": group["group"],
            "patient_count": group["patient_count"],
            "eligible_days": eligible_days,
            "valid_data_days": valid_data_days,
            "mean": round(sum(values) / len(values), 2) if values else None,
            "min": min(minimums) if minimums else None,
            "max": max(maximums) if maximums else None,
            "measurement_count": len(values),
            "missing_rate": round((eligible_days - valid_data_days) / eligible_days * 100, 2)
            if eligible_days
            else None,
        }
        if metric_type == "blood_pressure":
            result.pop("mean")
            result.pop("min")
            result.pop("max")
            d = group["diastolic"]
            result["systolic"] = {
                "mean": round(sum(values) / len(values), 2) if values else None,
                "min": min(minimums) if minimums else None,
                "max": max(maximums) if maximums else None,
            }
            result["diastolic"] = {
                "mean": round(sum(d) / len(d), 2) if d else None,
                "min": min(d) if d else None,
                "max": max(d) if d else None,
            }
        response_groups.append(result)
    return {
        "project_id": project_id,
        "metric_type": metric_type,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "groups": response_groups,
    }


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
        for summary in WearableDailySummary.objects.filter(
            patient_id=patient_id, record_date__in=eligible
        )
        if summary.heart_rate_count > 0
        or summary.blood_pressure_count > 0
        or summary.blood_oxygen_count > 0
        or (
            summary.steps is not None
            and summary.steps_attribution_status
            == WearableDailySummary.AttributionStatus.ATTRIBUTED
        )
    )
    return round(numerator / len(eligible) * 100, 2)


def tracking_wearable_summary(patient_id, *, today):
    return tracking_wearable_summaries([patient_id], today=today)[patient_id]


def tracking_wearable_summaries(patient_ids, *, today):
    patient_ids = list(dict.fromkeys(patient_ids))
    if not patient_ids:
        return {}
    bindings = list(
        WearableBinding.objects.select_related("device").filter(patient_id__in=patient_ids)
    )
    active = {binding.patient_id: binding for binding in bindings if binding.unbound_at is None}
    device_ids = {binding.device_id for binding in bindings}
    runs = list(
        WearableSyncRun.objects.filter(device_id__in=device_ids).order_by("created_at", "id")
    )
    days = [today - timedelta(days=offset) for offset in range(30, 0, -1)]
    summaries = {
        (summary.patient_id, summary.record_date): summary
        for summary in WearableDailySummary.objects.filter(
            patient_id__in=patient_ids, record_date__in=days
        )
    }
    result = {}
    for patient_id in patient_ids:
        patient_bindings = [binding for binding in bindings if binding.patient_id == patient_id]
        eligible = []
        for record_date in days:
            day_start, day_end = day_bounds(record_date)
            matching = [
                binding
                for binding in patient_bindings
                if binding.bound_at <= _utc(day_start)
                and (binding.unbound_at is None or binding.unbound_at >= _utc(day_end))
            ]
            if len(matching) == 1:
                eligible.append(record_date)
        numerator = sum(
            1
            for record_date in eligible
            if (summary := summaries.get((patient_id, record_date))) is not None
            and (
                summary.heart_rate_count > 0
                or summary.blood_pressure_count > 0
                or summary.blood_oxygen_count > 0
                or (
                    summary.steps is not None
                    and summary.steps_attribution_status
                    == WearableDailySummary.AttributionStatus.ATTRIBUTED
                )
            )
        )
        binding = active.get(patient_id)
        if binding is None:
            result[patient_id] = {
                "is_bound": False,
                "device_short_code": None,
                "last_sync_at": None,
                "last_30_days_data_completeness": round(numerator / len(eligible) * 100, 2)
                if eligible
                else None,
            }
            continue
        binding_runs = [
            run
            for run in runs
            if run.device_id == binding.device_id
            and run.created_at >= binding.bound_at
            and (binding.unbound_at is None or run.created_at < binding.unbound_at)
            and run.status == WearableSyncRun.Status.SUCCEEDED
        ]
        last_sync = binding_runs[-1].created_at if binding_runs else None
        result[patient_id] = {
            "is_bound": True,
            "device_short_code": binding.device.short_code,
            "last_sync_at": _serialize_datetime(last_sync) if last_sync else None,
            "last_30_days_data_completeness": round(numerator / len(eligible) * 100, 2)
            if eligible
            else None,
        }
    return result


def _legacy_tracking_wearable_summary(patient_id, *, today):
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
    last_sync_at = (
        _runs_for_binding(binding)
        .filter(status=WearableSyncRun.Status.SUCCEEDED)
        .aggregate(last_sync_at=Max("created_at"))["last_sync_at"]
    )
    return {
        "is_bound": True,
        "device_short_code": binding.device.short_code,
        "last_sync_at": _serialize_datetime(last_sync_at) if last_sync_at else None,
        "last_30_days_data_completeness": last_30_days_data_completeness(patient_id, today=today),
    }


def _runs_for_binding(binding):
    queryset = WearableSyncRun.objects.filter(
        device=binding.device,
        created_at__gte=binding.bound_at,
    )
    if binding.unbound_at is not None:
        queryset = queryset.filter(created_at__lt=binding.unbound_at)
    return queryset
