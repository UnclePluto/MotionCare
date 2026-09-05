from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable
from typing import TextIO


_URL_PATTERN = re.compile(r"https?://[^\s,;)}\]>]+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"Bearer\s+[^\s,;)}\]>]+", re.IGNORECASE)
_WINDOWS_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:\\|\\\\)[^\s,;)}\]>]+")
_UNIX_PATH_PATTERN = re.compile(r"/(?:[^/\s]+/)*[^/\s,;)}\]>]+")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?:access[_-]?key|secret[_-]?key|token|credential|password)\s*[=:]\s*[^\s,;]+"
)
_SAFE_RELATIVE_PATH_PATTERN = re.compile(
    r"/api/internal/motion-analysis/jobs/(?:claim/|[1-9][0-9]*/(?:heartbeat|complete|fail)/)\Z"
)
_SAFE_REASON_CODES = frozenset(
    {
        "claim_retry_exhausted",
        "fail_report_error",
        "processor_error",
        "response",
        "server_error",
        "transport_error",
    }
)
_SAFE_MESSAGES = frozenset(
    {
        "motioncare_request_retry",
        "motioncare_request_complete",
        "motioncare_claim_unavailable",
        "motion_analysis_processor_failed",
        "motion_analysis_fail_report_failed",
    }
)


def _redact_text(value: str, secrets: tuple[str, ...]) -> str:
    rendered = value
    for secret in secrets:
        if secret:
            rendered = rendered.replace(secret, "<redacted>")
    rendered = _BEARER_PATTERN.sub("Bearer <redacted>", rendered)
    rendered = _URL_PATTERN.sub("<redacted-url>", rendered)
    rendered = _WINDOWS_PATH_PATTERN.sub("<redacted-path>", rendered)
    rendered = _UNIX_PATH_PATTERN.sub("<redacted-path>", rendered)
    return _SECRET_ASSIGNMENT_PATTERN.sub("<redacted-secret>", rendered)


def _redact_untrusted_value(value: object) -> object:
    return "<redacted>"


def _safe_structured_extra(key: str, value: object) -> bool:
    if key == "method":
        return value in {None, "POST"}
    if key == "path":
        return value is None or (
            isinstance(value, str) and bool(_SAFE_RELATIVE_PATH_PATTERN.fullmatch(value))
        )
    if key == "status":
        return value is None or (
            isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599
        )
    if key == "job_id":
        return value is None or (
            isinstance(value, int) and not isinstance(value, bool) and value > 0
        )
    if key == "attempt":
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    if key == "reason_code":
        return value in _SAFE_REASON_CODES
    return False


class SafeLogFilter(logging.Filter):
    """在日志进入任何 handler 前统一清除凭证、URL、路径和异常正文。"""

    def __init__(self, *, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.msg, str) or record.msg not in _SAFE_MESSAGES:
            record.msg = "<redacted>"
        else:
            record.msg = _redact_text(record.msg, self._secrets)
        record.args = ()
        standard = logging.makeLogRecord({}).__dict__
        for key, value in tuple(record.__dict__.items()):
            if key not in standard and key not in {"message", "asctime"}:
                if _safe_structured_extra(key, value):
                    continue
                record.__dict__[key] = _redact_untrusted_value(value)
        if record.exc_info is not None:
            record.exc_info = None
            record.exc_text = None
            record.msg = f"{record.msg} exception=<redacted>"
        if record.stack_info:
            record.stack_info = "<redacted>"
        for field_name in (
            "method",
            "path",
            "status",
            "job_id",
            "attempt",
            "reason_code",
        ):
            record.__dict__.setdefault(field_name, None)
        return True


def install_safe_logging(
    logger: logging.Logger,
    *,
    secrets: Iterable[str] = (),
) -> SafeLogFilter:
    filter_ = SafeLogFilter(secrets=secrets)
    logger.addFilter(filter_)
    return filter_


_SAFE_HANDLER_MARKER = "_pp_mcare_safe_handler"
_SAFE_FORMAT = (
    "event=%(message)s method=%(method)s path=%(path)s status=%(status)s "
    "job_id=%(job_id)s attempt=%(attempt)s reason_code=%(reason_code)s"
)


def configure_safe_logging(
    *,
    secrets: Iterable[str] = (),
    stream: TextIO | None = None,
) -> logging.Handler:
    """配置不可向 root 传播的 pp_mcare 专用安全日志边界。"""

    namespace = logging.getLogger("pp_mcare")
    namespace.setLevel(logging.DEBUG)
    namespace.propagate = False
    existing = next(
        (
            handler
            for handler in namespace.handlers
            if getattr(handler, _SAFE_HANDLER_MARKER, False)
        ),
        None,
    )
    if existing is None or stream is not None:
        for handler in tuple(namespace.handlers):
            namespace.removeHandler(handler)
            handler.close()
        existing = logging.StreamHandler(stream if stream is not None else sys.stderr)
        setattr(existing, _SAFE_HANDLER_MARKER, True)
        existing.setFormatter(logging.Formatter(_SAFE_FORMAT))
        namespace.addHandler(existing)

    for filter_ in tuple(existing.filters):
        if isinstance(filter_, SafeLogFilter):
            existing.removeFilter(filter_)
    existing.addFilter(SafeLogFilter(secrets=secrets))
    return existing
