from __future__ import annotations

import logging
import os
import re
import stat
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Iterator
from urllib.parse import urlsplit

import httpx
import qiniu
from motion_analysis_contract import DownloadGrant, UploadGrant

from .workspace import TaskWorkspace


_DOWNLOAD_TRANSPORT: httpx.BaseTransport | None = None
_SLEEP = time.sleep
_ATTEMPTS = 3
_CONTENT_TYPE = "video/mp4"
_QINIU_LOGGING_LOCK = threading.RLock()
_QINIU_PACKAGE_ROOT = Path(qiniu.__file__).resolve().parent
_SKELETON_KEY = re.compile(
    r"motion-analysis/[1-9][0-9]*/[0-9]{4}/(?:0[1-9]|1[0-2])/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/skeleton\.mp4\Z"
)


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
    """Quarantine third-party logger namespaces without changing host handlers."""

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


class _DropQiniuRootRecords(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            source = Path(record.pathname).resolve()
            return not source.is_relative_to(_QINIU_PACKAGE_ROOT)
        except (OSError, RuntimeError, ValueError):
            return False


@contextmanager
def _qiniu_root_logging_boundary() -> Iterator[None]:
    """Drop qiniu's direct root records without mutating shared LogRecord objects."""

    root = logging.getLogger()
    record_filter = _DropQiniuRootRecords()
    temporary_handler: logging.Handler | None = None
    with _QINIU_LOGGING_LOCK:
        if not root.handlers:
            temporary_handler = logging.NullHandler()
            root.addHandler(temporary_handler)
        root.addFilter(record_filter)
        try:
            yield
        finally:
            root.removeFilter(record_filter)
            if temporary_handler is not None:
                root.removeHandler(temporary_handler)


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


def _fd_path(descriptor: int) -> str:
    if sys.platform.startswith("linux"):
        candidate = f"/proc/self/fd/{descriptor}"
    elif sys.platform == "darwin":
        candidate = f"/dev/fd/{descriptor}"
    else:
        raise StoragePermanentError("当前平台不支持安全文件描述符路径")
    if os.path.exists(candidate):
        return candidate
    raise StoragePermanentError("当前平台不支持安全文件描述符路径")


def _qiniu_etag(path: Path | str) -> str:
    try:
        value = qiniu.etag(str(path))
    except Exception:
        raise StoragePermanentError("对象完整性计算失败") from None
    if not isinstance(value, str) or not value:
        raise StoragePermanentError("对象完整性计算失败")
    return value


def qiniu_etag_fd(descriptor: int) -> str:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        return _qiniu_etag(_fd_path(descriptor))
    except OSError:
        raise StoragePermanentError("对象完整性计算失败") from None


def _validate_mp4_prefix(prefix: bytes) -> None:
    if len(prefix) < 12 or prefix[4:8] != b"ftyp":
        raise StoragePermanentError("下载对象不是受支持的视频容器")


def download_original(
    grant: DownloadGrant,
    destination: TaskWorkspace,
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
    if not isinstance(destination, TaskWorkspace):
        raise TypeError("destination 必须是 TaskWorkspace")
    workspace = destination
    target = workspace.input_path
    configure_storage_logging((grant.url,))
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

    for attempt in range(1, _ATTEMPTS + 1):
        created = False
        descriptor = -1
        try:
            descriptor = workspace.create_file("original.mp4")
            created = True
            with os.fdopen(descriptor, "w+b", closefd=False) as output:
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
            actual_hash = qiniu_etag_fd(descriptor)
            verified = os.fstat(descriptor)
            if actual_hash != expected_hash:
                raise StoragePermanentError("下载对象完整性不匹配")
            if not stat.S_ISREG(verified.st_mode) or stat.S_IMODE(verified.st_mode) & 0o077:
                raise StoragePermanentError("下载文件权限无效")
            if not workspace.file_matches("original.mp4", descriptor):
                raise StoragePermanentError("下载文件在校验期间发生变化")
            os.close(descriptor)
            descriptor = -1
            return DownloadedObject(target, actual_hash, size, _CONTENT_TYPE)
        except StoragePermanentError:
            if descriptor >= 0:
                os.close(descriptor)
            if created:
                workspace.unlink_file("original.mp4")
            raise
        except (httpx.TimeoutException, httpx.TransportError):
            if descriptor >= 0:
                os.close(descriptor)
            if created:
                workspace.unlink_file("original.mp4")
            if attempt == _ATTEMPTS:
                raise StorageTransientError("下载重试耗尽") from None
            _SLEEP(float(attempt))
        except OSError:
            if descriptor >= 0:
                os.close(descriptor)
            if created:
                workspace.unlink_file("original.mp4")
            raise StoragePermanentError("下载文件写入失败") from None
        except StorageTransientError:
            if descriptor >= 0:
                os.close(descriptor)
            if created:
                workspace.unlink_file("original.mp4")
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


def _ambiguous_response(info: object, status: int | None) -> bool:
    if status is not None and status < 0:
        return True
    if getattr(info, "exception", None) is not None:
        return True
    connect_failed = getattr(info, "connect_failed", None)
    if callable(connect_failed):
        try:
            return bool(connect_failed())
        except Exception:
            return False
    return False


def _unique_skeleton_key(key: str) -> bool:
    return isinstance(key, str) and bool(_SKELETON_KEY.fullmatch(key))


def upload_skeleton(grant: UploadGrant, path: TaskWorkspace) -> UploadedObject:
    if not isinstance(grant, UploadGrant):
        raise TypeError("grant 必须是 UploadGrant")
    if not isinstance(path, TaskWorkspace):
        raise TypeError("path 必须是 TaskWorkspace")
    workspace = path
    try:
        descriptor = workspace.open_file("skeleton.mp4")
        metadata = os.fstat(descriptor)
    except OSError:
        raise StoragePermanentError("上传文件无效") from None
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
        os.close(descriptor)
        raise StoragePermanentError("上传文件无效")
    if not _unique_skeleton_key(grant.object_key):
        os.close(descriptor)
        raise StoragePermanentError("上传对象键无效")
    try:
        local_hash = qiniu_etag_fd(descriptor)
        descriptor_path = _fd_path(descriptor)
        configure_storage_logging((grant.token,))
        qiniu.config.set_default(connection_retries=1)
        ambiguous_attempt = False

        for attempt in range(1, _ATTEMPTS + 1):
            try:
                with _qiniu_root_logging_boundary():
                    result, info = qiniu.put_file(
                        grant.token,
                        grant.object_key,
                        descriptor_path,
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
                after = os.fstat(descriptor)
                if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_size,
                    metadata.st_mtime_ns,
                ):
                    raise StoragePermanentError("上传文件在传输期间发生变化")
                return UploadedObject(grant.bucket, grant.object_key, local_hash, metadata.st_size)
            ambiguous_response = _ambiguous_response(info, status)
            if ambiguous_response or (status is not None and 500 <= status <= 599):
                ambiguous_attempt = ambiguous_attempt or ambiguous_response
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
            after = os.fstat(descriptor)
            if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_mtime_ns,
            ):
                raise StoragePermanentError("上传文件在传输期间发生变化")
            return UploadedObject(grant.bucket, grant.object_key, local_hash, metadata.st_size)
        raise StorageTransientError("上传重试耗尽")
    finally:
        os.close(descriptor)
