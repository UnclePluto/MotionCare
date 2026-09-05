from __future__ import annotations

import os
import re
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


_WORKSPACE_NAME = re.compile(r"job-([1-9][0-9]*)-([0-9a-f]{32})\Z")
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


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


def _remove_named_directory(root_fd: int, name: str) -> None:
    child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
    try:
        opened = os.fstat(child_fd)
        current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if not stat.S_ISDIR(current.st_mode) or (opened.st_dev, opened.st_ino) != (
            current.st_dev,
            current.st_ino,
        ):
            raise OSError("任务目录身份校验失败")
        _empty_directory(child_fd)
    finally:
        os.close(child_fd)
    current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
        raise OSError("任务目录清理时对象发生变化")
    os.rmdir(name, dir_fd=root_fd)


@dataclass
class TaskWorkspace:
    root: Path
    path: Path
    job_id: int
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
            for _ in range(10):
                name = f"job-{job_id}-{uuid.uuid4().hex}"
                try:
                    os.mkdir(name, mode=0o700, dir_fd=root_fd)
                except FileExistsError:
                    continue
                child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
                try:
                    os.fchmod(child_fd, 0o700)
                    created = os.fstat(child_fd)
                    linked = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
                    if (created.st_dev, created.st_ino) != (linked.st_dev, linked.st_ino):
                        raise OSError("任务目录创建竞态")
                finally:
                    os.close(child_fd)
                return cls(root=root_path, path=root_path / name, job_id=job_id)
        finally:
            os.close(root_fd)
        raise OSError("无法创建唯一任务目录")

    @property
    def input_path(self) -> Path:
        return self.path / "original.mp4"

    @property
    def output_path(self) -> Path:
        return self.path / "skeleton.mp4"

    @property
    def cleaned(self) -> bool:
        return self._cleaned

    def cleanup(self) -> bool:
        if self._cleaned:
            return True
        if not _WORKSPACE_NAME.fullmatch(self.path.name) or self.path.parent != self.root:
            raise OSError("拒绝清理非任务目录")
        root_fd = _open_directory(self.root)
        try:
            try:
                _remove_named_directory(root_fd, self.path.name)
            except FileNotFoundError:
                pass
        finally:
            os.close(root_fd)
        self._cleaned = True
        return True

    def __enter__(self) -> TaskWorkspace:
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.cleanup()


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
    root_path = Path(root)
    root_fd = _open_directory(root_path)
    scanned = removed = failed = 0
    cutoff = (time.time() if now is None else now) - max_age_seconds
    try:
        inspected = 0
        with os.scandir(root_fd) as entries:
            for entry in entries:
                if inspected >= limit * 4:
                    break
                inspected += 1
                name = entry.name
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
                    _remove_named_directory(root_fd, name)
                    removed += 1
                except (FileNotFoundError, OSError):
                    failed += 1
    finally:
        os.close(root_fd)
    return CleanupSummary(scanned=scanned, removed=removed, failed=failed)
