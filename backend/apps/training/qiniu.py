import base64
import hashlib
import hmac
from pathlib import Path
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
import qiniu
from qiniu import Auth, BucketManager, put_file


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


def stat_object_metadata_or_none(*, bucket: str, key: str) -> dict | None:
    auth = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    try:
        metadata, response = BucketManager(auth).stat(bucket, key)
    except Exception as exc:
        raise ValidationError("七牛训练视频对象无法读取") from exc
    status_code = getattr(response, "status_code", None)
    if status_code == 200 and isinstance(metadata, dict):
        return metadata
    if status_code == 612:
        return None
    raise ValidationError("七牛训练视频对象无法读取")


def stat_object_metadata(*, bucket: str, key: str) -> dict:
    metadata = stat_object_metadata_or_none(bucket=bucket, key=key)
    if metadata is None:
        raise ValidationError("七牛训练视频对象不存在")
    return metadata


def delete_object_if_exists(*, bucket: str, key: str) -> None:
    auth = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    try:
        _, response = BucketManager(auth).delete(bucket, key)
    except Exception as exc:
        raise ValidationError("七牛训练视频对象删除失败") from exc
    if getattr(response, "status_code", None) not in {200, 612}:
        raise ValidationError("七牛训练视频对象删除失败")


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


def upload_local_video(*, path: Path, bucket: str, key: str) -> dict:
    path = Path(path).resolve()
    if not path.is_file():
        raise ValidationError("训练视频最终文件不存在或不是普通文件")

    local_size = path.stat().st_size
    try:
        local_etag = qiniu.etag(str(path))
    except OSError as exc:
        raise ValidationError("训练视频最终文件无法计算 Hash") from exc

    existing = stat_object_metadata_or_none(bucket=bucket, key=key)
    if existing is not None:
        if existing.get("fsize") != local_size or existing.get("hash") != local_etag:
            raise ValidationError("七牛目标对象与本地视频冲突")
        validate_object_metadata(
            existing,
            expected_hash=local_etag,
            expected_size_bytes=local_size,
            expected_content_type="video/mp4",
        )
        return existing

    try:
        auth = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
        token = auth.upload_token(bucket, key, 3600)
        result, response = put_file(
            token, key, str(path), check_crc=True, mime_type="video/mp4"
        )
    except Exception as exc:
        raise ValidationError("训练视频上传七牛失败") from exc
    if getattr(response, "status_code", None) != 200 or not isinstance(result, dict):
        raise ValidationError("训练视频上传七牛失败")
    if result.get("key") != key or result.get("hash") != local_etag:
        raise ValidationError("七牛训练视频上传结果不匹配")

    metadata = stat_object_metadata(bucket=bucket, key=key)
    validate_object_metadata(
        metadata,
        expected_hash=local_etag,
        expected_size_bytes=local_size,
        expected_content_type="video/mp4",
    )
    return metadata


def private_download_url(base_url: str, *, expires_at: int) -> str:
    separator = "&" if "?" in base_url else "?"
    unsigned = f"{base_url}{separator}{urlencode({'e': expires_at})}"
    token = f"{settings.QINIU_ACCESS_KEY}:{_sign(unsigned)}"
    return f"{unsigned}&token={quote(token, safe=':')}"
