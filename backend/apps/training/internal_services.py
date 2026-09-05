import hashlib
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from hmac import compare_digest

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Q
from motion_analysis_contract import WorkerCapability, capability_key

from .motion_analysis_storage import AnalysisStorageGrant, issue_storage_grant
from .video_models import MotionAnalysisJob


_STAGE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
_CAPABILITY_FIELDS = (
    "action_source_key",
    "algorithm_version",
    "rule_version",
    "parameter_version",
)
_logger = logging.getLogger(__name__)


class LeaseUnavailable(Exception):
    pass


class StorageGrantUnavailable(Exception):
    pass


@dataclass(frozen=True, repr=False)
class ClaimedMotionJob:
    job: MotionAnalysisJob
    lease_token: str = field(repr=False)
    storage_grant: AnalysisStorageGrant = field(repr=False)

    def __repr__(self):
        return (
            f"ClaimedMotionJob(job_id={self.job.id!r}, "
            "lease_credential=<redacted>, storage_credentials=<redacted>)"
        )


def _control_plane_timings():
    lease_seconds = settings.PP_MCARE_JOB_LEASE_SECONDS
    heartbeat_seconds = settings.PP_MCARE_HEARTBEAT_INTERVAL_SECONDS
    if (
        isinstance(lease_seconds, bool)
        or not isinstance(lease_seconds, int)
        or lease_seconds <= 0
        or isinstance(heartbeat_seconds, bool)
        or not isinstance(heartbeat_seconds, int)
        or heartbeat_seconds <= 0
        or heartbeat_seconds >= lease_seconds
    ):
        raise ImproperlyConfigured("pp-mcare 租约与心跳配置无效")
    return lease_seconds, heartbeat_seconds


def _capability_filter(capabilities):
    keys = {capability_key(capability) for capability in capabilities}
    compatible = Q()
    for action_source_key, algorithm_version, rule_version, parameter_version in keys:
        compatible |= Q(
            action_source_key=action_source_key,
            algorithm_version=algorithm_version,
            rule_version=rule_version,
            parameter_version=parameter_version,
        )
    return compatible if keys else None


def _capability_payload(capability):
    return dict(zip(_CAPABILITY_FIELDS, capability_key(capability), strict=True))


def _log_incompatible_pending_job(*, worker_id, capabilities, compatible):
    if compatible is not None:
        compatible_pending_exists = MotionAnalysisJob.objects.filter(
            compatible,
            status=MotionAnalysisJob.Status.PENDING,
        ).exists()
        if compatible_pending_exists:
            return

    oldest_pending = (
        MotionAnalysisJob.objects.filter(status=MotionAnalysisJob.Status.PENDING)
        .order_by("created_at", "id")
        .values("id", *_CAPABILITY_FIELDS)
        .first()
    )
    if oldest_pending is None:
        return

    _logger.warning(
        "motion_analysis_claim_unavailable",
        extra={
            "reason_code": "no_compatible_capability",
            "oldest_pending_job_id": oldest_pending["id"],
            "required_capability": {
                field_name: oldest_pending[field_name] for field_name in _CAPABILITY_FIELDS
            },
            "worker_id": worker_id,
            "declared_capabilities": [
                _capability_payload(capability) for capability in capabilities[:32]
            ],
        },
    )


@transaction.atomic
def claim_next_job(
    *,
    worker_id: str,
    capabilities: list[WorkerCapability],
    now,
) -> ClaimedMotionJob | None:
    lease_seconds, _heartbeat_seconds = _control_plane_timings()
    compatible = _capability_filter(capabilities)
    if compatible is None:
        _log_incompatible_pending_job(
            worker_id=worker_id,
            capabilities=capabilities,
            compatible=compatible,
        )
        return None

    job = (
        MotionAnalysisJob.objects.select_for_update(skip_locked=True)
        .select_related("training_video")
        .filter(compatible, status=MotionAnalysisJob.Status.PENDING)
        .order_by("created_at", "id")
        .first()
    )
    if job is None:
        _log_incompatible_pending_job(
            worker_id=worker_id,
            capabilities=capabilities,
            compatible=compatible,
        )
        return None

    lease_token = secrets.token_urlsafe(32)
    job.status = MotionAnalysisJob.Status.RUNNING
    job.worker_id = worker_id
    job.lease_token_hash = hashlib.sha256(lease_token.encode()).hexdigest()
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.last_heartbeat_at = now
    job.started_at = now
    job.current_stage = ""
    job.save(
        update_fields=[
            "status",
            "worker_id",
            "lease_token_hash",
            "lease_expires_at",
            "last_heartbeat_at",
            "started_at",
            "current_stage",
            "updated_at",
        ]
    )
    try:
        storage_grant = issue_storage_grant(job, now)
    except Exception as exc:
        raise StorageGrantUnavailable("存储授权暂不可用") from exc
    return ClaimedMotionJob(
        job=job,
        lease_token=lease_token,
        storage_grant=storage_grant,
    )


@transaction.atomic
def heartbeat_job(*, job_id: int, lease_token: str, stage: str, now) -> MotionAnalysisJob:
    lease_seconds, _heartbeat_seconds = _control_plane_timings()
    if not isinstance(stage, str) or not _STAGE_PATTERN.fullmatch(stage):
        raise LeaseUnavailable("租约不可用")

    job = MotionAnalysisJob.objects.select_for_update().filter(pk=job_id).first()
    supplied_digest = hashlib.sha256(lease_token.encode()).hexdigest()
    if (
        job is None
        or job.status != MotionAnalysisJob.Status.RUNNING
        or job.lease_expires_at is None
        or job.lease_expires_at <= now
        or not compare_digest(supplied_digest, job.lease_token_hash)
    ):
        raise LeaseUnavailable("租约不可用")

    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.last_heartbeat_at = now
    job.current_stage = stage
    job.save(
        update_fields=[
            "lease_expires_at",
            "last_heartbeat_at",
            "current_stage",
            "updated_at",
        ]
    )
    return job
