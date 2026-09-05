import hashlib
import re
from hmac import compare_digest

from django.conf import settings
from rest_framework.permissions import BasePermission


_BEARER_PATTERN = re.compile(r"Bearer ([A-Za-z0-9\-._~+/]+={0,2})\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_DISABLED_DIGEST = "0" * 64


class IsPpMcareWorker(BasePermission):
    def has_permission(self, request, view):
        if not request.is_secure():
            return False

        authorization = request.headers.get("Authorization", "")
        match = _BEARER_PATTERN.fullmatch(authorization)
        supplied_token = match.group(1) if match else ""
        supplied_digest = hashlib.sha256(supplied_token.encode()).hexdigest()

        expected_digest = settings.PP_MCARE_SERVICE_TOKEN_SHA256
        configured = isinstance(expected_digest, str) and bool(
            _SHA256_PATTERN.fullmatch(expected_digest)
        )
        comparable_digest = expected_digest if configured else _DISABLED_DIGEST
        digest_matches = compare_digest(supplied_digest, comparable_digest)
        return bool(match and configured and digest_matches)
