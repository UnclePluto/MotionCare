from __future__ import annotations

import json
import logging
import math
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx
from motion_analysis_contract import (
    PROTOCOL_VERSION,
    ClaimedJob,
    CompletionPayload,
    ContractValidationError,
    MotionCounts,
)

from .config import ConfigurationError, Settings
from .retry import run_with_retry
from .safe_logging import configure_safe_logging, install_safe_logging


_CLAIM_PATH = "/api/internal/motion-analysis/jobs/claim/"
_JOB_PATH_PATTERN = "/api/internal/motion-analysis/jobs/{job_id}/{action}/"
_CLAIM_FIELDS = frozenset(
    {
        "protocol_version",
        "job_id",
        "action_source_key",
        "algorithm_version",
        "rule_version",
        "parameter_version",
        "subject_tracker_version",
        "lease_token",
        "lease_expires_at",
        "heartbeat_interval_seconds",
        "download",
        "upload",
    }
)
_DOWNLOAD_FIELDS = frozenset(
    {"url", "bucket", "object_key", "object_hash", "expires_at", "size_bytes", "content_type"}
)
_UPLOAD_FIELDS = frozenset({"bucket", "object_key", "token", "expires_at"})
_HEARTBEAT_FIELDS = frozenset(
    {
        "protocol_version",
        "job_id",
        "lease_expires_at",
        "heartbeat_interval_seconds",
        "current_stage",
    }
)
_TERMINAL_FIELDS = frozenset({"protocol_version", "job_id", "status", "finished_at"})
_SUCCESS_COUNT_FIELDS = frozenset({"total_count", "standard_count", "nonstandard_count"})
_LEASE_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,128}\Z")
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}\Z")
_STAGE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
_FAILURE_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")


class MotionCareClientError(RuntimeError):
    pass


class MotionCareUnavailableError(MotionCareClientError):
    pass


class MotionCareValidationError(MotionCareClientError):
    pass


class MotionCareConflictError(MotionCareClientError):
    pass


class MotionCareProtocolError(MotionCareClientError):
    pass


class _ClaimImmediately:
    __slots__ = ()


CLAIM_IMMEDIATELY = _ClaimImmediately()


class _TransientRequestError(RuntimeError):
    def __init__(self, *, reason_code: str, status: int | None = None) -> None:
        self.reason_code = reason_code
        self.status = status
        super().__init__(reason_code)


@dataclass(frozen=True)
class HeartbeatResult:
    job_id: int
    lease_expires_at: str
    heartbeat_interval_seconds: int
    current_stage: str


@dataclass(frozen=True)
class TerminalResult:
    job_id: int
    status: str
    finished_at: str
    counts: MotionCounts | None = None


def _require_exact_mapping(
    value: object,
    fields: frozenset[str],
    *,
    response_name: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MotionCareProtocolError(f"{response_name}响应格式无效")
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MotionCareProtocolError(f"响应字段 {field_name} 无效")
    return value


def _require_nonempty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise MotionCareProtocolError(f"响应字段 {field_name} 无效")
    return value


class MotionCareClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        try:
            settings.validate_network_security()
        except (AttributeError, ConfigurationError):
            raise MotionCareValidationError("HTTP 客户端配置无效") from None
        self._settings = settings
        self._sleeper = sleeper
        self._logger = logger or logging.getLogger(__name__)
        configure_safe_logging(secrets=(settings.service_token,))
        self._safe_log_filter = install_safe_logging(
            self._logger,
            secrets=(settings.service_token,),
        )
        timeout = httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=settings.read_timeout_seconds,
            write=settings.write_timeout_seconds,
            pool=settings.pool_timeout_seconds,
        )
        self._client = httpx.Client(
            base_url=settings.api_base_url,
            headers={"Authorization": f"Bearer {settings.service_token}"},
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
        )

    def __repr__(self) -> str:
        return (
            "MotionCareClient("
            f"base_origin={self._settings.api_base_url!r}, worker_id={self._settings.worker_id!r}, "
            "authorization=<redacted>)"
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MotionCareClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _post(
        self,
        path: str,
        payload: Mapping[str, object],
        *,
        job_id: int | None,
    ) -> httpx.Response:
        try:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode()
        except (TypeError, ValueError):
            raise MotionCareValidationError("请求数据格式无效") from None

        def request_once() -> httpx.Response:
            try:
                response = self._client.post(
                    path,
                    content=body,
                    headers={"Content-Type": "application/json"},
                )
            except (httpx.TimeoutException, httpx.TransportError) as error:
                reason_code = (
                    "request_timeout"
                    if isinstance(error, httpx.TimeoutException)
                    else "transport_error"
                )
                raise _TransientRequestError(reason_code=reason_code) from None
            if 500 <= response.status_code <= 599:
                raise _TransientRequestError(
                    reason_code="server_error",
                    status=response.status_code,
                )
            return response

        def log_retry(attempt: int, error: Exception) -> None:
            transient = error if isinstance(error, _TransientRequestError) else None
            self._logger.warning(
                "motioncare_request_retry",
                extra={
                    "method": "POST",
                    "path": path,
                    "status": transient.status if transient else None,
                    "job_id": job_id,
                    "attempt": attempt,
                    "reason_code": transient.reason_code if transient else "transport_error",
                },
            )

        try:
            response = run_with_retry(
                request_once,
                attempts=self._settings.network_attempts,
                sleeper=self._sleeper,
                retryable=(_TransientRequestError,),
                on_retry=log_retry,
            )
        except _TransientRequestError as error:
            raise MotionCareUnavailableError(
                f"POST {path} 暂不可用（reason_code={error.reason_code}）"
            ) from None

        status = response.status_code
        self._logger.debug(
            "motioncare_request_complete",
            extra={
                "method": "POST",
                "path": path,
                "status": status,
                "job_id": job_id,
                "attempt": 1,
                "reason_code": "response",
            },
        )
        if status == 409:
            raise MotionCareConflictError(f"POST {path} 状态冲突（status=409）")
        if 400 <= status <= 499:
            raise MotionCareValidationError(f"POST {path} 请求被拒绝（status={status}）")
        if 300 <= status <= 399:
            raise MotionCareProtocolError(f"POST {path} 拒绝重定向（status={status}）")
        return response

    @staticmethod
    def _decode_json(response: httpx.Response, response_name: str) -> object:
        try:
            return response.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            raise MotionCareProtocolError(f"{response_name}响应不是有效 JSON") from None

    def claim(self) -> ClaimedJob | _ClaimImmediately | None:
        response = self._post(
            _CLAIM_PATH,
            {
                "worker_id": self._settings.worker_id,
                "protocol_version": PROTOCOL_VERSION,
                "capabilities": [
                    capability.to_dict() for capability in self._settings.capabilities
                ],
            },
            job_id=None,
        )
        if response.status_code == 204:
            return None
        if response.status_code == 202:
            payload = self._decode_json(response, "claim")
            if payload == {"protocol_version": PROTOCOL_VERSION, "status": "scan_incomplete"}:
                return CLAIM_IMMEDIATELY
            raise MotionCareProtocolError("claim 响应契约无效")
        if response.status_code != 200:
            raise MotionCareProtocolError("claim 响应状态无效")
        payload = _require_exact_mapping(
            self._decode_json(response, "claim"),
            _CLAIM_FIELDS,
            response_name="claim",
        )
        _require_exact_mapping(payload.get("download"), _DOWNLOAD_FIELDS, response_name="claim")
        _require_exact_mapping(payload.get("upload"), _UPLOAD_FIELDS, response_name="claim")
        try:
            return ClaimedJob.from_dict(payload)
        except (ContractValidationError, TypeError, ValueError):
            raise MotionCareProtocolError("claim 响应契约无效") from None

    def heartbeat(self, job_id: int, lease_token: str, stage: str) -> HeartbeatResult:
        self._validate_job_id(job_id)
        self._validate_lease_token(lease_token)
        if not isinstance(stage, str) or not _STAGE_PATTERN.fullmatch(stage):
            raise MotionCareValidationError("心跳阶段格式无效")
        response = self._post(
            _JOB_PATH_PATTERN.format(job_id=job_id, action="heartbeat"),
            {
                "protocol_version": PROTOCOL_VERSION,
                "lease_token": lease_token,
                "stage": stage,
            },
            job_id=job_id,
        )
        if response.status_code != 200:
            raise MotionCareProtocolError("heartbeat 响应状态无效")
        payload = _require_exact_mapping(
            self._decode_json(response, "heartbeat"),
            _HEARTBEAT_FIELDS,
            response_name="heartbeat",
        )
        if payload.get("protocol_version") != PROTOCOL_VERSION or payload.get("job_id") != job_id:
            raise MotionCareProtocolError("heartbeat 响应身份无效")
        current_stage = _require_nonempty_string(payload.get("current_stage"), "current_stage")
        if not _STAGE_PATTERN.fullmatch(current_stage):
            raise MotionCareProtocolError("heartbeat 响应阶段无效")
        return HeartbeatResult(
            job_id=job_id,
            lease_expires_at=_require_nonempty_string(
                payload.get("lease_expires_at"),
                "lease_expires_at",
            ),
            heartbeat_interval_seconds=_require_positive_int(
                payload.get("heartbeat_interval_seconds"),
                "heartbeat_interval_seconds",
            ),
            current_stage=current_stage,
        )

    def complete(self, job_id: int, payload: CompletionPayload) -> TerminalResult:
        self._validate_job_id(job_id)
        if not isinstance(payload, CompletionPayload):
            raise MotionCareValidationError("complete 必须使用 CompletionPayload")
        response = self._post(
            _JOB_PATH_PATTERN.format(job_id=job_id, action="complete"),
            payload.to_dict(),
            job_id=job_id,
        )
        return self._parse_terminal(response, job_id=job_id, expected_status="succeeded")

    def fail(
        self,
        job_id: int,
        *,
        lease_token: str,
        idempotency_key: str,
        failure_code: str,
        summary: str,
        stage_timings: Mapping[str, int | float],
    ) -> TerminalResult:
        self._validate_job_id(job_id)
        self._validate_lease_token(lease_token)
        if not isinstance(idempotency_key, str) or not _IDENTIFIER_PATTERN.fullmatch(
            idempotency_key
        ):
            raise MotionCareValidationError("失败幂等键格式无效")
        if not isinstance(failure_code, str) or not _FAILURE_CODE_PATTERN.fullmatch(failure_code):
            raise MotionCareValidationError("失败代码格式无效")
        if not isinstance(summary, str) or not summary or len(summary) > 2000:
            raise MotionCareValidationError("失败摘要格式无效")
        if not isinstance(stage_timings, Mapping) or len(stage_timings) > 32:
            raise MotionCareValidationError("阶段耗时格式无效")
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
                raise MotionCareValidationError("阶段耗时格式无效")
            normalized_timings[stage] = value
        response = self._post(
            _JOB_PATH_PATTERN.format(job_id=job_id, action="fail"),
            {
                "protocol_version": PROTOCOL_VERSION,
                "lease_token": lease_token,
                "idempotency_key": idempotency_key,
                "failure_code": failure_code,
                "summary": summary,
                "stage_timings": normalized_timings,
            },
            job_id=job_id,
        )
        return self._parse_terminal(response, job_id=job_id, expected_status="failed")

    @staticmethod
    def _validate_job_id(job_id: int) -> None:
        if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
            raise MotionCareValidationError("job_id 格式无效")

    @staticmethod
    def _validate_lease_token(lease_token: str) -> None:
        if not isinstance(lease_token, str) or not _LEASE_TOKEN_PATTERN.fullmatch(lease_token):
            raise MotionCareValidationError("租约凭证格式无效")

    def _parse_terminal(
        self,
        response: httpx.Response,
        *,
        job_id: int,
        expected_status: str,
    ) -> TerminalResult:
        if response.status_code != 200:
            raise MotionCareProtocolError("终态响应状态无效")
        decoded = self._decode_json(response, "终态")
        expected_fields = (
            _TERMINAL_FIELDS | _SUCCESS_COUNT_FIELDS
            if expected_status == "succeeded"
            else _TERMINAL_FIELDS
        )
        payload = _require_exact_mapping(
            decoded,
            expected_fields,
            response_name="终态",
        )
        if (
            payload.get("protocol_version") != PROTOCOL_VERSION
            or payload.get("job_id") != job_id
            or payload.get("status") != expected_status
        ):
            raise MotionCareProtocolError("终态响应身份无效")
        counts = None
        if expected_status == "succeeded":
            try:
                counts = MotionCounts.from_dict(payload)
            except (ContractValidationError, TypeError, ValueError):
                raise MotionCareProtocolError("终态计数响应无效") from None
        return TerminalResult(
            job_id=job_id,
            status=expected_status,
            finished_at=_require_nonempty_string(payload.get("finished_at"), "finished_at"),
            counts=counts,
        )
