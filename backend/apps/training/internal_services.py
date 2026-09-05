import hashlib
import json
import logging
import math
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from hmac import compare_digest

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.db.models import Q
from motion_analysis_contract import (
    PROTOCOL_VERSION,
    CompletionPayload,
    ContractValidationError,
    WorkerCapability,
    capability_key,
)

from .models import MotionResultSource
from .motion_analysis_storage import (
    AnalysisStorageGrant,
    issue_storage_grant,
    queue_skeleton_cleanup,
    verify_skeleton_upload,
)
from .video_models import MotionAnalysisJob


_STAGE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
_FAILURE_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}\Z")
_LEASE_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,128}\Z")
_SENSITIVE_FAILURE_PATTERN = re.compile(
    r"(?i)(?:https?://|(?<![A-Za-z0-9])/(?:[^\s'\";,()]+)|"
    r"traceback|token|access[_-]?key|secret[_-]?key|credential|"
    r"(?:^|[^A-Za-z0-9_])(?:AK|SK)(?:$|[^A-Za-z0-9_]))"
)
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


class AnalysisConflict(Exception):
    pass


class CompletionRejected(Exception):
    pass


@dataclass(frozen=True, repr=False)
class FailurePayload:
    protocol_version: str
    lease_token: str = field(repr=False)
    idempotency_key: str
    failure_code: str
    summary: str = field(repr=False)
    stage_timings: dict[str, int | float]

    def __repr__(self):
        return (
            "FailurePayload("
            f"protocol_version={self.protocol_version!r}, lease_credential=<redacted>, "
            f"idempotency_key={self.idempotency_key!r}, "
            f"failure_code={self.failure_code!r}, summary=<redacted>, "
            f"stage_timing_count={len(self.stage_timings)!r})"
        )


def parse_failure_payload(payload: Mapping[str, object]) -> FailurePayload:
    allowed_fields = {
        "protocol_version",
        "lease_token",
        "idempotency_key",
        "failure_code",
        "summary",
        "stage_timings",
    }
    if not isinstance(payload, Mapping) or set(payload) != allowed_fields:
        raise ValueError("失败数据格式无效")

    protocol_version = payload.get("protocol_version")
    lease_token = payload.get("lease_token")
    idempotency_key = payload.get("idempotency_key")
    failure_code = payload.get("failure_code")
    summary = payload.get("summary")
    stage_timings = payload.get("stage_timings")
    if protocol_version != PROTOCOL_VERSION or not isinstance(protocol_version, str):
        raise ValueError("失败数据格式无效")
    if not isinstance(lease_token, str) or not _LEASE_TOKEN_PATTERN.fullmatch(lease_token):
        raise ValueError("失败数据格式无效")
    if not isinstance(idempotency_key, str) or not _IDEMPOTENCY_KEY_PATTERN.fullmatch(
        idempotency_key
    ):
        raise ValueError("失败数据格式无效")
    if not isinstance(failure_code, str) or not _FAILURE_CODE_PATTERN.fullmatch(failure_code):
        raise ValueError("失败数据格式无效")
    if (
        not isinstance(summary, str)
        or not summary
        or len(summary) > 2000
        or _SENSITIVE_FAILURE_PATTERN.search(summary)
    ):
        raise ValueError("失败数据格式无效")
    for secret in (settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY):
        if secret and secret in summary:
            raise ValueError("失败数据格式无效")
    if not isinstance(stage_timings, Mapping) or len(stage_timings) > 32:
        raise ValueError("失败数据格式无效")
    normalized_timings: dict[str, int | float] = {}
    for stage, value in stage_timings.items():
        if (
            not isinstance(stage, str)
            or not _STAGE_PATTERN.fullmatch(stage)
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("失败数据格式无效")
        normalized_timings[stage] = value
    return FailurePayload(
        protocol_version=protocol_version,
        lease_token=lease_token,
        idempotency_key=idempotency_key,
        failure_code=failure_code,
        summary=summary,
        stage_timings=normalized_timings,
    )


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


def _capabilities_digest(capabilities):
    canonical_payload = json.dumps(
        sorted(capability_key(capability) for capability in capabilities),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_payload.encode()).hexdigest()


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
            "declared_capability_count": len(capabilities),
            "declared_capabilities_sha256": _capabilities_digest(capabilities),
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


def _locked_job(job_id: int) -> MotionAnalysisJob:
    job = (
        MotionAnalysisJob.objects.select_for_update()
        .select_related("training_video")
        .filter(pk=job_id)
        .first()
    )
    if job is None:
        raise AnalysisConflict("任务不可用")
    return job


def _require_live_lease(job: MotionAnalysisJob, lease_token: str, now) -> None:
    if not isinstance(lease_token, str):
        raise LeaseUnavailable("租约不可用")
    supplied_digest = hashlib.sha256(lease_token.encode()).hexdigest()
    if (
        job.status != MotionAnalysisJob.Status.RUNNING
        or job.lease_expires_at is None
        or job.lease_expires_at <= now
        or not compare_digest(supplied_digest, job.lease_token_hash)
    ):
        raise LeaseUnavailable("租约不可用")


def _completion_payload(payload) -> CompletionPayload:
    if isinstance(payload, CompletionPayload):
        return payload
    try:
        return CompletionPayload.from_dict(payload)
    except (ContractValidationError, TypeError) as exc:
        raise CompletionRejected("完成数据无效") from exc


def _validate_execution_versions(job: MotionAnalysisJob, payload: CompletionPayload) -> None:
    expected = (
        job.algorithm_version,
        job.rule_version,
        job.parameter_version,
        job.subject_tracker_version,
    )
    supplied = (
        payload.algorithm_version,
        payload.rule_version,
        payload.parameter_version,
        payload.subject_tracker_version,
    )
    if supplied != expected:
        raise AnalysisConflict("任务执行版本不匹配")


def _validate_completion_metadata(payload: CompletionPayload) -> None:
    skeleton = payload.skeleton
    if (
        len(payload.idempotency_key) > 120
        or len(skeleton.bucket) > 120
        or len(skeleton.object_key) > 500
        or len(skeleton.object_hash) > 64
        or skeleton.duration_seconds < 0
        or skeleton.fps <= 0
        or skeleton.content_type != "video/mp4"
    ):
        raise CompletionRejected("完成数据无效")


def _clear_lease(job: MotionAnalysisJob, terminal_stage: str) -> None:
    job.lease_token_hash = ""
    job.lease_expires_at = None
    job.current_stage = terminal_stage


def _queue_skeleton_cleanup_if_allocated(job: MotionAnalysisJob) -> None:
    if job.skeleton_bucket and job.skeleton_object_key:
        queue_skeleton_cleanup(job)


@transaction.atomic
def complete_job(
    *,
    job_id: int,
    lease_token: str,
    idempotency_key: str,
    payload,
    now,
) -> MotionAnalysisJob:
    job = _locked_job(job_id)
    if job.status == MotionAnalysisJob.Status.SUCCEEDED:
        if job.completion_idempotency_key == idempotency_key:
            return job
        raise AnalysisConflict("任务已由不同请求完成")
    if job.status == MotionAnalysisJob.Status.FAILED:
        raise AnalysisConflict("失败任务不能完成")

    completion = _completion_payload(payload)
    if completion.lease_token != lease_token or completion.idempotency_key != idempotency_key:
        raise CompletionRejected("完成数据无效")
    _require_live_lease(job, lease_token, now)
    _validate_execution_versions(job, completion)
    _validate_completion_metadata(completion)
    if job.training_record is None:
        raise CompletionRejected("训练记录不可用")

    skeleton = completion.skeleton
    try:
        verify_skeleton_upload(job, skeleton.to_dict())
    except ValidationError as exc:
        raise CompletionRejected("骨架对象验证失败") from exc

    record = job.training_record
    record.set_motion_result(
        completion.counts,
        completion.quality_summary,
        MotionResultSource.ALGORITHM,
        None,
        now,
    )
    record.save(
        update_fields=[
            "motion_total_count",
            "motion_standard_count",
            "motion_nonstandard_count",
            "motion_quality_data",
            "motion_result_source",
            "motion_result_updated_by",
            "motion_result_updated_at",
            "updated_at",
        ]
    )

    job.status = MotionAnalysisJob.Status.SUCCEEDED
    job.completion_idempotency_key = idempotency_key
    job.total_count = completion.counts.total_count
    job.standard_count = completion.counts.standard_count
    job.nonstandard_count = completion.counts.nonstandard_count
    job.result_payload = completion.result_payload
    job.skeleton_object_hash = skeleton.object_hash
    job.skeleton_size_bytes = skeleton.size_bytes
    job.skeleton_duration_seconds = skeleton.duration_seconds
    job.skeleton_width = skeleton.width
    job.skeleton_height = skeleton.height
    job.skeleton_fps = skeleton.fps
    job.failure_code = ""
    job.failure_reason = ""
    job.finished_at = now
    _clear_lease(job, "completed")
    job.save(
        update_fields=[
            "status",
            "completion_idempotency_key",
            "total_count",
            "standard_count",
            "nonstandard_count",
            "result_payload",
            "skeleton_object_hash",
            "skeleton_size_bytes",
            "skeleton_duration_seconds",
            "skeleton_width",
            "skeleton_height",
            "skeleton_fps",
            "failure_code",
            "failure_reason",
            "finished_at",
            "lease_token_hash",
            "lease_expires_at",
            "current_stage",
            "updated_at",
        ]
    )
    return job


@transaction.atomic
def fail_job(
    *,
    job_id: int,
    lease_token: str,
    idempotency_key: str,
    failure,
    now,
) -> MotionAnalysisJob:
    job = _locked_job(job_id)
    if job.status == MotionAnalysisJob.Status.FAILED:
        if job.completion_idempotency_key == idempotency_key:
            return job
        raise AnalysisConflict("任务已由不同请求失败收口")
    if job.status == MotionAnalysisJob.Status.SUCCEEDED:
        raise AnalysisConflict("成功任务不能失败收口")

    failure_payload = (
        failure if isinstance(failure, FailurePayload) else parse_failure_payload(failure)
    )
    if (
        failure_payload.lease_token != lease_token
        or failure_payload.idempotency_key != idempotency_key
    ):
        raise CompletionRejected("失败数据无效")
    _require_live_lease(job, lease_token, now)
    job.status = MotionAnalysisJob.Status.FAILED
    job.completion_idempotency_key = idempotency_key
    job.failure_code = failure_payload.failure_code
    job.failure_reason = failure_payload.summary
    job.result_payload = {
        "failure_diagnostics": {"stage_timings": failure_payload.stage_timings}
    }
    job.finished_at = now
    _clear_lease(job, "failed")
    job.save(
        update_fields=[
            "status",
            "completion_idempotency_key",
            "failure_code",
            "failure_reason",
            "result_payload",
            "finished_at",
            "lease_token_hash",
            "lease_expires_at",
            "current_stage",
            "updated_at",
        ]
    )
    _queue_skeleton_cleanup_if_allocated(job)
    return job
