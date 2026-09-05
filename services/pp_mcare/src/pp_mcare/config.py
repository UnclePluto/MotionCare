from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping
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
    path = default if raw is None else Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise ConfigurationError(f"{name} 必须是无上级跳转的绝对路径")
    return path


def _prepare_private_directory(path: Path) -> None:
    try:
        if path.is_symlink():
            raise ConfigurationError("PP_MCARE_WORK_ROOT 不得是符号链接")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not path.is_dir():
            raise ConfigurationError("PP_MCARE_WORK_ROOT 必须是目录")
        path.chmod(0o700)
        if stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise ConfigurationError("PP_MCARE_WORK_ROOT 权限必须为 0700")
    except OSError:
        raise ConfigurationError("无法准备 PP_MCARE_WORK_ROOT") from None


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
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
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
        _prepare_private_directory(work_root)
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
