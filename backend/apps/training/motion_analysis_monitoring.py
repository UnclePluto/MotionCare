from dataclasses import asdict, dataclass

from django.db import transaction
from django.db.models import DateTimeField, Min
from django.db.models.functions import Coalesce
from django.utils import timezone

from .motion_analysis_storage import queue_skeleton_cleanup
from .video_models import MotionAnalysisJob


@dataclass(frozen=True)
class MotionAnalysisHealthSnapshot:
    pending_count: int
    oldest_pending_age_seconds: int
    running_count: int
    oldest_running_lease_age_seconds: int
    expired_running_lease_count: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _elapsed_seconds(now, earlier) -> int:
    if earlier is None:
        return 0
    return max(0, int((now - earlier).total_seconds()))


def motion_analysis_health_snapshot(now=None) -> MotionAnalysisHealthSnapshot:
    now = now or timezone.now()
    pending = MotionAnalysisJob.objects.filter(status=MotionAnalysisJob.Status.PENDING)
    running = MotionAnalysisJob.objects.filter(status=MotionAnalysisJob.Status.RUNNING)
    oldest_pending_at = pending.aggregate(value=Min("created_at"))["value"]
    oldest_running_activity_at = running.aggregate(
        value=Min(
            Coalesce(
                "last_heartbeat_at",
                "started_at",
                "created_at",
                output_field=DateTimeField(),
            )
        )
    )["value"]
    return MotionAnalysisHealthSnapshot(
        pending_count=pending.count(),
        oldest_pending_age_seconds=_elapsed_seconds(now, oldest_pending_at),
        running_count=running.count(),
        oldest_running_lease_age_seconds=_elapsed_seconds(now, oldest_running_activity_at),
        expired_running_lease_count=running.filter(lease_expires_at__lt=now).count(),
    )


def expire_stale_motion_analysis_jobs(now=None) -> int:
    now = now or timezone.now()
    stale_ids = list(
        MotionAnalysisJob.objects.filter(
            status=MotionAnalysisJob.Status.RUNNING,
            lease_expires_at__lt=now,
        )
        .order_by("lease_expires_at", "id")
        .values_list("id", flat=True)
    )
    expired_count = 0
    for job_id in stale_ids:
        with transaction.atomic():
            job = (
                MotionAnalysisJob.objects.select_for_update(skip_locked=True)
                .select_related("training_video")
                .filter(
                    pk=job_id,
                    status=MotionAnalysisJob.Status.RUNNING,
                    lease_expires_at__lt=now,
                )
                .first()
            )
            if job is None:
                continue
            job.status = MotionAnalysisJob.Status.FAILED
            job.failure_code = "lease_expired"
            job.failure_reason = "动作分析任务租约已过期"
            job.finished_at = now
            job.lease_token_hash = ""
            job.lease_expires_at = None
            job.current_stage = "lease_expired"
            job.save(
                update_fields=[
                    "status",
                    "failure_code",
                    "failure_reason",
                    "finished_at",
                    "lease_token_hash",
                    "lease_expires_at",
                    "current_stage",
                    "updated_at",
                ]
            )
            if job.skeleton_bucket and job.skeleton_object_key:
                queue_skeleton_cleanup(job)
            expired_count += 1
    return expired_count
