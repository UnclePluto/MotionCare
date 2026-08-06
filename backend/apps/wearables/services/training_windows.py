from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from django.db.models import Q

from apps.wearables.models import WearableMeasurement

if TYPE_CHECKING:
    from apps.training.models import TrainingVideo

ONE_DECIMAL = Decimal("0.1")


def _average(values):
    if not values:
        return None
    result = (sum(Decimal(value) for value in values) / Decimal(len(values))).quantize(
        ONE_DECIMAL,
        rounding=ROUND_HALF_UP,
    )
    return float(result)


def _scalar_statistics(values):
    return {
        "average": _average(values),
        "maximum": max(values),
        "minimum": min(values),
        "count": len(values),
    }


def training_video_wearable_window(video: "TrainingVideo") -> dict:
    if video.training_started_at is None or video.training_ended_at is None:
        return {"available": False}

    points = (
        WearableMeasurement.objects.filter(
            patient_id=video.project_patient.patient_id,
            attribution_status=WearableMeasurement.AttributionStatus.ATTRIBUTED,
            measured_at__gte=video.training_started_at,
            measured_at__lte=video.training_ended_at,
        )
        .filter(
            Q(
                metric_type=WearableMeasurement.MetricType.HEART_RATE,
                heart_rate__isnull=False,
            )
            | Q(
                metric_type=WearableMeasurement.MetricType.BLOOD_PRESSURE,
                systolic__isnull=False,
                diastolic__isnull=False,
            )
            | Q(
                metric_type=WearableMeasurement.MetricType.BLOOD_OXYGEN,
                blood_oxygen__isnull=False,
            )
        )
        .order_by("measured_at", "id")
    )

    heart_rate_points = []
    blood_pressure_points = []
    blood_oxygen_points = []
    for point in points:
        measured_at = point.measured_at.isoformat()
        if point.metric_type == WearableMeasurement.MetricType.HEART_RATE:
            heart_rate_points.append({"measured_at": measured_at, "value": point.heart_rate})
        elif point.metric_type == WearableMeasurement.MetricType.BLOOD_PRESSURE:
            blood_pressure_points.append(
                {
                    "measured_at": measured_at,
                    "systolic": point.systolic,
                    "diastolic": point.diastolic,
                }
            )
        else:
            blood_oxygen_points.append({"measured_at": measured_at, "value": point.blood_oxygen})

    metrics = {}
    if heart_rate_points:
        heart_rate_values = [point["value"] for point in heart_rate_points]
        metrics["heart_rate"] = {
            "points": heart_rate_points,
            "statistics": _scalar_statistics(heart_rate_values),
        }
    if blood_pressure_points:
        systolic_values = [point["systolic"] for point in blood_pressure_points]
        diastolic_values = [point["diastolic"] for point in blood_pressure_points]
        metrics["blood_pressure"] = {
            "points": blood_pressure_points,
            "statistics": {
                "systolic": {
                    "average": _average(systolic_values),
                    "maximum": max(systolic_values),
                    "minimum": min(systolic_values),
                },
                "diastolic": {
                    "average": _average(diastolic_values),
                    "maximum": max(diastolic_values),
                    "minimum": min(diastolic_values),
                },
                "count": len(blood_pressure_points),
            },
        }
    if blood_oxygen_points:
        metrics["blood_oxygen"] = {"points": blood_oxygen_points}

    if not metrics:
        return {"available": False}
    return {
        "available": True,
        "training_started_at": video.training_started_at.isoformat(),
        "training_ended_at": video.training_ended_at.isoformat(),
        "metrics": metrics,
    }
