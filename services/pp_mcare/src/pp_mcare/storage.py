from __future__ import annotations

import logging
import os
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import qiniu
from motion_analysis_contract import DownloadGrant, UploadGrant


_DOWNLOAD_TRANSPORT: httpx.BaseTransport | None = None
_SLEEP = time.sleep
_ATTEMPTS = 3
_CONTENT_TYPE = "video/mp4"


class StorageError(RuntimeError):
    """Safe storage failure whose message never contains provider details."""


class StoragePermanentError(StorageError):
    pass


class StorageTransientError(StorageError):
    pass


@dataclass(frozen=True, repr=False)
class DownloadedObject:
    path: Path = field(repr=False)
    object_hash: str
    size_bytes: int
    content_type: str

    def __repr__(self) -> str:
        return (
            "DownloadedObject(path=<redacted>, "
            f"object_hash={self.object_hash!r}, size_bytes={self.size_bytes!r}, "
            f"content_type={self.content_type!r})"
        )


@dataclass(frozen=True, repr=False)
class UploadedObject:
    bucket: str = field(repr=False)
    object_key: str = field(repr=False)
    object_hash: str
    size_bytes: int

    def __repr__(self) -> str:
        return (
            "UploadedObject(bucket=<redacted>, object_key=<redacted>, "
            f"object_hash={self.object_hash!r}, size_bytes={self.size_bytes!r})"
        )


def configure_storage_logging(secrets=()) -> None:
    """Quarantine SDK log namespaces; worker emits only its own safe events."""

    del secrets
    roots = ("httpx", "httpcore", "qiniu")
    existing = tuple(logging.root.manager.loggerDict)
    names = {
        *roots,
        *(name for name in existing if name.startswith(tuple(f"{root}." for root in roots))),
    }
    for name in names:
        logger = logging.getLogger(name)
        logger.handlers[:] = [logging.NullHandler()]
        logger.propagate = False


def _safe_https_url(value: str) -> None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise StoragePermanentError("下载授权格式无效") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise StoragePermanentError("下载授权格式无效")


def _qiniu_etag(path: Path) -> str:
    try:
        value = qiniu.etag(str(path))
    except Exception:
        raise StoragePermanentError("对象完整性计算失败") from None
    if not isinstance(value, str) or not value:
        raise StoragePermanentError("对象完整性计算失败")
    return value


def _unlink_owned(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _validate_mp4_prefix(prefix: bytes) -> None:
    if len(prefix) < 12 or prefix[4:8] != b"ftyp":
        raise StoragePermanentError("下载对象不是受支持的视频容器")


def download_original(
    grant: DownloadGrant,
    destination: Path,
    expected_size: int,
    expected_hash: str,
) -> DownloadedObject:
    if not isinstance(grant, DownloadGrant):
        raise TypeError("grant 必须是 DownloadGrant")
    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size <= 0
        or expected_size != grant.size_bytes
        or not isinstance(expected_hash, str)
        or expected_hash != grant.object_hash
    ):
        raise StoragePermanentError("下载对象元数据无效")
    _safe_https_url(grant.url)
    target = Path(destination)
    if target.exists() or not target.parent.is_dir():
        raise StoragePermanentError("下载目标无效")
    configure_storage_logging((grant.url,))
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

    for attempt in range(1, _ATTEMPTS + 1):
        created = False
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(descriptor, "wb") as output:
                with httpx.Client(
                    follow_redirects=False,
                    transport=_DOWNLOAD_TRANSPORT,
                    timeout=timeout,
                ) as http_client:
                    with http_client.stream("GET", grant.url) as response:
                        if 300 <= response.status_code <= 499:
                            raise StoragePermanentError("下载请求被拒绝")
                        if response.status_code >= 500:
                            raise StorageTransientError("下载服务暂不可用")
                        if response.status_code != 200:
                            raise StoragePermanentError("下载响应状态无效")
                        content_type = (
                            response.headers.get("Content-Type", "").split(";", 1)[0].strip()
                        )
                        if content_type != _CONTENT_TYPE or grant.content_type != _CONTENT_TYPE:
                            raise StoragePermanentError("下载对象类型不匹配")
                        size = 0
                        prefix = bytearray()
                        for chunk in response.iter_bytes(1024 * 1024):
                            size += len(chunk)
                            if size > expected_size:
                                raise StoragePermanentError("下载对象超过预期大小")
                            if len(prefix) < 32:
                                prefix.extend(chunk[: 32 - len(prefix)])
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
            if size != expected_size:
                raise StoragePermanentError("下载对象大小不匹配")
            _validate_mp4_prefix(bytes(prefix))
            actual_hash = _qiniu_etag(target)
            if actual_hash != expected_hash:
                raise StoragePermanentError("下载对象完整性不匹配")
            mode = os.stat(target, follow_symlinks=False).st_mode
            if not stat.S_ISREG(mode) or stat.S_IMODE(mode) & 0o077:
                raise StoragePermanentError("下载文件权限无效")
            return DownloadedObject(target, actual_hash, size, _CONTENT_TYPE)
        except StoragePermanentError:
            if created:
                _unlink_owned(target)
            raise
        except (httpx.TimeoutException, httpx.TransportError):
            if created:
                _unlink_owned(target)
            if attempt == _ATTEMPTS:
                raise StorageTransientError("下载重试耗尽") from None
            _SLEEP(float(attempt))
        except OSError:
            if created:
                _unlink_owned(target)
            raise StoragePermanentError("下载文件写入失败") from None
        except StorageTransientError:
            if created:
                _unlink_owned(target)
            if attempt == _ATTEMPTS:
                raise StorageTransientError("下载重试耗尽") from None
            _SLEEP(float(attempt))
    raise StorageTransientError("下载重试耗尽")


def _status_code(info: object) -> int | None:
    if isinstance(info, dict):
        value = info.get("status_code")
    else:
        value = getattr(info, "status_code", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _unique_skeleton_key(key: str) -> bool:
    parts = key.split("/")
    return (
        len(parts) >= 3
        and parts[0] == "motion-analysis"
        and parts[-1] == "skeleton.mp4"
        and all(part not in ("", ".", "..") for part in parts)
    )


def upload_skeleton(grant: UploadGrant, path: Path) -> UploadedObject:
    if not isinstance(grant, UploadGrant):
        raise TypeError("grant 必须是 UploadGrant")
    source = Path(path)
    try:
        metadata = os.stat(source, follow_symlinks=False)
    except OSError:
        raise StoragePermanentError("上传文件无效") from None
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
        raise StoragePermanentError("上传文件无效")
    if not _unique_skeleton_key(grant.object_key):
        raise StoragePermanentError("上传对象键无效")
    local_hash = _qiniu_etag(source)
    configure_storage_logging((grant.token,))
    ambiguous_attempt = False

    for attempt in range(1, _ATTEMPTS + 1):
        try:
            result, info = qiniu.put_file(
                grant.token,
                grant.object_key,
                str(source),
                mime_type=_CONTENT_TYPE,
                check_crc=True,
            )
        except OSError:
            ambiguous_attempt = True
            if attempt == _ATTEMPTS:
                raise StorageTransientError("上传重试耗尽") from None
            _SLEEP(float(attempt))
            continue
        except Exception:
            raise StoragePermanentError("上传客户端失败") from None
        status = _status_code(info)
        if status == 614 and ambiguous_attempt:
            return UploadedObject(grant.bucket, grant.object_key, local_hash, metadata.st_size)
        if status is not None and 500 <= status <= 599:
            if attempt == _ATTEMPTS:
                raise StorageTransientError("上传重试耗尽")
            _SLEEP(float(attempt))
            continue
        if status != 200 or not isinstance(result, dict):
            raise StoragePermanentError("上传请求被拒绝")
        if result.get("key") != grant.object_key:
            raise StoragePermanentError("上传对象键不匹配")
        if result.get("hash") != local_hash:
            raise StoragePermanentError("上传对象完整性不匹配")
        return UploadedObject(grant.bucket, grant.object_key, local_hash, metadata.st_size)
    raise StorageTransientError("上传重试耗尽")
