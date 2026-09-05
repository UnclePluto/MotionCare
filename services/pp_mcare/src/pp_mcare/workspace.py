from __future__ import annotations

import logging
import os
import re
import stat
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

if sys.platform == "darwin":
    import fcntl


_WORKSPACE_NAME = re.compile(r"job-([1-9][0-9]*)-([0-9a-f]{32})\Z")
_LEAF_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_CURSOR_NAME = ".pp-mcare-cleanup-cursor"
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanupSummary:
    scanned: int
    removed: int
    failed: int


def _open_directory(path: Path) -> int:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise OSError("当前平台不支持安全目录操作")
    return os.open(path, _DIRECTORY_FLAGS)


def _empty_directory(directory_fd: int) -> None:
    """Delete entries by descriptor without ever following directory symlinks."""
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            before = os.stat(entry.name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(before.st_mode):
                child_fd = os.open(entry.name, _DIRECTORY_FLAGS, dir_fd=directory_fd)
                try:
                    opened = os.fstat(child_fd)
                    current = os.stat(entry.name, dir_fd=directory_fd, follow_symlinks=False)
                    if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                        raise OSError("任务目录清理时对象发生变化")
                    _empty_directory(child_fd)
                finally:
                    os.close(child_fd)
                current = os.stat(entry.name, dir_fd=directory_fd, follow_symlinks=False)
                if (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino):
                    raise OSError("任务目录清理时对象发生变化")
                os.rmdir(entry.name, dir_fd=directory_fd)
            else:
                os.unlink(entry.name, dir_fd=directory_fd)


def _remove_named_directory(
    root_fd: int,
    name: str,
    *,
    expected: os.stat_result | None = None,
    cutoff: float | None = None,
) -> bool:
    child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
    try:
        opened = os.fstat(child_fd)
        current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        expected_identity = (
            (expected.st_dev, expected.st_ino)
            if expected is not None
            else (opened.st_dev, opened.st_ino)
        )
        if (
            not stat.S_ISDIR(current.st_mode)
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            or (opened.st_dev, opened.st_ino) != expected_identity
        ):
            raise OSError("任务目录身份校验失败")
        if cutoff is not None and opened.st_mtime >= cutoff:
            return False
        _empty_directory(child_fd)
    finally:
        os.close(child_fd)
    current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
        raise OSError("任务目录清理时对象发生变化")
    os.rmdir(name, dir_fd=root_fd)
    return True


def _unlink_replacement(root_fd: int, name: str) -> None:
    try:
        current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(current.st_mode) or not stat.S_ISDIR(current.st_mode):
        os.unlink(name, dir_fd=root_fd)


def _name_for_open_directory(root_fd: int, directory_fd: int) -> str | None:
    try:
        if sys.platform.startswith("linux"):
            raw_path = os.readlink(f"/proc/self/fd/{directory_fd}")
        elif sys.platform == "darwin":
            raw_path = os.fsdecode(fcntl.fcntl(directory_fd, 50, b"\0" * 1024)).rstrip("\0")
        else:
            return None
        current_path = Path(raw_path)
        parent_fd = _open_directory(current_path.parent)
        try:
            parent = os.fstat(parent_fd)
            root = os.fstat(root_fd)
            if (parent.st_dev, parent.st_ino) != (root.st_dev, root.st_ino):
                return None
        finally:
            os.close(parent_fd)
        return current_path.name
    except (OSError, ValueError):
        return None


def _remove_owned_directory(
    root_fd: int,
    identity: tuple[int, int],
    *,
    directory_fd: int | None = None,
    expected_name: str | None = None,
    fallback_names: tuple[str, ...] = (),
) -> bool:
    names: list[str] = []
    if expected_name is not None:
        names.append(expected_name)
    if directory_fd is not None:
        discovered = _name_for_open_directory(root_fd, directory_fd)
        if discovered is not None and discovered not in names:
            names.append(discovered)
    names.extend(name for name in fallback_names if name not in names)
    for name in names:
        try:
            current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == identity:
            _remove_named_directory(root_fd, name, expected=current)
            return True
    return False


@dataclass
class TaskWorkspace:
    root: Path
    path: Path
    job_id: int
    _root_fd: int = field(repr=False)
    _directory_fd: int = field(repr=False)
    _identity: tuple[int, int] = field(repr=False)
    _cleaned: bool = False

    @classmethod
    def create(cls, root: Path, job_id: int) -> TaskWorkspace:
        if isinstance(job_id, bool) or not isinstance(job_id, int):
            raise TypeError("job_id 必须是正整数")
        if job_id <= 0:
            raise ValueError("job_id 必须是正整数")
        root_path = Path(root)
        try:
            root_path.mkdir(mode=0o700, parents=True, exist_ok=True)
        except FileExistsError:
            raise OSError("任务根目录无效") from None
        root_fd = _open_directory(root_path)
        try:
            os.fchmod(root_fd, 0o700)
        except BaseException:
            os.close(root_fd)
            raise
        for _ in range(10):
            name = f"job-{job_id}-{uuid.uuid4().hex}"
            child_fd: int | None = None
            created_identity: tuple[int, int] | None = None
            before_names = frozenset(os.listdir(root_fd))
            try:
                os.mkdir(name, mode=0o700, dir_fd=root_fd)
                created = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
                if not stat.S_ISDIR(created.st_mode):
                    raise OSError("任务目录创建竞态")
                created_identity = (created.st_dev, created.st_ino)
                child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
                created = os.fstat(child_fd)
                if created_identity != (created.st_dev, created.st_ino):
                    raise OSError("任务目录创建竞态")
                os.fchmod(child_fd, 0o700)
                linked = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
                if created_identity != (linked.st_dev, linked.st_ino):
                    raise OSError("任务目录创建竞态")
                return cls(
                    root_path,
                    root_path / name,
                    job_id,
                    root_fd,
                    child_fd,
                    created_identity,
                )
            except FileExistsError:
                continue
            except BaseException:
                if created_identity is not None:
                    try:
                        fallback_names = tuple(
                            entry
                            for entry in os.listdir(root_fd)
                            if entry not in before_names and entry != name
                        )
                        _remove_owned_directory(
                            root_fd,
                            created_identity,
                            directory_fd=child_fd,
                            expected_name=name,
                            fallback_names=fallback_names,
                        )
                    except OSError:
                        pass
                if child_fd is not None:
                    os.close(child_fd)
                try:
                    _unlink_replacement(root_fd, name)
                except OSError:
                    pass
                os.close(root_fd)
                raise
        os.close(root_fd)
        raise OSError("无法创建唯一任务目录")

    @staticmethod
    def _validate_leaf(name: str) -> None:
        if not isinstance(name, str) or not _LEAF_NAME.fullmatch(name):
            raise OSError("任务文件名无效")

    @property
    def input_path(self) -> Path:
        return self.path / "original.mp4"

    @property
    def output_path(self) -> Path:
        return self.path / "skeleton.mp4"

    @property
    def cleaned(self) -> bool:
        return self._cleaned

    def create_file(self, name: str) -> int:
        self._validate_leaf(name)
        if self._cleaned:
            raise OSError("任务目录已清理")
        descriptor = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW,
            0o600,
            dir_fd=self._directory_fd,
        )
        try:
            os.fchmod(descriptor, 0o600)
        except BaseException:
            os.close(descriptor)
            self.unlink_file(name)
            raise
        return descriptor

    def open_file(self, name: str, flags: int = os.O_RDONLY) -> int:
        self._validate_leaf(name)
        if self._cleaned:
            raise OSError("任务目录已清理")
        descriptor = os.open(name, flags | _FILE_NOFOLLOW, dir_fd=self._directory_fd)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(descriptor)
            raise OSError("任务文件无效")
        return descriptor

    def unlink_file(self, name: str) -> None:
        self._validate_leaf(name)
        try:
            os.unlink(name, dir_fd=self._directory_fd)
        except FileNotFoundError:
            pass

    def file_matches(self, name: str, descriptor: int) -> bool:
        self._validate_leaf(name)
        opened = os.fstat(descriptor)
        try:
            linked = os.stat(name, dir_fd=self._directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return stat.S_ISREG(linked.st_mode) and (opened.st_dev, opened.st_ino) == (
            linked.st_dev,
            linked.st_ino,
        )

    def secure_tool_path(self, name: str) -> Path:
        self._validate_leaf(name)
        candidate = Path(f"/proc/self/fd/{self._directory_fd}")
        if not candidate.is_dir():
            raise OSError("当前平台不支持安全外部工具路径")
        return candidate / name

    def cleanup(self) -> bool:
        if self._cleaned:
            return True
        if not _WORKSPACE_NAME.fullmatch(self.path.name) or self.path.parent != self.root:
            raise OSError("拒绝清理非任务目录")
        completed = False
        try:
            removed = _remove_owned_directory(
                self._root_fd,
                self._identity,
                directory_fd=self._directory_fd,
                expected_name=self.path.name,
            )
            if not removed:
                raise OSError("任务目录不再位于受信任根目录")
            _unlink_replacement(self._root_fd, self.path.name)
            completed = True
        finally:
            os.close(self._directory_fd)
            os.close(self._root_fd)
            self._cleaned = completed
        return True

    def __enter__(self) -> TaskWorkspace:
        return self

    def __exit__(self, exc_type, _value, _traceback) -> None:
        try:
            self.cleanup()
        except Exception:
            if exc_type is not None and not issubclass(exc_type, Exception):
                _logger.critical("motion_analysis_workspace_cleanup_fatal")
                return
            raise


def _read_cursor(root_fd: int) -> tuple[str, bool]:
    try:
        descriptor = os.open(
            _CURSOR_NAME,
            os.O_RDONLY | _FILE_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=root_fd,
        )
    except FileNotFoundError:
        return "", False
    except OSError:
        return "", True
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 256:
            return "", True
        return os.read(descriptor, 257).decode("ascii"), False
    except (OSError, UnicodeDecodeError):
        return "", True
    finally:
        os.close(descriptor)


def _write_cursor(root_fd: int, value: str) -> None:
    temporary = f".cleanup-cursor-{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW,
            0o600,
            dir_fd=root_fd,
        )
        os.fchmod(descriptor, 0o600)
        payload = value.encode("ascii")
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("游标写入失败")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, _CURSOR_NAME, src_dir_fd=root_fd, dst_dir_fd=root_fd)
    except BaseException:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.unlink(temporary, dir_fd=root_fd)
        except OSError:
            pass
        raise


def _discard_corrupt_cursor(root_fd: int) -> None:
    try:
        current = os.stat(_CURSOR_NAME, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(current.st_mode):
        _remove_named_directory(root_fd, _CURSOR_NAME, expected=current)
        return
    os.unlink(_CURSOR_NAME, dir_fd=root_fd)


def cleanup_stale_workspaces(
    root: Path,
    *,
    max_age_seconds: float,
    limit: int = 100,
    now: float | None = None,
) -> CleanupSummary:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit 必须是正整数")
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds 必须是正数")
    root_fd = _open_directory(Path(root))
    scanned = removed = failed = 0
    cutoff = (time.time() if now is None else now) - max_age_seconds
    last_inspected = ""
    try:
        with os.scandir(root_fd) as entries:
            names = sorted(entry.name for entry in entries if entry.name != _CURSOR_NAME)
        cursor, cursor_invalid = _read_cursor(root_fd)
        if cursor_invalid:
            failed += 1
            try:
                _discard_corrupt_cursor(root_fd)
            except OSError:
                failed += 1
        split = next((index for index, name in enumerate(names) if name > cursor), len(names))
        ordered = names[split:] + names[:split]
        for name in ordered[: limit * 4]:
            last_inspected = name
            if not _WORKSPACE_NAME.fullmatch(name):
                continue
            try:
                item = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
                if not stat.S_ISDIR(item.st_mode):
                    continue
                if scanned >= limit:
                    break
                scanned += 1
                if item.st_mtime >= cutoff:
                    continue
                if _remove_named_directory(root_fd, name, expected=item, cutoff=cutoff):
                    removed += 1
            except (FileNotFoundError, OSError):
                failed += 1
        if last_inspected:
            try:
                _write_cursor(root_fd, last_inspected)
            except (OSError, UnicodeEncodeError):
                failed += 1
    finally:
        os.close(root_fd)
    return CleanupSummary(scanned=scanned, removed=removed, failed=failed)
