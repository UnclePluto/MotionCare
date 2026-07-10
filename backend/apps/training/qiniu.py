import base64
import hashlib
import hmac
import json
from urllib.parse import quote, urlencode

from django.conf import settings


def _urlsafe_base64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _sign(data: str) -> str:
    digest = hmac.new(
        settings.QINIU_SECRET_KEY.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return _urlsafe_base64(digest)


def generate_upload_token(*, bucket: str, key: str, expires_at: int) -> str:
    policy = {
        "scope": f"{bucket}:{key}",
        "deadline": expires_at,
        "returnBody": '{"key":"$(key)","hash":"$(etag)","size":$(fsize)}',
    }
    encoded_policy = _urlsafe_base64(
        json.dumps(policy, separators=(",", ":")).encode("utf-8")
    )
    return f"{settings.QINIU_ACCESS_KEY}:{_sign(encoded_policy)}:{encoded_policy}"


def private_download_url(base_url: str, *, expires_at: int) -> str:
    separator = "&" if "?" in base_url else "?"
    unsigned = f"{base_url}{separator}{urlencode({'e': expires_at})}"
    token = f"{settings.QINIU_ACCESS_KEY}:{_sign(unsigned)}"
    return f"{unsigned}&token={quote(token, safe=':')}"
