from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping


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
_REASON_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
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
    if isinstance(value, str):
        return "<redacted>"
    if isinstance(value, tuple):
        return tuple(_redact_untrusted_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_untrusted_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _redact_untrusted_value(item) for key, item in value.items()}
    return value


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
        return isinstance(value, str) and bool(_REASON_CODE_PATTERN.fullmatch(value))
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
        return True


def install_safe_logging(
    logger: logging.Logger,
    *,
    secrets: Iterable[str] = (),
) -> SafeLogFilter:
    filter_ = SafeLogFilter(secrets=secrets)
    logger.addFilter(filter_)
    return filter_
