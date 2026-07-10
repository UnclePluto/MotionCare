import base64
import hashlib
import hmac
import json
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from qiniu import Auth, BucketManager


ALLOWED_VIDEO_CONTENT_TYPES = frozenset({"video/mp4", "video/quicktime"})


def _urlsafe_base64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8")


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


def stat_object_metadata(*, bucket: str, key: str) -> dict:
    auth = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    try:
        metadata, response = BucketManager(auth).stat(bucket, key)
    except Exception as exc:
        raise ValidationError("七牛训练视频对象无法读取") from exc
    if getattr(response, "status_code", None) != 200 or not isinstance(metadata, dict):
        raise ValidationError("七牛训练视频对象不存在或无法读取")
    return metadata


def validate_object_metadata(
    metadata: dict,
    *,
    expected_hash: str,
    expected_size_bytes: int,
    expected_content_type: str,
) -> None:
    if metadata.get("hash") != expected_hash:
        raise ValidationError("训练视频对象 Hash 不匹配")
    if metadata.get("fsize") != expected_size_bytes:
        raise ValidationError("训练视频对象大小不匹配")

    remote_content_type = str(metadata.get("mimeType", "")).split(";", 1)[0].strip().lower()
    expected_content_type = expected_content_type.strip().lower()
    if (
        remote_content_type not in ALLOWED_VIDEO_CONTENT_TYPES
        or expected_content_type not in ALLOWED_VIDEO_CONTENT_TYPES
        or remote_content_type != expected_content_type
    ):
        raise ValidationError("训练视频对象类型不匹配")


def private_download_url(base_url: str, *, expires_at: int) -> str:
    separator = "&" if "?" in base_url else "?"
    unsigned = f"{base_url}{separator}{urlencode({'e': expires_at})}"
    token = f"{settings.QINIU_ACCESS_KEY}:{_sign(unsigned)}"
    return f"{unsigned}&token={quote(token, safe=':')}"
