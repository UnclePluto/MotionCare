import re
from datetime import timedelta

from django.utils import timezone

from .models import TrainingUploadDiagnostic

RETENTION_DAYS = 15
DIAGNOSTIC_FIELDS = (
    "event_id",
    "occurred_at",
    "received_at",
    "client_session_id",
    "video_id",
    "segment_index",
    "http_status",
    "stage",
    "error_code",
    "message",
    "network_type",
    "platform",
    "sdk_version",
    "app_version",
)
SAFE_SUMMARIES = (
    "timeout",
    "permission denied",
    "auth deny",
    "cancel",
    "network error",
    "network disconnected",
    "file not found",
    "no such file",
    "file too large",
    "not supported",
    "invalid data",
    "storage full",
    "disk full",
    "system error",
)
SAFE_OPERATIONS = (
    "uploadFile",
    "request",
    "compressVideo",
    "readFile",
    "getFileInfo",
    "startRecord",
    "stopRecord",
    "onCameraError",
)


def sanitize_diagnostic_message(value):
    """Retain only recognized diagnostic phrases, never arbitrary native text.

    A denylist alone cannot reliably remove names, opaque tokens or response
    bodies. Reconstructing the short summary makes the persisted vocabulary
    finite while the stable error code and stage preserve the failure context.
    """
    text = str(value).lower()
    reason = next((phrase for phrase in SAFE_SUMMARIES if phrase in text), "operation failed")
    operation = next(
        (
            name
            for name in SAFE_OPERATIONS
            if re.search(rf"\b{re.escape(name.lower())}:fail\b", text)
        ),
        None,
    )
    return f"{operation}:fail {reason}" if operation else reason


def diagnostic_cutoff():
    return timezone.now() - timedelta(days=RETENTION_DAYS)


def current_diagnostics():
    return TrainingUploadDiagnostic.objects.filter(received_at__gt=diagnostic_cutoff())
