from collections import defaultdict
from decimal import Decimal
from statistics import mean

from django.db.models import Count, F, Max, Prefetch, Q
from django.http import Http404
from django.utils import timezone

from apps.accounts.models import User
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient

from .models import MotionAnalysisJob, TrainingRecord

TRACKING_RANGES = {"7d", "30d", "weekly"}


def phone_masked(phone: str) -> str:
    if not phone:
        return ""
    if len(phone) <= 7:
        return "****"
    return f"{phone[:3]}****{phone[-4:]}"


def _is_admin(user) -> bool:
    return user.role in {User.Role.SUPER_ADMIN, User.Role.ADMIN}


def accessible_project_patients(user):
    qs = ProjectPatient.objects.select_related("patient", "project", "group")
    if _is_admin(user):
        return qs
    return qs.filter(
        Q(patient__primary_doctor=user) | Q(project__created_by=user) | Q(created_by=user)
    )


def serialize_patient(patient) -> dict:
    return {
        "id": patient.id,
        "name": patient.name,
        "phone_masked": phone_masked(patient.phone),
    }


def serialize_project_patient(project_patient: ProjectPatient) -> dict:
    return {
        "id": project_patient.id,
        "project": project_patient.project_id,
        "project_name": project_patient.project.name,
        "project_status": project_patient.project.status,
        "group": project_patient.group_id,
        "group_name": project_patient.group.name if project_patient.group_id else None,
        "enrolled_at": project_patient.enrolled_at.isoformat(),
    }


def _float_or_none(value):
    if value is None:
        return None
    return float(value)


def _round_or_none(values):
    if not values:
        return None
    return round(float(mean(values)), 2)


def _form_number(form_data, key):
    value = form_data.get(key) if isinstance(form_data, dict) else None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    return None


def _form_error_count(form_data):
    value = form_data.get("error_count") if isinstance(form_data, dict) else None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _form_difficulty(form_data):
    value = form_data.get("difficulty") if isinstance(form_data, dict) else None
    return value if isinstance(value, str) else None


def _form_raw_detail(form_data):
    value = form_data.get("raw_detail") if isinstance(form_data, dict) else None
    return value if isinstance(value, dict) else {}


def _raw_bool(form_data, key):
    value = _form_raw_detail(form_data).get(key)
    return value if isinstance(value, bool) else None


def _raw_text(form_data, key):
    value = _form_raw_detail(form_data).get(key)
    return value if isinstance(value, str) else None


def _raw_int(form_data, key):
    value = _form_raw_detail(form_data).get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def list_patient_tracking_summaries(user, *, q: str = "", today=None) -> list[dict]:
    today = today or timezone.localdate()
    last_30_start = today - timezone.timedelta(days=29)
    qs = accessible_project_patients(user)
    if q:
        qs = qs.filter(Q(patient__name__icontains=q) | Q(patient__phone__icontains=q))

    rows = (
        qs.values("patient_id", "patient__name", "patient__phone")
        .annotate(
            project_count=Count("id", distinct=True),
            last_training_at=Max("training_records__training_date"),
            last_30_days_completed_count=Count(
                "training_records",
                filter=Q(
                    training_records__status=TrainingRecord.Status.COMPLETED,
                    training_records__training_date__gte=last_30_start,
                    training_records__training_date__lte=today,
                ),
            ),
        )
        .order_by("patient__name", "patient_id")
    )
    return [
        {
            "patient": {
                "id": row["patient_id"],
                "name": row["patient__name"],
                "phone_masked": phone_masked(row["patient__phone"]),
            },
            "project_count": row["project_count"],
            "last_training_at": (
                row["last_training_at"].isoformat() if row["last_training_at"] else None
            ),
            "last_30_days_completed_count": row["last_30_days_completed_count"],
        }
        for row in rows
    ]


def current_prescription_for(project_patient: ProjectPatient):
    return (
        Prescription.objects.filter(
            project_patient=project_patient,
            status=Prescription.Status.ACTIVE,
        )
        .prefetch_related(
            "actions",
        )
        .order_by("-effective_at", "-id")
        .first()
    )


def _serialize_current_prescription(prescription: Prescription | None) -> dict | None:
    if prescription is None:
        return None
    return {
        "id": prescription.id,
        "version": prescription.version,
        "status": prescription.status,
        "effective_at": prescription.effective_at.isoformat()
        if prescription.effective_at
        else None,
    }


def current_week_bounds(today=None):
    today = today or timezone.localdate()
    start = today - timezone.timedelta(days=today.weekday())
    return start, start + timezone.timedelta(days=6)


def prescription_completion(project_patient: ProjectPatient, prescription: Prescription | None):
    if prescription is None:
        return []
    actions = list(prescription.actions.order_by("sort_order", "id"))
    action_ids = [action.id for action in actions]
    week_start, week_end = current_week_bounds()
    completed_counts = {
        row["prescription_action_id"]: row["count"]
        for row in TrainingRecord.objects.filter(
            project_patient=project_patient,
            prescription_action_id__in=action_ids,
            status=TrainingRecord.Status.COMPLETED,
            training_date__gte=week_start,
            training_date__lte=week_end,
        )
        .values("prescription_action_id")
        .annotate(count=Count("id"))
    }
    recent_dates = {
        row["prescription_action_id"]: row["recent"]
        for row in TrainingRecord.objects.filter(
            project_patient=project_patient,
            prescription_action_id__in=action_ids,
        )
        .values("prescription_action_id")
        .annotate(recent=Max("training_date"))
    }

    result = []
    for action in actions:
        completed_count = completed_counts.get(action.id, 0)
        target_count = action.weekly_target_count
        result.append(
            {
                "prescription_action": action.id,
                "action_name": action.action_name_snapshot,
                "internal_type": action.internal_type_snapshot,
                "action_type": action.action_type_snapshot,
                "target_count": target_count,
                "completed_count": completed_count,
                "completion_rate": round(completed_count / target_count * 100, 2)
                if target_count
                else 0,
                "recent_record_at": recent_dates[action.id].isoformat()
                if action.id in recent_dates and recent_dates[action.id]
                else None,
            }
        )
    return result


def _empty_day(day):
    return {
        "date": day.isoformat(),
        "completed_count": 0,
        "duration_minutes": 0,
        "game_scores": [],
    }


def trend(project_patient: ProjectPatient, *, range_value: str, today=None) -> dict:
    today = today or timezone.localdate()
    day_count = 7 if range_value == "7d" else 30
    start = today - timezone.timedelta(days=day_count - 1)
    days = [start + timezone.timedelta(days=offset) for offset in range(day_count)]
    buckets = {day: _empty_day(day) for day in days}
    weekly_buckets = defaultdict(
        lambda: {
            "completed_count": 0,
            "duration_minutes": 0,
            "game_scores": [],
        }
    )

    records = (
        TrainingRecord.objects.filter(
            project_patient=project_patient,
            training_date__gte=start,
            training_date__lte=today,
        )
        .select_related("prescription_action")
        .order_by("training_date", "id")
    )
    for record in records:
        if record.training_date not in buckets:
            continue
        day_bucket = buckets[record.training_date]
        duration = record.actual_duration_minutes or 0
        day_bucket["duration_minutes"] += duration
        week_start = record.training_date - timezone.timedelta(days=record.training_date.weekday())
        weekly_bucket = weekly_buckets[week_start]
        weekly_bucket["duration_minutes"] += duration
        if record.status == TrainingRecord.Status.COMPLETED:
            day_bucket["completed_count"] += 1
            weekly_bucket["completed_count"] += 1
        if (
            record.prescription_action.internal_type_snapshot == ActionLibraryItem.InternalType.GAME
            and record.score is not None
        ):
            score = float(record.score)
            day_bucket["game_scores"].append(score)
            weekly_bucket["game_scores"].append(score)

    daily = []
    for day in days:
        bucket = buckets[day]
        daily.append(
            {
                "date": bucket["date"],
                "completed_count": bucket["completed_count"],
                "duration_minutes": bucket["duration_minutes"],
                "game_average_score": _round_or_none(bucket["game_scores"]),
            }
        )

    moving_average = []
    for index, item in enumerate(daily):
        window = daily[max(0, index - 6) : index + 1]
        moving_average.append(
            {
                "date": item["date"],
                "completed_count_avg": round(
                    sum(day["completed_count"] for day in window) / len(window),
                    2,
                ),
                "duration_minutes_avg": round(
                    sum(day["duration_minutes"] for day in window) / len(window),
                    2,
                ),
            }
        )

    weekly = []
    first_week = start - timezone.timedelta(days=start.weekday())
    week_start = first_week
    while week_start <= today:
        bucket = weekly_buckets[week_start]
        weekly.append(
            {
                "week_start": week_start.isoformat(),
                "week_end": (week_start + timezone.timedelta(days=6)).isoformat(),
                "completed_count": bucket["completed_count"],
                "duration_minutes": bucket["duration_minutes"],
                "game_average_score": _round_or_none(bucket["game_scores"]),
            }
        )
        week_start += timezone.timedelta(days=7)

    return {"daily": daily, "moving_average": moving_average, "weekly": weekly}


def game_summary(project_patient: ProjectPatient, *, today=None) -> dict:
    today = today or timezone.localdate()
    start = today - timezone.timedelta(days=29)
    records = list(
        TrainingRecord.objects.filter(
            project_patient=project_patient,
            training_date__gte=start,
            training_date__lte=today,
            prescription_action__internal_type_snapshot=ActionLibraryItem.InternalType.GAME,
        )
        .select_related("prescription_action")
        .order_by("-training_date", "-id")
    )
    scores = [float(record.score) for record in records if record.score is not None]
    accuracies = [
        value
        for value in (_form_number(record.form_data, "accuracy_rate") for record in records)
        if value is not None
    ]
    error_counts = [
        value for value in (_form_error_count(record.form_data) for record in records) if value is not None
    ]

    by_action = {}
    for record in records:
        bucket = by_action.setdefault(
            record.prescription_action_id,
            {
                "prescription_action": record.prescription_action_id,
                "action_name": record.prescription_action.action_name_snapshot,
                "record_count": 0,
                "scores": [],
                "accuracies": [],
                "recent_record_at": record.training_date,
            },
        )
        bucket["record_count"] += 1
        if record.score is not None:
            bucket["scores"].append(float(record.score))
        accuracy = _form_number(record.form_data, "accuracy_rate")
        if accuracy is not None:
            bucket["accuracies"].append(accuracy)
        if record.training_date > bucket["recent_record_at"]:
            bucket["recent_record_at"] = record.training_date

    return {
        "average_score": _round_or_none(scores),
        "average_accuracy_rate": _round_or_none(accuracies),
        "total_error_count": sum(error_counts),
        "by_game": [
            {
                "prescription_action": item["prescription_action"],
                "action_name": item["action_name"],
                "record_count": item["record_count"],
                "average_score": _round_or_none(item["scores"]),
                "average_accuracy_rate": _round_or_none(item["accuracies"]),
                "recent_record_at": item["recent_record_at"].isoformat(),
            }
            for item in sorted(
                by_action.values(),
                key=lambda value: (value["recent_record_at"], value["prescription_action"]),
                reverse=True,
            )
        ],
    }


def recent_records(project_patient: ProjectPatient) -> list[dict]:
    records = (
        TrainingRecord.objects.filter(project_patient=project_patient)
        .select_related("prescription", "prescription_action", "video")
        .prefetch_related(
            Prefetch(
                "motion_analysis_jobs",
                queryset=MotionAnalysisJob.objects.order_by("-created_at", "-id"),
                to_attr="ordered_analysis_jobs",
            )
        )
        .order_by("-training_date", "-id")[:30]
    )
    rows = []
    for record in records:
        video = getattr(record, "video", None)
        latest_job = record.ordered_analysis_jobs[0] if record.ordered_analysis_jobs else None
        is_game = (
            record.prescription_action.internal_type_snapshot
            == ActionLibraryItem.InternalType.GAME
        )
        game_fields = (
            {
                "game_ended_early": _raw_bool(record.form_data, "ended_early"),
                "game_difficulty_adjust_reason": _raw_text(
                    record.form_data,
                    "difficulty_adjust_reason",
                ),
                "game_upload_mode": _raw_text(record.form_data, "upload_mode"),
                "game_retry_count": _raw_int(record.form_data, "retry_count"),
                "game_total_retry_count": _raw_int(record.form_data, "total_retry_count"),
            }
            if is_game
            else {
                "game_ended_early": None,
                "game_difficulty_adjust_reason": None,
                "game_upload_mode": None,
                "game_retry_count": None,
                "game_total_retry_count": None,
            }
        )
        rows.append(
            {
                "id": record.id,
                "training_date": record.training_date.isoformat(),
                "status": record.status,
                "prescription": record.prescription_id,
                "prescription_version": record.prescription.version,
                "prescription_action": record.prescription_action_id,
                "action_name": record.prescription_action.action_name_snapshot,
                "internal_type": record.prescription_action.internal_type_snapshot,
                "action_type": record.prescription_action.action_type_snapshot,
                "actual_duration_minutes": record.actual_duration_minutes,
                "score": _float_or_none(record.score),
                "game_accuracy_rate": _form_number(record.form_data, "accuracy_rate"),
                "game_error_count": _form_error_count(record.form_data),
                "game_difficulty": _form_difficulty(record.form_data),
                **game_fields,
                "note": record.note,
                "video_id": video.id if video else None,
                "video_status": video.status if video else None,
                "latest_analysis_status": latest_job.status if latest_job else None,
                "analysis_total_count": latest_job.total_count if latest_job else None,
                "analysis_standard_count": latest_job.standard_count if latest_job else None,
                "analysis_nonstandard_count": latest_job.nonstandard_count if latest_job else None,
            }
        )
    return rows


def _project_patients_for_patient(user, patient_id):
    return accessible_project_patients(user).filter(patient_id=patient_id)


def _select_project_patient(qs, *, project_patient_id=None):
    if project_patient_id is not None:
        selected = qs.filter(pk=project_patient_id).first()
        if selected is None:
            raise Http404
        return selected
    selected = (
        qs.annotate(last_training_at=Max("training_records__training_date"))
        .order_by(F("last_training_at").desc(nulls_last=True), "-enrolled_at", "-id")
        .first()
    )
    if selected is None:
        raise Http404
    return selected


def get_patient_tracking_detail(
    user,
    *,
    patient_id: int,
    project_patient_id: int | None = None,
    range_value: str = "30d",
) -> dict:
    if range_value not in TRACKING_RANGES:
        raise ValueError("range 只支持 7d、30d、weekly")
    qs = _project_patients_for_patient(user, patient_id)
    selected = _select_project_patient(qs, project_patient_id=project_patient_id)
    project_patients = list(qs.order_by("-enrolled_at", "-id"))
    active_prescription = current_prescription_for(selected)

    return {
        "patient": serialize_patient(selected.patient),
        "project_patients": [serialize_project_patient(item) for item in project_patients],
        "selected_project_patient": serialize_project_patient(selected),
        "current_prescription": _serialize_current_prescription(active_prescription),
        "prescription_completion": prescription_completion(selected, active_prescription),
        "trend": trend(selected, range_value=range_value),
        "game_summary": game_summary(selected),
        "recent_records": recent_records(selected),
    }
