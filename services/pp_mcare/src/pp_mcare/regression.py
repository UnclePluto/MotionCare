from __future__ import annotations

import ctypes
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import psutil
from motion_analysis_contract import ClaimedJob, MotionCounts, PROTOCOL_VERSION

from .actions.shoulder_press_v2 import ShoulderPressV2Plugin
from .media import SourceVideoMetadata, probe_source_video
from .pipeline import run_local_pipeline
from .pose_inference import PP_TINYPOSE_MODEL_NAME
from .subject_tracker import SUBJECT_TRACKER_VERSION


EXPECTED_VIDEO_SHA256 = "f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd"
EXPECTED_DECODED_FRAME_COUNT = 8_929
EXPECTED_MANUAL_TOTAL_COUNT = 90
REPORT_FORMAT_VERSION = "4.0"
MAX_PROCESS_RSS_BYTES = int(1.5 * 1024**3)
_CLOCK = time.monotonic
_ACTION_PLUGIN = ShoulderPressV2Plugin()
_IMPLEMENTATION_FILES = (
    "__init__.py",
    "__main__.py",
    "cli.py",
    "media.py",
    "paddle_visualize_pose.py",
    "pipeline.py",
    "pose_inference.py",
    "registry.py",
    "regression.py",
    "subject_tracker.py",
    "actions/__init__.py",
    "actions/base.py",
    "actions/shoulder_press_v2.py",
)
_RELEASE_MANIFEST_PATH = Path("/opt/motioncare-analysis/current/release-manifest.json")
_AT_FDCWD = -100
_AT_SYMLINK_FOLLOW = 0x400


class RegressionFailure(RuntimeError):
    """真实样本回归未满足固定验收契约。"""


def _implementation_sha256(
    package_root: Path,
    *,
    relative_paths: tuple[str, ...] = _IMPLEMENTATION_FILES,
) -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(set(relative_paths)):
        normalized = Path(relative_path)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise RegressionFailure("实现身份文件清单无效")
        try:
            content = (package_root / normalized).read_bytes()
        except OSError as exc:
            raise RegressionFailure("实现身份无法读取") from exc
        encoded_name = normalized.as_posix().encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _digest_named_content(entries: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    if not entries:
        raise RegressionFailure("分发内容身份为空")
    for logical_name, content in sorted(entries):
        encoded_name = logical_name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _source_distribution_entries(package_root: Path, project_root: Path) -> list[tuple[str, bytes]]:
    entries: list[tuple[str, bytes]] = []
    try:
        for path in package_root.rglob("*"):
            relative = path.relative_to(package_root)
            if (
                not path.is_file()
                or path.is_symlink()
                or "__pycache__" in relative.parts
                or path.suffix in {".pyc", ".pyo"}
            ):
                continue
            entries.append((f"pp_mcare/{relative.as_posix()}", path.read_bytes()))
        for filename in ("pyproject.toml", "LICENSE.paddledetection", "NOTICE"):
            path = project_root / filename
            if not path.is_file() or path.is_symlink():
                raise RegressionFailure("分发内容身份无法读取")
            entries.append((f"project/{filename}", path.read_bytes()))
    except OSError as exc:
        raise RegressionFailure("分发内容身份无法读取") from exc
    return entries


def _installed_distribution_entries() -> list[tuple[str, bytes]]:
    try:
        distribution = importlib.metadata.distribution("pp-mcare")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RegressionFailure("分发内容身份无法读取") from exc
    entries: list[tuple[str, bytes]] = []
    excluded_metadata = {"RECORD", "INSTALLER", "REQUESTED", "direct_url.json"}
    for item in distribution.files or ():
        parts = Path(str(item)).parts
        logical_name: str | None = None
        if "pp_mcare" in parts:
            package_index = parts.index("pp_mcare")
            package_parts = parts[package_index:]
            if "__pycache__" not in package_parts and Path(*package_parts).suffix not in {
                ".pyc",
                ".pyo",
            }:
                logical_name = Path(*package_parts).as_posix()
        else:
            dist_info_index = next(
                (index for index, part in enumerate(parts) if part.endswith(".dist-info")),
                None,
            )
            if dist_info_index is not None:
                metadata_parts = parts[dist_info_index + 1 :]
                if metadata_parts and metadata_parts[0] not in excluded_metadata:
                    logical_name = Path("dist-info", *metadata_parts).as_posix()
        if logical_name is None:
            continue
        path = Path(distribution.locate_file(item))
        try:
            if not path.is_file() or path.is_symlink():
                raise RegressionFailure("分发内容身份无法读取")
            entries.append((logical_name, path.read_bytes()))
        except OSError as exc:
            raise RegressionFailure("分发内容身份无法读取") from exc
    return entries


def _source_project_root(package_root: Path) -> Path | None:
    if package_root.name != "pp_mcare" or package_root.parent.name != "src":
        return None
    project_root = package_root.parent.parent
    expected_package_root = project_root / "src" / "pp_mcare"
    try:
        if expected_package_root.resolve(strict=True) != package_root.resolve(strict=True):
            return None
    except OSError:
        return None
    pyproject = project_root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, TypeError, tomllib.TOMLDecodeError):
        return None
    project = payload.get("project")
    if not isinstance(project, dict) or project.get("name") != "pp-mcare":
        return None
    return project_root


def _distribution_content_sha256(package_root: Path) -> str:
    project_root = _source_project_root(package_root)
    if project_root is not None:
        entries = _source_distribution_entries(package_root, project_root)
    else:
        entries = _installed_distribution_entries()
    return _digest_named_content(entries)


def _package_version(package_root: Path) -> str:
    project_root = _source_project_root(package_root)
    if project_root is not None:
        pyproject = project_root / "pyproject.toml"
        try:
            payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            version = payload["project"]["version"]
        except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
            raise RegressionFailure("包版本身份无法读取") from exc
    else:
        try:
            version = importlib.metadata.version("pp-mcare")
        except importlib.metadata.PackageNotFoundError as exc:
            raise RegressionFailure("包版本身份无法读取") from exc
    if not isinstance(version, str) or not version:
        raise RegressionFailure("包版本身份无效")
    return version


@dataclass(frozen=True)
class SourceCheckoutIdentity:
    commit: str
    dirty: bool


def _source_checkout_identity(package_root: Path) -> SourceCheckoutIdentity | None:
    project_root = _source_project_root(package_root)
    if project_root is None:
        return None
    try:
        root_result = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        repository_root = Path(root_result.stdout.strip()).resolve(strict=True)
        if not project_root.resolve(strict=True).is_relative_to(repository_root):
            return None
        tracked_paths = tuple(
            str((package_root / relative_path).relative_to(repository_root))
            for relative_path in _IMPLEMENTATION_FILES
        ) + tuple(
            str((project_root / filename).relative_to(repository_root))
            for filename in ("pyproject.toml", "LICENSE.paddledetection", "NOTICE")
        )
        tracked_result = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "ls-files",
                "--error-unmatch",
                "--",
                *tracked_paths,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if set(tracked_result.stdout.splitlines()) != set(tracked_paths):
            return None
        commit_result = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        status_result = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
                str(project_root.relative_to(repository_root)),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = commit_result.stdout.strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        return None
    return SourceCheckoutIdentity(commit=commit, dirty=bool(status_result.stdout))


def _source_checkout_commit(package_root: Path) -> str | None:
    identity = _source_checkout_identity(package_root)
    return None if identity is None else identity.commit


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _release_manifest_path_for_package(package_root: Path) -> Path | None:
    try:
        active_release = _RELEASE_MANIFEST_PATH.parent.resolve(strict=True)
        installed_package = package_root.resolve(strict=True)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RegressionFailure("发布清单无法读取") from exc
    if not installed_package.is_relative_to(active_release):
        return None
    return _RELEASE_MANIFEST_PATH


def _release_artifact_identity(
    *,
    package_root: Path,
    package_version: str,
    distribution_content_sha256: str,
    source_checkout_commit: str | None,
) -> dict[str, object]:
    if source_checkout_commit is not None:
        return {"manifest_status": "source_checkout", "wheel_sha256": None}
    manifest_path = _release_manifest_path_for_package(package_root)
    if manifest_path is None:
        return {"manifest_status": "not_present", "wheel_sha256": None}
    try:
        manifest_identity = manifest_path.lstat()
    except FileNotFoundError:
        return {"manifest_status": "not_present", "wheel_sha256": None}
    except OSError as exc:
        raise RegressionFailure("发布清单无法读取") from exc
    if not stat.S_ISREG(manifest_identity.st_mode) or manifest_path.is_symlink():
        raise RegressionFailure("发布清单无效")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegressionFailure("发布清单无法读取") from exc
    expected = {
        "manifest_version": "1",
        "package_name": "pp-mcare",
        "package_version": package_version,
        "installed_distribution_sha256": distribution_content_sha256,
    }
    expected_keys = {
        *expected,
        "wheel_sha256",
        "contract_wheel_sha256",
        "git_commit",
        "release_name",
    }
    git_commit = payload.get("git_commit") if isinstance(payload, dict) else None
    release_name = payload.get("release_name") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or set(payload) != expected_keys
        or any(payload.get(key) != value for key, value in expected.items())
        or not _valid_sha256(payload.get("wheel_sha256"))
        or not _valid_sha256(payload.get("contract_wheel_sha256"))
        or not isinstance(git_commit, str)
        or len(git_commit) != 40
        or any(character not in "0123456789abcdef" for character in git_commit)
        or not isinstance(release_name, str)
        or not 7 <= len(release_name) <= 40
        or any(character not in "0123456789abcdef" for character in release_name)
        or not git_commit.startswith(release_name)
    ):
        raise RegressionFailure("发布清单身份不匹配")
    return {
        "manifest_status": "verified",
        "wheel_sha256": payload["wheel_sha256"],
        "contract_wheel_sha256": payload["contract_wheel_sha256"],
        "git_commit": git_commit,
        "release_name": release_name,
    }


def read_implementation_identity() -> dict[str, object]:
    package_root = Path(__file__).resolve().parent
    package_version = _package_version(package_root)
    source_checkout = _source_checkout_identity(package_root)
    source_checkout_commit = None if source_checkout is None else source_checkout.commit
    distribution_content_sha256 = _distribution_content_sha256(package_root)
    release_artifact = _release_artifact_identity(
        package_root=package_root,
        package_version=package_version,
        distribution_content_sha256=distribution_content_sha256,
        source_checkout_commit=source_checkout_commit,
    )
    reported_commit = source_checkout_commit
    if reported_commit is None and release_artifact["manifest_status"] == "verified":
        reported_commit = release_artifact["git_commit"]
    return {
        "package_name": "pp-mcare",
        "package_version": package_version,
        "regression_runtime_sha256": _implementation_sha256(package_root),
        "distribution_content_sha256": distribution_content_sha256,
        "git_commit": reported_commit,
        "git_dirty": None if source_checkout is None else source_checkout.dirty,
        "release_artifact": release_artifact,
        "capability": {
            "protocol_version": PROTOCOL_VERSION,
            "action_source_key": _ACTION_PLUGIN.source_key,
            "algorithm_version": _ACTION_PLUGIN.algorithm_version,
            "rule_version": _ACTION_PLUGIN.rule_version,
            "parameter_version": _ACTION_PLUGIN.parameter_version,
            "subject_tracker_version": SUBJECT_TRACKER_VERSION,
        },
    }


@dataclass(frozen=True)
class ResourceSnapshot:
    process_rss_bytes: int
    system_memory_used_bytes: int
    memory_available_bytes: int
    swap_used_bytes: int
    swap_free_bytes: int
    unreadable_process_count: int = 0


def read_resource_snapshot() -> ResourceSnapshot:
    root = psutil.Process()
    unreadable_process_count = 0
    try:
        descendants = root.children(recursive=True)
    except psutil.NoSuchProcess:
        descendants = []
    except psutil.AccessDenied:
        descendants = []
        unreadable_process_count += 1
    processes = {process.pid: process for process in (root, *descendants)}
    process_tree_rss = 0
    for process in processes.values():
        try:
            process_tree_rss += int(process.memory_info().rss)
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            unreadable_process_count += 1
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return ResourceSnapshot(
        process_rss_bytes=process_tree_rss,
        system_memory_used_bytes=int(memory.used),
        memory_available_bytes=int(memory.available),
        swap_used_bytes=int(swap.used),
        swap_free_bytes=int(swap.free),
        unreadable_process_count=unreadable_process_count,
    )


class ResourceSampler:
    JOIN_TIMEOUT_SECONDS = 1.0

    def __init__(self, *, reader=read_resource_snapshot, interval_seconds: float = 0.5):
        self._reader = reader
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sampling_error: BaseException | None = None
        self.peak: ResourceSnapshot | None = None

    def sample_once(self) -> ResourceSnapshot:
        current = self._reader()
        if self.peak is None:
            self.peak = current
        else:
            self.peak = ResourceSnapshot(
                process_rss_bytes=max(self.peak.process_rss_bytes, current.process_rss_bytes),
                system_memory_used_bytes=max(
                    self.peak.system_memory_used_bytes,
                    current.system_memory_used_bytes,
                ),
                memory_available_bytes=min(
                    self.peak.memory_available_bytes,
                    current.memory_available_bytes,
                ),
                swap_used_bytes=max(self.peak.swap_used_bytes, current.swap_used_bytes),
                swap_free_bytes=min(self.peak.swap_free_bytes, current.swap_free_bytes),
                unreadable_process_count=max(
                    self.peak.unreadable_process_count,
                    current.unreadable_process_count,
                ),
            )
        return current

    def _sample_until_stopped(self) -> None:
        try:
            while True:
                stopped = self._stop.wait(self._interval_seconds)
                self.sample_once()
                if stopped:
                    return
        except BaseException as exc:
            self._sampling_error = exc
            self._stop.set()

    def __enter__(self) -> ResourceSampler:
        try:
            self.sample_once()
        except BaseException as exc:
            raise RegressionFailure("资源采样失败") from exc
        self._thread = threading.Thread(target=self._sample_until_stopped, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.JOIN_TIMEOUT_SECONDS)
            if self._thread.is_alive():
                raise RegressionFailure("资源采样失败")
        if self._sampling_error is not None:
            raise RegressionFailure("资源采样失败") from self._sampling_error


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same_file_identity(before: os.stat_result, after: os.stat_result) -> bool:
    fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_gid",
        "st_size",
        "st_mtime_ns",
    )
    return all(getattr(before, field) == getattr(after, field) for field in fields)


def _same_source_copy_identity(before: os.stat_result, after: os.stat_result) -> bool:
    fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_gid",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    return all(getattr(before, field) == getattr(after, field) for field in fields)


def _open_fd_path(descriptor: int) -> Path:
    if sys.platform == "linux":
        return Path(f"/proc/self/fd/{descriptor}")
    if sys.platform == "darwin":
        return Path(f"/dev/fd/{descriptor}")
    raise RegressionFailure("当前平台不支持安全的固定输入路径")


def _rewind_video(descriptor: int) -> None:
    try:
        if os.lseek(descriptor, 0, os.SEEK_SET) != 0:
            raise RegressionFailure("固定输入无法复位")
    except OSError as exc:
        raise RegressionFailure("固定输入无法复位") from exc


def _write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise RegressionFailure("验证副本写入失败")
        view = view[written:]


def _create_video_snapshot(
    source_descriptor: int,
    source_identity: os.stat_result,
) -> tuple[int, os.stat_result]:
    temporary_directory = Path(tempfile.mkdtemp(prefix="pp-mcare-input-snapshot-"))
    snapshot_path = temporary_directory / "input.snapshot"
    writer: int | None = None
    reader: int | None = None
    try:
        os.chmod(temporary_directory, 0o700)
        if shutil.disk_usage(temporary_directory).free < source_identity.st_size:
            raise RegressionFailure("验证副本磁盘空间不足")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        writer = os.open(snapshot_path, flags, 0o600)
        _rewind_video(source_descriptor)
        copied_bytes = 0
        while True:
            chunk = os.read(source_descriptor, 1024 * 1024)
            if not chunk:
                break
            _write_all(writer, chunk)
            copied_bytes += len(chunk)
        os.fsync(writer)
        source_after_copy = os.fstat(source_descriptor)
        if (
            copied_bytes != source_identity.st_size
            or not _same_source_copy_identity(source_identity, source_after_copy)
        ):
            raise RegressionFailure("视频在验证副本创建期间发生变化")
        os.fchmod(writer, 0o400)
        os.close(writer)
        writer = None

        read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        read_flags |= getattr(os, "O_NOFOLLOW", 0)
        reader = os.open(snapshot_path, read_flags)
        snapshot_identity = os.fstat(reader)
        if (
            not stat.S_ISREG(snapshot_identity.st_mode)
            or snapshot_identity.st_size != source_identity.st_size
            or stat.S_IMODE(snapshot_identity.st_mode) != 0o400
        ):
            raise RegressionFailure("验证副本无效")
        os.unlink(snapshot_path)
        os.rmdir(temporary_directory)
        result = reader
        reader = None
        return result, snapshot_identity
    except RegressionFailure:
        raise
    except OSError as exc:
        raise RegressionFailure("验证副本创建失败") from exc
    finally:
        if writer is not None:
            os.close(writer)
        if reader is not None:
            os.close(reader)
        try:
            os.unlink(snapshot_path)
        except FileNotFoundError:
            pass
        try:
            os.rmdir(temporary_directory)
        except FileNotFoundError:
            pass


def read_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for distribution in ("paddlepaddle", "paddlex"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "not_installed"
    try:
        cv2 = importlib.import_module("cv2")
    except (ImportError, OSError) as exc:
        raise RegressionFailure("推理运行时不可用") from exc
    opencv_version = getattr(cv2, "__version__", None)
    if not isinstance(opencv_version, str) or not opencv_version.strip():
        raise RegressionFailure("推理运行时不可用")
    versions["opencv"] = opencv_version.strip()
    try:
        completed = subprocess.run(
            ["/usr/bin/ffmpeg", "-version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RegressionFailure("媒体运行时不可用") from exc
    first_line = completed.stdout.splitlines()
    if not first_line:
        raise RegressionFailure("媒体运行时不可用")
    versions["ffmpeg"] = first_line[0]
    return versions


def read_hardware() -> dict[str, object]:
    cpu_model = "unknown"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "cpu_model": cpu_model,
        "vcpu_count": os.cpu_count(),
        "physical_memory_bytes": int(memory.total),
        "swap_total_bytes": int(swap.total),
    }


def _validated_report_path(path: Path) -> tuple[Path, int]:
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise RegressionFailure("报告路径无效")
    parent_fd: int | None = None
    try:
        parent = path.parent
        if parent.resolve(strict=True) != parent or not parent.is_dir():
            raise RegressionFailure("报告路径无效")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        parent_fd = os.open(parent, flags)
        try:
            os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise RegressionFailure("报告目标已存在")
        return path, parent_fd
    except RegressionFailure:
        if parent_fd is not None:
            os.close(parent_fd)
        raise
    except OSError as exc:
        if parent_fd is not None:
            os.close(parent_fd)
        raise RegressionFailure("报告路径无效") from exc


def _reject_colliding_report(
    *,
    video: Path,
    video_identity: os.stat_result,
    report: Path,
    report_parent_fd: int,
) -> None:
    try:
        if video.resolve(strict=True) == report:
            raise RegressionFailure("报告路径不得指向输入视频")
        try:
            report_identity = os.stat(
                report.name,
                dir_fd=report_parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return
        if (report_identity.st_dev, report_identity.st_ino) == (
            video_identity.st_dev,
            video_identity.st_ino,
        ):
            raise RegressionFailure("报告路径不得指向输入视频")
    except RegressionFailure:
        raise
    except OSError as exc:
        raise RegressionFailure("输入与报告路径无法安全核对") from exc


def _link_anonymous_file_linux(
    descriptor: int,
    parent_descriptor: int,
    final_name: str,
) -> None:
    if type(descriptor) is not int or descriptor < 0:
        raise RegressionFailure("报告文件描述符无效")
    if type(parent_descriptor) is not int or parent_descriptor < 0:
        raise RegressionFailure("报告目录描述符无效")
    if not isinstance(final_name, str):
        raise RegressionFailure("报告文件名无效")
    encoded_name = os.fsencode(final_name)
    if (
        not encoded_name
        or encoded_name in {b".", b".."}
        or b"/" in encoded_name
        or b"\0" in encoded_name
    ):
        raise RegressionFailure("报告文件名无效")
    proc_fd_path = f"/proc/self/fd/{descriptor}"
    try:
        proc_identity = os.stat(proc_fd_path, follow_symlinks=True)
        descriptor_identity = os.fstat(descriptor)
    except OSError as exc:
        raise RegressionFailure("当前 Linux 不支持安全报告发布") from exc
    if (proc_identity.st_dev, proc_identity.st_ino) != (
        descriptor_identity.st_dev,
        descriptor_identity.st_ino,
    ):
        raise RegressionFailure("当前 Linux 不支持安全报告发布")
    libc = ctypes.CDLL(None, use_errno=True)
    linkat = libc.linkat
    linkat.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    linkat.restype = ctypes.c_int
    if (
        linkat(
            _AT_FDCWD,
            os.fsencode(proc_fd_path),
            parent_descriptor,
            encoded_name,
            _AT_SYMLINK_FOLLOW,
        )
        != 0
    ):
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def _publish_report_linux(parent_descriptor: int, final_name: str, content: bytes) -> None:
    temporary_flag = getattr(os, "O_TMPFILE", 0)
    if not temporary_flag:
        raise RegressionFailure("当前 Linux 不支持安全报告发布")
    descriptor: int | None = None
    try:
        descriptor = os.open(
            ".",
            os.O_WRONLY | temporary_flag | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=parent_descriptor,
        )
        _write_all(descriptor, content)
        os.fsync(descriptor)
        identity = os.fstat(descriptor)
        if (
            not stat.S_ISREG(identity.st_mode)
            or stat.S_IMODE(identity.st_mode) != 0o600
            or identity.st_nlink != 0
        ):
            raise RegressionFailure("匿名报告文件无效")
        _link_anonymous_file_linux(descriptor, parent_descriptor, final_name)
        os.fsync(parent_descriptor)
    except OSError as exc:
        raise RegressionFailure("报告写入失败") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _publish_report(parent_descriptor: int, final_name: str, content: bytes) -> None:
    if sys.platform != "linux":
        raise RegressionFailure("当前平台不支持安全报告发布")
    _publish_report_linux(parent_descriptor, final_name, content)


def _atomic_write_report(path: Path, report: dict[str, object]) -> None:
    path, parent_fd = _validated_report_path(path)
    try:
        content = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        _publish_report(parent_fd, path.name, content)
    finally:
        os.close(parent_fd)


def _video_metadata(source: SourceVideoMetadata, *, sha256: str, size_bytes: int) -> dict:
    return {
        "sha256": sha256,
        "size_bytes": size_bytes,
        "duration_seconds": source.duration_seconds,
        "width": source.width,
        "height": source.height,
        "fps": source.fps,
        "frame_count": source.frame_count,
        "codec_name": source.codec_name,
    }


def _local_job(*, size_bytes: int, object_hash: str) -> ClaimedJob:
    return ClaimedJob.from_dict(
        {
            "protocol_version": PROTOCOL_VERSION,
            "job_id": 1,
            "action_source_key": _ACTION_PLUGIN.source_key,
            "algorithm_version": _ACTION_PLUGIN.algorithm_version,
            "rule_version": _ACTION_PLUGIN.rule_version,
            "parameter_version": _ACTION_PLUGIN.parameter_version,
            "subject_tracker_version": SUBJECT_TRACKER_VERSION,
            "lease_token": "local-regression-only",
            "lease_expires_at": "2099-01-01T00:00:00Z",
            "heartbeat_interval_seconds": 60,
            "download": {
                "url": "https://regression.invalid/original.mp4",
                "bucket": "local-regression",
                "object_key": "original.mp4",
                "object_hash": object_hash,
                "expires_at": "2099-01-01T00:00:00Z",
                "size_bytes": size_bytes,
                "content_type": "video/mp4",
            },
            "upload": {
                "bucket": "local-regression",
                "object_key": "skeleton.mp4",
                "token": "local-regression-only",
                "expires_at": "2099-01-01T00:00:00Z",
            },
        }
    )


def _acceptance_failures(mode: dict[str, object]) -> list[str]:
    failures: list[str] = []
    for field in ("decoded_frame_count", "inferred_frame_count", "encoded_frame_count"):
        if mode.get(field) != EXPECTED_DECODED_FRAME_COUNT:
            failures.append(f"{field}_mismatch")
    result = mode.get("result")
    if not isinstance(result, dict):
        return failures + ["invalid_result"]
    total = result.get("total_count")
    standard = result.get("standard_count")
    nonstandard = result.get("nonstandard_count")
    left = result.get("left_event_count")
    right = result.get("right_event_count")
    if (
        isinstance(total, bool)
        or not isinstance(total, int)
        or isinstance(standard, bool)
        or not isinstance(standard, int)
        or isinstance(nonstandard, bool)
        or not isinstance(nonstandard, int)
        or total != standard + nonstandard
    ):
        failures.append("count_invariant_failed")
    if total != EXPECTED_MANUAL_TOTAL_COUNT:
        failures.append("manual_total_count_mismatch")
    if (
        isinstance(left, bool)
        or not isinstance(left, int)
        or isinstance(right, bool)
        or not isinstance(right, int)
        or total != max(left, right)
    ):
        failures.append("side_max_count_mismatch")
    total_seconds = mode.get("total_seconds")
    if (
        isinstance(total_seconds, bool)
        or not isinstance(total_seconds, (int, float))
        or not math.isfinite(total_seconds)
        or total_seconds < 0
    ):
        failures.append("invalid_total_seconds")
    peak = mode.get("resource_peak")
    if not isinstance(peak, dict):
        failures.append("invalid_resource_peak")
    else:
        rss = peak.get("peak_rss_bytes")
        swap = peak.get("swap_used_bytes")
        unreadable = peak.get("unreadable_process_count")
        if isinstance(rss, bool) or not isinstance(rss, int) or rss < 0:
            failures.append("invalid_process_rss")
        elif rss >= MAX_PROCESS_RSS_BYTES:
            failures.append("all_frame_rss_limit_exceeded")
        if isinstance(unreadable, bool) or not isinstance(unreadable, int) or unreadable < 0:
            failures.append("invalid_unreadable_process_count")
        elif unreadable:
            failures.append("resource_sampling_incomplete")
        if isinstance(swap, bool) or not isinstance(swap, int) or swap < 0:
            failures.append("invalid_swap_used")
        elif swap != 0:
            failures.append("swap_used")
    return failures


def _failure_summary(stage: str) -> str:
    return {
        "input_validation": "回归参数校验失败",
        "hash_validation": "视频校验失败",
        "video_probe": "视频探测失败",
        "frame_validation": "视频帧数校验失败",
        "runtime_inventory": "运行环境读取失败",
        "all_frames": "全帧分析失败",
        "acceptance": "回归验收失败",
    }.get(stage, "回归执行失败")


def run_regression(
    *,
    video_path: str | os.PathLike[str],
    manual_total_count: int,
    report_path: str | os.PathLike[str],
) -> dict[str, object]:
    video = Path(video_path)
    report_file = Path(report_path)
    if type(manual_total_count) is not int or manual_total_count != EXPECTED_MANUAL_TOTAL_COUNT:
        raise RegressionFailure("人工真值必须为 90")
    _validated_path, report_parent_fd = _validated_report_path(report_file)
    video_descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        video_descriptor = os.open(video, flags)
        video_identity = os.fstat(video_descriptor)
    except OSError as exc:
        os.close(report_parent_fd)
        if video_descriptor is not None:
            os.close(video_descriptor)
        raise RegressionFailure("视频路径无效") from exc
    if not stat.S_ISREG(video_identity.st_mode):
        os.close(report_parent_fd)
        os.close(video_descriptor)
        raise RegressionFailure("视频路径无效")
    snapshot_descriptor: int | None = None
    try:
        try:
            _reject_colliding_report(
                video=video,
                video_identity=video_identity,
                report=report_file,
                report_parent_fd=report_parent_fd,
            )
            snapshot_descriptor, snapshot_identity = _create_video_snapshot(
                video_descriptor,
                video_identity,
            )
            stable_video = _open_fd_path(snapshot_descriptor)
        except BaseException:
            if snapshot_descriptor is not None:
                os.close(snapshot_descriptor)
            raise
    finally:
        os.close(report_parent_fd)
        os.close(video_descriptor)

    now = datetime.now(timezone.utc).isoformat()
    report: dict[str, object] = {
        "report_format_version": REPORT_FORMAT_VERSION,
        "status": "running",
        "started_at": now,
        "finished_at": None,
        "git_commit": None,
        "implementation": {},
        "versions": {},
        "hardware": {},
        "video": {},
        "model": {"name": PP_TINYPOSE_MODEL_NAME, "device": "cpu"},
        "manual_total_count": manual_total_count,
        "modes": [],
        "acceptance": {"passed": False, "failures": []},
    }
    stage = "implementation_identity"
    try:
        implementation = read_implementation_identity()
        report["implementation"] = implementation
        report["git_commit"] = implementation["git_commit"]
        stage = "hash_validation"
        actual_sha256 = sha256_file(stable_video)
        _rewind_video(snapshot_descriptor)
        if actual_sha256 != EXPECTED_VIDEO_SHA256:
            report["acceptance"] = {"passed": False, "failures": ["video_sha256_mismatch"]}
            raise RegressionFailure("视频 SHA-256 与固定样本不一致")
        if not _same_file_identity(snapshot_identity, os.fstat(snapshot_descriptor)):
            raise RegressionFailure("验证副本在校验期间发生变化")

        stage = "video_probe"
        source = probe_source_video(stable_video, pass_fds=(snapshot_descriptor,))
        _rewind_video(snapshot_descriptor)
        report["video"] = _video_metadata(
            source,
            sha256=actual_sha256,
            size_bytes=snapshot_identity.st_size,
        )
        if source.frame_count != EXPECTED_DECODED_FRAME_COUNT:
            stage = "frame_validation"
            report["acceptance"] = {
                "passed": False,
                "failures": ["source_frame_count_mismatch"],
            }
            raise RegressionFailure("视频帧数与固定样本不一致")

        stage = "runtime_inventory"
        report["versions"] = read_versions()
        report["hardware"] = read_hardware()

        stage = "all_frames"
        started = _CLOCK()
        with tempfile.TemporaryDirectory(prefix="pp-mcare-regression-") as temporary:
            output_path = Path(temporary) / "skeleton.mp4"
            with ResourceSampler() as sampler:
                result = run_local_pipeline(
                    _local_job(size_bytes=snapshot_identity.st_size, object_hash=actual_sha256),
                    stable_video,
                    output_path,
                    lambda _stage: None,
                    source_metadata=source,
                )
            total_seconds = _CLOCK() - started
        if sampler.peak is None:
            raise RegressionFailure("资源采样没有结果")
        _rewind_video(snapshot_descriptor)
        final_sha256 = sha256_file(stable_video)
        _rewind_video(snapshot_descriptor)
        if final_sha256 != actual_sha256 or not _same_file_identity(
            snapshot_identity,
            os.fstat(snapshot_descriptor),
        ):
            raise RegressionFailure("验证副本在分析期间发生变化")
        if not isinstance(result.counts, MotionCounts):
            raise RegressionFailure("正式流水线返回了无效计数")
        result_payload = result.result_payload_json()
        mode = {
            "name": "all_frames",
            "label": "全帧",
            "sample_fps": None,
            "status": "completed",
            "decoded_frame_count": result.decoded_frame_count,
            "inferred_frame_count": result.inferred_frame_count,
            "encoded_frame_count": result.encoded_frame_count,
            "inference_seconds": result.inference_seconds,
            "encoding_seconds": result.encoding_seconds,
            "total_seconds": total_seconds,
            "average_inference_ms_per_frame": (
                result.inference_seconds * 1000 / result.inferred_frame_count
            ),
            "count_error": result.counts.total_count - manual_total_count,
            "resource_peak": {
                **asdict(sampler.peak),
                "peak_rss_bytes": sampler.peak.process_rss_bytes,
            },
            "result": result_payload,
            "tracking_summary": result.tracking_summary_json(),
        }
        report["modes"] = [mode]
        failures = _acceptance_failures(mode)
        report["acceptance"] = {"passed": not failures, "failures": failures}
        if failures:
            stage = "acceptance"
            raise RegressionFailure("回归验收失败")

        report["status"] = "completed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write_report(report_file, report)
        return report
    except BaseException as exc:
        report["status"] = "failed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["failure"] = {
            "stage": stage,
            "error_summary": _failure_summary(stage),
        }
        try:
            _atomic_write_report(report_file, report)
        except RegressionFailure:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise RegressionFailure(_failure_summary(stage)) from exc
    finally:
        os.close(snapshot_descriptor)
