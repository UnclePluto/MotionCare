from __future__ import annotations

import logging
import time
from collections.abc import Callable

from motion_analysis_contract import ClaimedJob

from .api_client import MotionCareClient, MotionCareUnavailableError
from .config import Settings
from .safe_logging import install_safe_logging


_logger = logging.getLogger(__name__)


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
                    "status": None,
                    "job_id": None,
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
        except Exception:
            _logger.warning(
                "motion_analysis_processor_failed",
                extra={
                    "method": None,
                    "path": None,
                    "status": None,
                    "job_id": job.job_id,
                    "attempt": 1,
                    "reason_code": "processor_error",
                },
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
                        "path": (f"/api/internal/motion-analysis/jobs/{job.job_id}/fail/"),
                        "status": None,
                        "job_id": job.job_id,
                        "attempt": settings.network_attempts,
                        "reason_code": "fail_report_error",
                    },
                )
