from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from motion_analysis_contract import PROTOCOL_VERSION, WorkerCapability


class ConfigurationError(ValueError):
    """表示 worker 配置不安全或不完整。"""


_WORKER_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}\Z")
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9\-._~+/]+={0,2}\Z")
_FORBIDDEN_ENVIRONMENT_KEYS = frozenset(
    {
        "QINIU_ACCESS_KEY",
        "QINIU_SECRET_KEY",
        "DATABASE_URL",
        "REDIS_URL",
        "DJANGO_SECRET_KEY",
    }
)
_ALLOWED_WORKER_ENVIRONMENT_KEYS = frozenset(
    {
        "PP_MCARE_API_BASE_URL",
        "PP_MCARE_SERVICE_TOKEN",
        "PP_MCARE_WORKER_ID",
        "PP_MCARE_POLL_INTERVAL_SECONDS",
        "PP_MCARE_WORK_ROOT",
        "PP_MCARE_MODEL_CACHE",
        "PP_MCARE_NETWORK_ATTEMPTS",
        "PP_MCARE_CONNECT_TIMEOUT_SECONDS",
        "PP_MCARE_READ_TIMEOUT_SECONDS",
        "PP_MCARE_WRITE_TIMEOUT_SECONDS",
        "PP_MCARE_POOL_TIMEOUT_SECONDS",
        "PP_MCARE_CAPABILITIES",
    }
)
_APPROVED_CAPABILITY = WorkerCapability(
    action_source_key="motion-resistance-shoulder-press",
    algorithm_version="PP-TinyPose_128x96",
    rule_version="shoulder-press-v2",
    parameter_version="shoulder-press-v2-defaults",
)
_TRUSTED_PATH_BASE = Path("/opt/motioncare-analysis")
_DIRECTORY_OPERATION_HOOK: Callable[[Path], None] | None = None


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"缺少必填配置：{name}")
    return value


def _parse_integer(
    environ: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = environ.get(name)
    if raw is None:
        return default
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
        raise ConfigurationError(f"{name} 必须是规范十进制整数")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} 超出允许范围")
    return value


def _parse_https_origin(raw: str) -> str:
    if any(character.isspace() or ord(character) < 32 for character in raw) or "\\" in raw:
        raise ConfigurationError("PP_MCARE_API_BASE_URL 格式无效")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        raise ConfigurationError("PP_MCARE_API_BASE_URL 格式无效") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ConfigurationError("PP_MCARE_API_BASE_URL 必须是无路径的 HTTPS origin")
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return f"https://{host}{f':{port}' if port is not None else ''}"


def _parse_absolute_path(environ: Mapping[str, str], name: str, default: Path) -> Path:
    raw = environ.get(name)
    if raw is not None and not isinstance(raw, str):
        raise ConfigurationError(f"{name} 必须是绝对路径")
    path = default if raw is None else Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise ConfigurationError(f"{name} 必须是无上级跳转的绝对路径")
    return path


def _path_is_within(path: Path, trusted_base: Path) -> bool:
    return (
        path != trusted_base
        and len(path.parts) > len(trusted_base.parts)
        and path.parts[: len(trusted_base.parts)] == trusted_base.parts
    )


def _secure_directory(
    path: Path,
    *,
    trusted_base: Path,
    operation_hook: Callable[[Path], None] | None,
) -> None:
    directory_flag = getattr(os, "O_DIRECTORY", None)
    nofollow_flag = getattr(os, "O_NOFOLLOW", None)
    if directory_flag is None or nofollow_flag is None:
        raise ConfigurationError("当前平台不支持安全目录校验")
    if (
        not isinstance(path, Path)
        or not isinstance(trusted_base, Path)
        or not path.is_absolute()
        or not trusted_base.is_absolute()
        or ".." in path.parts
        or ".." in trusted_base.parts
        or not _path_is_within(path, trusted_base)
    ):
        raise ConfigurationError("worker 目录必须位于受信任根目录内")

    flags = os.O_RDONLY | directory_flag | nofollow_flag
    current_fd: int | None = None
    current_path = Path("/")
    try:
        current_fd = os.open("/", flags)
        for index, component in enumerate(path.parts[1:], start=1):
            child_fd: int | None = None
            created = False
            try:
                child_fd = os.open(component, flags, dir_fd=current_fd)
            except FileNotFoundError:
                os.mkdir(component, mode=0o700, dir_fd=current_fd)
                created = True
                created_path = Path(*path.parts[: index + 1])
                if operation_hook is not None:
                    operation_hook(created_path)
                child_fd = os.open(component, flags, dir_fd=current_fd)
            try:
                child_stat = os.fstat(child_fd)
                entry_stat = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(child_stat.st_mode)
                    or not stat.S_ISDIR(entry_stat.st_mode)
                    or child_stat.st_dev != entry_stat.st_dev
                    or child_stat.st_ino != entry_stat.st_ino
                ):
                    raise ConfigurationError("worker 目录校验失败")
                if created:
                    os.fchmod(child_fd, 0o700)
                os.close(current_fd)
                current_fd = child_fd
                child_fd = None
                current_path /= component
            finally:
                if child_fd is not None:
                    os.close(child_fd)

        os.fchmod(current_fd, 0o700)
        final_stat = os.fstat(current_fd)
        path_stat = os.stat(path, follow_symlinks=False)
        if (
            current_path != path
            or final_stat.st_dev != path_stat.st_dev
            or final_stat.st_ino != path_stat.st_ino
            or not stat.S_ISDIR(path_stat.st_mode)
            or stat.S_IMODE(final_stat.st_mode) != 0o700
        ):
            raise ConfigurationError("worker 目录最终校验失败")
    except ConfigurationError:
        raise
    except OSError:
        raise ConfigurationError("无法安全准备 worker 目录") from None
    finally:
        if current_fd is not None:
            os.close(current_fd)


def _validate_integer_value(
    value: object,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} 超出允许范围")


def _parse_capabilities(environ: Mapping[str, str]) -> tuple[WorkerCapability, ...]:
    raw = environ.get("PP_MCARE_CAPABILITIES")
    if raw is None:
        return (_APPROVED_CAPABILITY,)
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise ConfigurationError("PP_MCARE_CAPABILITIES 必须是有效 JSON") from None
    if not isinstance(decoded, list) or len(decoded) != 1 or not isinstance(decoded[0], dict):
        raise ConfigurationError("PP_MCARE_CAPABILITIES 必须只包含已批准能力")
    expected_fields = set(_APPROVED_CAPABILITY.to_dict())
    if set(decoded[0]) != expected_fields:
        raise ConfigurationError("PP_MCARE_CAPABILITIES 字段无效")
    try:
        capability = WorkerCapability.from_dict(decoded[0])
    except (TypeError, ValueError):
        raise ConfigurationError("PP_MCARE_CAPABILITIES 内容无效") from None
    if capability != _APPROVED_CAPABILITY:
        raise ConfigurationError("PP_MCARE_CAPABILITIES 与已批准能力不一致")
    return (capability,)


@dataclass(frozen=True, repr=False)
class Settings:
    api_base_url: str
    service_token: str = field(repr=False)
    worker_id: str
    poll_interval_seconds: int = 900
    work_root: Path = Path("/opt/motioncare-analysis/tmp/jobs")
    model_cache: Path = Path("/opt/motioncare-analysis/model-cache")
    network_attempts: int = 3
    connect_timeout_seconds: int = 5
    read_timeout_seconds: int = 30
    write_timeout_seconds: int = 30
    pool_timeout_seconds: int = 5
    protocol_version: str = PROTOCOL_VERSION
    capabilities: tuple[WorkerCapability, ...] = (_APPROVED_CAPABILITY,)

    def __post_init__(self) -> None:
        if not isinstance(self.api_base_url, str):
            raise ConfigurationError("PP_MCARE_API_BASE_URL 格式无效")
        object.__setattr__(self, "api_base_url", _parse_https_origin(self.api_base_url))
        self.validate_network_security()
        _validate_integer_value(
            self.poll_interval_seconds,
            "PP_MCARE_POLL_INTERVAL_SECONDS",
            minimum=1,
            maximum=86_400,
        )
        if not isinstance(self.work_root, Path) or not isinstance(self.model_cache, Path):
            raise ConfigurationError("worker 目录必须使用 Path")
        if self.work_root == self.model_cache or self.work_root in self.model_cache.parents:
            raise ConfigurationError("worker 目录不得重叠")
        if self.model_cache in self.work_root.parents:
            raise ConfigurationError("worker 目录不得重叠")
        _secure_directory(
            self.work_root,
            trusted_base=_TRUSTED_PATH_BASE,
            operation_hook=_DIRECTORY_OPERATION_HOOK,
        )
        _secure_directory(
            self.model_cache,
            trusted_base=_TRUSTED_PATH_BASE,
            operation_hook=_DIRECTORY_OPERATION_HOOK,
        )

    def validate_network_security(self) -> None:
        """供 HTTP 边界在构造连接前防御性复核安全字段。"""

        if not isinstance(self.api_base_url, str):
            raise ConfigurationError("PP_MCARE_API_BASE_URL 格式无效")
        _parse_https_origin(self.api_base_url)
        if not isinstance(self.service_token, str) or not _TOKEN_PATTERN.fullmatch(
            self.service_token
        ):
            raise ConfigurationError("PP_MCARE_SERVICE_TOKEN 格式无效")
        if not isinstance(self.worker_id, str) or not _WORKER_ID_PATTERN.fullmatch(self.worker_id):
            raise ConfigurationError("PP_MCARE_WORKER_ID 格式无效")
        for value, name, minimum, maximum in (
            (self.network_attempts, "PP_MCARE_NETWORK_ATTEMPTS", 1, 3),
            (self.connect_timeout_seconds, "PP_MCARE_CONNECT_TIMEOUT_SECONDS", 1, 120),
            (self.read_timeout_seconds, "PP_MCARE_READ_TIMEOUT_SECONDS", 1, 300),
            (self.write_timeout_seconds, "PP_MCARE_WRITE_TIMEOUT_SECONDS", 1, 300),
            (self.pool_timeout_seconds, "PP_MCARE_POOL_TIMEOUT_SECONDS", 1, 120),
        ):
            _validate_integer_value(value, name, minimum=minimum, maximum=maximum)
        if self.protocol_version != PROTOCOL_VERSION:
            raise ConfigurationError("协议版本必须来自共享契约")
        if self.capabilities != (_APPROVED_CAPABILITY,):
            raise ConfigurationError("worker 能力必须精确匹配已批准能力")

    def __repr__(self) -> str:
        return (
            "Settings("
            f"api_base_url={self.api_base_url!r}, service_token=<redacted>, "
            f"worker_id={self.worker_id!r}, poll_interval_seconds={self.poll_interval_seconds!r}, "
            f"work_root={self.work_root!r}, model_cache={self.model_cache!r}, "
            f"network_attempts={self.network_attempts!r}, "
            f"connect_timeout_seconds={self.connect_timeout_seconds!r}, "
            f"read_timeout_seconds={self.read_timeout_seconds!r}, "
            f"write_timeout_seconds={self.write_timeout_seconds!r}, "
            f"pool_timeout_seconds={self.pool_timeout_seconds!r}, "
            f"protocol_version={self.protocol_version!r}, capabilities={self.capabilities!r})"
        )

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> Settings:
        source = os.environ if environ is None else environ
        forbidden = sorted(key for key in _FORBIDDEN_ENVIRONMENT_KEYS if key in source)
        if forbidden:
            raise ConfigurationError(f"worker 环境包含禁用配置：{', '.join(forbidden)}")
        unknown_worker_keys = sorted(
            key
            for key in source
            if key.startswith("PP_MCARE_") and key not in _ALLOWED_WORKER_ENVIRONMENT_KEYS
        )
        if unknown_worker_keys:
            raise ConfigurationError("worker 环境包含未知 PP_MCARE 配置")

        service_token = _required(source, "PP_MCARE_SERVICE_TOKEN")
        if not _TOKEN_PATTERN.fullmatch(service_token):
            raise ConfigurationError("PP_MCARE_SERVICE_TOKEN 格式无效")
        worker_id = _required(source, "PP_MCARE_WORKER_ID")
        if not _WORKER_ID_PATTERN.fullmatch(worker_id):
            raise ConfigurationError("PP_MCARE_WORKER_ID 格式无效")

        work_root = _parse_absolute_path(
            source,
            "PP_MCARE_WORK_ROOT",
            cls.__dataclass_fields__["work_root"].default,
        )
        model_cache = _parse_absolute_path(
            source,
            "PP_MCARE_MODEL_CACHE",
            cls.__dataclass_fields__["model_cache"].default,
        )
        return cls(
            api_base_url=_parse_https_origin(_required(source, "PP_MCARE_API_BASE_URL")),
            service_token=service_token,
            worker_id=worker_id,
            poll_interval_seconds=_parse_integer(
                source,
                "PP_MCARE_POLL_INTERVAL_SECONDS",
                900,
                minimum=1,
                maximum=86_400,
            ),
            work_root=work_root,
            model_cache=model_cache,
            network_attempts=_parse_integer(
                source,
                "PP_MCARE_NETWORK_ATTEMPTS",
                3,
                minimum=1,
                maximum=3,
            ),
            connect_timeout_seconds=_parse_integer(
                source,
                "PP_MCARE_CONNECT_TIMEOUT_SECONDS",
                5,
                minimum=1,
                maximum=120,
            ),
            read_timeout_seconds=_parse_integer(
                source,
                "PP_MCARE_READ_TIMEOUT_SECONDS",
                30,
                minimum=1,
                maximum=300,
            ),
            write_timeout_seconds=_parse_integer(
                source,
                "PP_MCARE_WRITE_TIMEOUT_SECONDS",
                30,
                minimum=1,
                maximum=300,
            ),
            pool_timeout_seconds=_parse_integer(
                source,
                "PP_MCARE_POOL_TIMEOUT_SECONDS",
                5,
                minimum=1,
                maximum=120,
            ),
            capabilities=_parse_capabilities(source),
        )
