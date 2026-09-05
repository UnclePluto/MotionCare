from __future__ import annotations

import logging
import resource
import shutil
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from motion_analysis_contract import ClaimedJob, SkeletonArtifact

from .api_client import (
    MotionCareClient,
    MotionCareConflictError,
    MotionCareUnavailableError,
)
from .config import Settings
from .pipeline import LocalAnalysisResult, run_local_pipeline
from .safe_logging import configure_safe_logging, install_safe_logging
from .storage import (
    StoragePermanentError,
    StorageTransientError,
    UploadedObject,
    download_original,
    upload_skeleton,
)
from .workspace import TaskWorkspace


_logger = logging.getLogger(__name__)


class LeaseLostError(RuntimeError):
    pass


class JobAlreadyFinalized(RuntimeError):
    """Processor has already attempted the single allowed terminal report."""


class ResourceInsufficientError(RuntimeError):
    pass


class HeartbeatLease:
    def __init__(
        self,
        client,
        job: ClaimedJob,
        *,
        wait: Callable[[float], bool] | None = None,
    ) -> None:
        self._client = client
        self._job = job
        self._stop = threading.Event()
        self._wait = wait or self._stop.wait
        self._lock = threading.Lock()
        self._stage = "preflight"
        self._failure: LeaseLostError | None = None
        self._thread: threading.Thread | None = None

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def __enter__(self) -> HeartbeatLease:
        self._thread = threading.Thread(
            target=self._pump,
            name=f"pp-mcare-heartbeat-{self._job.job_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.stop()

    def _pump(self) -> None:
        while not self._stop.is_set():
            if self._wait(float(self._job.heartbeat_interval_seconds)):
                return
            if self._stop.is_set():
                return
            with self._lock:
                stage = self._stage
            try:
                self._client.heartbeat(self._job.job_id, self._job.lease_token, stage)
            except Exception:
                with self._lock:
                    self._failure = LeaseLostError("任务租约已失效")
                self._stop.set()
                return

    def checkpoint(self, stage: str) -> None:
        if stage not in {"preflight", "download", "inference", "encoding", "upload", "complete"}:
            raise ValueError("心跳阶段无效")
        with self._lock:
            self._stage = stage
            failure = self._failure
        if failure is not None:
            raise failure

    def raise_if_lost(self) -> None:
        with self._lock:
            failure = self._failure
        if failure is not None:
            raise failure

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                with self._lock:
                    self._failure = LeaseLostError("心跳线程无法停止")
                raise LeaseLostError("心跳线程无法停止")


@dataclass
class _StageTimer:
    timings: dict[str, float]
    stage: str
    job_id: int
    started: float = 0.0

    def __enter__(self):
        self.started = time.monotonic()
        _logger.info(
            "motion_analysis_stage_started",
            extra={"job_id": self.job_id, "stage": self.stage, "outcome": "started"},
        )
        return self

    def __exit__(self, exc_type, _value, _traceback):
        elapsed = max(0.0, (time.monotonic() - self.started) * 1000.0)
        self.timings[self.stage] = elapsed
        _logger.info(
            "motion_analysis_stage_finished",
            extra={
                "job_id": self.job_id,
                "stage": self.stage,
                "outcome": "failed" if exc_type is not None else "succeeded",
                "duration_ms": elapsed,
            },
        )


def _check_disk(settings: Settings, expected_size: int) -> int:
    free = shutil.disk_usage(settings.work_root).free
    required = max(256 * 1024 * 1024, expected_size * 3)
    if free < required:
        raise ResourceInsufficientError("磁盘空间不足")
    return free


def _resource_metrics(settings: Settings) -> dict[str, int]:
    try:
        import psutil

        maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss = int(maximum_rss if sys.platform == "darwin" else maximum_rss * 1024)
        memory = psutil.virtual_memory().available
        swap = psutil.swap_memory().used
        disk = shutil.disk_usage(settings.work_root).free
    except Exception:
        return {
            "peak_rss_bytes": 0,
            "system_available_memory_bytes": 0,
            "swap_used_bytes": 0,
            "disk_free_bytes": 0,
        }
    return {
        "peak_rss_bytes": int(rss),
        "system_available_memory_bytes": int(memory),
        "swap_used_bytes": int(swap),
        "disk_free_bytes": int(disk),
    }


def _skeleton_artifact(job: ClaimedJob, local: LocalAnalysisResult, upload: UploadedObject):
    media = local.media_metadata
    return SkeletonArtifact(
        bucket=job.upload.bucket,
        object_key=job.upload.object_key,
        object_hash=upload.object_hash,
        size_bytes=upload.size_bytes,
        duration_seconds=media.duration_seconds,
        width=media.width,
        height=media.height,
        fps=media.fps,
        content_type=media.content_type,
    )


def _failure_details(error: Exception, stage: str) -> tuple[str, str]:
    if isinstance(error, (LeaseLostError, MotionCareConflictError)):
        return "lease_lost", "任务租约已失效"
    if isinstance(error, ResourceInsufficientError):
        return "resource_insufficient", "计算资源不足"
    if stage == "download" and isinstance(error, (StoragePermanentError, StorageTransientError)):
        return "download_failed", "原视频下载或校验失败"
    if stage == "upload" and isinstance(error, (StoragePermanentError, StorageTransientError)):
        return "upload_failed", "骨架视频上传失败"
    return "analysis_failed", "动作分析失败"


def process_claimed_job(job: ClaimedJob, client, settings: Settings) -> None:
    if not isinstance(job, ClaimedJob):
        raise TypeError("job 必须是 ClaimedJob")
    completion_key = uuid.uuid4().hex
    failure_key = uuid.uuid4().hex
    timings: dict[str, float] = {}
    stage = "preflight"
    local: LocalAnalysisResult | None = None
    terminal_status: str | None = None
    workspace: TaskWorkspace | None = None
    configure_safe_logging(
        secrets=(settings.service_token, job.lease_token, job.download.url, job.upload.token)
    )
    try:
        with TaskWorkspace.create(settings.work_root, job.job_id) as workspace:
            with HeartbeatLease(client, job) as lease:
                with _StageTimer(timings, "preflight", job.job_id):
                    lease.checkpoint("preflight")
                    _check_disk(settings, job.download.size_bytes)

                stage = "download"
                with _StageTimer(timings, stage, job.job_id):
                    lease.checkpoint(stage)
                    download_original(
                        job.download,
                        workspace.input_path,
                        job.download.size_bytes,
                        job.download.object_hash,
                    )
                    lease.raise_if_lost()

                stage = "analyze"
                with _StageTimer(timings, stage, job.job_id):
                    lease.checkpoint("inference")
                    local = run_local_pipeline(
                        job,
                        workspace.input_path,
                        workspace.output_path,
                        lease.checkpoint,
                    )
                    lease.raise_if_lost()

                stage = "upload"
                with _StageTimer(timings, stage, job.job_id):
                    lease.checkpoint("upload")
                    uploaded = upload_skeleton(job.upload, workspace.output_path)
                    lease.raise_if_lost()

                stage = "complete"
                with _StageTimer(timings, stage, job.job_id):
                    lease.checkpoint("complete")
                    payload = local.to_completion_payload(
                        job=job,
                        skeleton=_skeleton_artifact(job, local, uploaded),
                        idempotency_key=completion_key,
                    )
                    client.complete(job.job_id, payload)
                    terminal_status = "succeeded"
                    lease.stop()
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as error:
        if terminal_status == "succeeded":
            return
        failure_code, summary = _failure_details(error, stage)
        try:
            client.fail(
                job.job_id,
                lease_token=job.lease_token,
                idempotency_key=failure_key,
                failure_code=failure_code,
                summary=summary,
                stage_timings=timings,
            )
            terminal_status = "failed"
        except Exception:
            _logger.warning(
                "motion_analysis_fail_report_failed",
                extra={
                    "method": "POST",
                    "path": f"/api/internal/motion-analysis/jobs/{job.job_id}/fail/",
                    "job_id": job.job_id,
                    "attempt": settings.network_attempts,
                    "reason_code": "fail_report_error",
                },
            )
    finally:
        metrics = _resource_metrics(settings)
        _logger.info(
            "motion_analysis_workspace_cleanup",
            extra={
                "job_id": job.job_id,
                "stage": "cleanup",
                "outcome": "removed" if workspace is not None and workspace.cleaned else "failed",
            },
        )
        _logger.info(
            "motion_analysis_job_finished",
            extra={
                "job_id": job.job_id,
                "outcome": terminal_status or "failed",
                "reason_code": None,
                "decoded_frame_count": local.decoded_frame_count if local else 0,
                "inferred_frame_count": local.inferred_frame_count if local else 0,
                "output_frame_count": local.encoded_frame_count if local else 0,
                **metrics,
            },
        )


def run_worker(
    *,
    client: MotionCareClient,
    processor: Callable[[ClaimedJob], object],
    sleeper: Callable[[float], None] = time.sleep,
    settings: Settings,
    max_claims: int | None = None,
) -> None:
    """串行领取任务；max_claims 只限制测试中的 claim 调用总数。"""
    if max_claims is not None and (
        isinstance(max_claims, bool) or not isinstance(max_claims, int) or max_claims < 0
    ):
        raise ValueError("max_claims 必须是非负整数或 None")

    configure_safe_logging(secrets=(settings.service_token,))
    install_safe_logging(_logger, secrets=(settings.service_token,))
    claim_count = 0
    while max_claims is None or claim_count < max_claims:
        claim_count += 1
        try:
            job = client.claim()
        except MotionCareUnavailableError:
            _logger.warning(
                "motioncare_claim_unavailable",
                extra={
                    "method": "POST",
                    "path": "/api/internal/motion-analysis/jobs/claim/",
                    "attempt": settings.network_attempts,
                    "reason_code": "claim_retry_exhausted",
                },
            )
            sleeper(settings.poll_interval_seconds)
            continue

        if job is None:
            sleeper(settings.poll_interval_seconds)
            continue

        try:
            processor(job)
        except JobAlreadyFinalized:
            continue
        except Exception:
            _logger.warning(
                "motion_analysis_processor_failed",
                extra={"job_id": job.job_id, "attempt": 1, "reason_code": "processor_error"},
            )
            try:
                client.fail(
                    job.job_id,
                    lease_token=job.lease_token,
                    idempotency_key=f"worker-processor-error-{job.job_id}",
                    failure_code="processor_error",
                    summary="任务处理异常",
                    stage_timings={},
                )
            except Exception:
                _logger.warning(
                    "motion_analysis_fail_report_failed",
                    extra={
                        "method": "POST",
                        "path": f"/api/internal/motion-analysis/jobs/{job.job_id}/fail/",
                        "job_id": job.job_id,
                        "attempt": settings.network_attempts,
                        "reason_code": "fail_report_error",
                    },
                )
