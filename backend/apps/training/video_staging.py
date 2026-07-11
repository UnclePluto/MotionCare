import fcntl
import hashlib
import os
import re
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

from .models import TrainingVideo


SESSION_DIRECTORY_PATTERN = re.compile(r"^(?P<video_id>[1-9]\d*)-[0-9a-f]{32}$")
QUARANTINE_DIRECTORY_NAME = ".quarantine"
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600


class SegmentConflict(Exception):
    pass


class SessionConflict(Exception):
    pass


def _configured_staging_root(*, create: bool = True) -> Path:
    root = Path(settings.TRAINING_VIDEO_STAGING_ROOT).absolute()
    if create:
        root.mkdir(parents=True, exist_ok=True, mode=_PRIVATE_DIRECTORY_MODE)
    try:
        metadata = root.lstat()
    except FileNotFoundError as exc:
        raise ValidationError("训练视频临时根目录不存在") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise ValidationError("训练视频临时根目录不能是符号链接")
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValidationError("训练视频临时根目录无效")
    if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
        raise ValidationError("训练视频临时根目录权限不安全")
    return root


def staging_root() -> Path:
    return _configured_staging_root()


def _session_directory_name(video: TrainingVideo) -> str:
    if video.pk is None:
        raise ValidationError("训练视频会话尚未保存")
    return f"{video.pk}-{video.client_session_id.hex}"


def _reject_existing_symlink(path: Path, message: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode):
        raise ValidationError(message)


def session_root(video: TrainingVideo) -> Path:
    root = _configured_staging_root()
    candidate = root / _session_directory_name(video)
    _reject_existing_symlink(candidate, "训练视频会话目录不能是符号链接")
    return candidate


def segment_path(video: TrainingVideo, index: int) -> Path:
    root = session_root(video)
    segments = root / "segments"
    _reject_existing_symlink(segments, "训练视频分段目录不能是符号链接")
    candidate = segments / f"{index:06d}.mp4"
    _reject_existing_symlink(candidate, "训练视频分段不能是符号链接")
    return candidate


def _open_directory(path: Path) -> int:
    try:
        return os.open(path, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise ValidationError("训练视频目录无效或包含符号链接") from exc


def _ensure_child_directory(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, _PRIVATE_DIRECTORY_MODE, dir_fd=parent_fd)
    except FileExistsError:
        pass
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValidationError("训练视频中间目录不能是符号链接")
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        os.fchmod(descriptor, _PRIVATE_DIRECTORY_MODE)
        return descriptor
    except OSError as exc:
        raise ValidationError("训练视频中间目录无效或包含符号链接") from exc


@contextmanager
def _session_directory_fd(video: TrainingVideo, *, create: bool):
    root = _configured_staging_root(create=create)
    root_fd = _open_directory(root)
    session_fd = None
    try:
        name = _session_directory_name(video)
        if create:
            session_fd = _ensure_child_directory(root_fd, name)
        else:
            try:
                session_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
            except FileNotFoundError:
                yield root, root_fd, None
                return
            except OSError as exc:
                raise ValidationError("训练视频会话目录无效或包含符号链接") from exc
        yield root, root_fd, session_fd
    finally:
        if session_fd is not None:
            os.close(session_fd)
        os.close(root_fd)


def ensure_working_directory(video: TrainingVideo) -> Path:
    with _session_directory_fd(video, create=True) as (_, _, session_fd):
        working_fd = _ensure_child_directory(session_fd, "working")
        os.close(working_fd)
    return session_root(video) / "working"


@contextmanager
def segment_install_lock(video: TrainingVideo, index: int):
    with _session_directory_fd(video, create=True) as (_, _, session_fd):
        lock_directory_fd = _ensure_child_directory(session_fd, "locks")
        try:
            lock_name = f"{index:06d}.lock"
            flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
            try:
                lock_fd = os.open(
                    lock_name,
                    flags,
                    _PRIVATE_FILE_MODE,
                    dir_fd=lock_directory_fd,
                )
            except OSError as exc:
                raise ValidationError("训练视频分段锁文件无效或包含符号链接") from exc
            try:
                os.fchmod(lock_fd, _PRIVATE_FILE_MODE)
                with os.fdopen(lock_fd, "a+b", closefd=False) as lock_file:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                    try:
                        yield
                    finally:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        finally:
            os.close(lock_directory_fd)


def write_uploaded_segment(video, index, uploaded_file) -> tuple[Path, int, str]:
    digest = hashlib.sha256()
    written = 0
    temporary_name = f"{index:06d}.mp4.{uuid.uuid4().hex}.part"
    with _session_directory_fd(video, create=True) as (root, _, session_fd):
        segments_fd = _ensure_child_directory(session_fd, "segments")
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
            try:
                output_fd = os.open(
                    temporary_name,
                    flags,
                    _PRIVATE_FILE_MODE,
                    dir_fd=segments_fd,
                )
            except OSError as exc:
                raise ValidationError("训练视频临时分段文件无效") from exc
            try:
                os.fchmod(output_fd, _PRIVATE_FILE_MODE)
                with os.fdopen(output_fd, "wb", closefd=False) as output:
                    for chunk in uploaded_file.chunks():
                        written += len(chunk)
                        if written > settings.TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES:
                            raise ValidationError("训练视频分段过大")
                        digest.update(chunk)
                        output.write(chunk)
            except Exception:
                os.unlink(temporary_name, dir_fd=segments_fd)
                raise
            finally:
                os.close(output_fd)
        finally:
            os.close(segments_fd)
    temporary = root / _session_directory_name(video) / "segments" / temporary_name
    return temporary, written, digest.hexdigest()


def install_uploaded_segment(video: TrainingVideo, index: int, temporary: Path) -> Path:
    temporary = Path(temporary)
    destination_name = f"{index:06d}.mp4"
    with _session_directory_fd(video, create=False) as (root, _, session_fd):
        if session_fd is None:
            raise ValidationError("训练视频会话目录不存在")
        segments_fd = _ensure_child_directory(session_fd, "segments")
        try:
            if temporary.parent != root / _session_directory_name(video) / "segments":
                raise ValidationError("训练视频临时分段路径无效")
            metadata = os.stat(
                temporary.name,
                dir_fd=segments_fd,
                follow_symlinks=False,
            )
            if not stat.S_ISREG(metadata.st_mode):
                raise ValidationError("训练视频临时分段文件无效")
            os.rename(
                temporary.name,
                destination_name,
                src_dir_fd=segments_fd,
                dst_dir_fd=segments_fd,
            )
            os.chmod(
                destination_name,
                _PRIVATE_FILE_MODE,
                dir_fd=segments_fd,
                follow_symlinks=False,
            )
        finally:
            os.close(segments_fd)
    return root / _session_directory_name(video) / "segments" / destination_name


def unlink_segment_file(video: TrainingVideo, index: int) -> None:
    with _session_directory_fd(video, create=False) as (_, _, session_fd):
        if session_fd is None:
            return
        try:
            segments_fd = os.open("segments", _DIRECTORY_FLAGS, dir_fd=session_fd)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise ValidationError("训练视频分段目录无效或包含符号链接") from exc
        try:
            try:
                os.unlink(f"{index:06d}.mp4", dir_fd=segments_fd)
            except FileNotFoundError:
                pass
        finally:
            os.close(segments_fd)


def _remove_directory_contents(directory_fd: int) -> None:
    for name in os.listdir(directory_fd):
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=directory_fd)
            try:
                _remove_directory_contents(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        else:
            os.unlink(name, dir_fd=directory_fd)


def _remove_named_quarantine(root_fd: int, quarantine_fd: int, name: str) -> bool:
    try:
        directory_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=quarantine_fd)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ValidationError("训练视频隔离目录无效或包含符号链接") from exc
    try:
        _remove_directory_contents(directory_fd)
    finally:
        os.close(directory_fd)
    os.rmdir(name, dir_fd=quarantine_fd)
    return True


def quarantine_and_remove_session(video: TrainingVideo) -> None:
    root = _configured_staging_root()
    root_fd = _open_directory(root)
    quarantine_fd = None
    try:
        quarantine_fd = _ensure_child_directory(root_fd, QUARANTINE_DIRECTORY_NAME)
        name = _session_directory_name(video)
        _remove_named_quarantine(root_fd, quarantine_fd, name)
        try:
            metadata = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValidationError("训练视频会话目录无效或包含符号链接")
        os.rename(name, name, src_dir_fd=root_fd, dst_dir_fd=quarantine_fd)
        _remove_named_quarantine(root_fd, quarantine_fd, name)
    finally:
        if quarantine_fd is not None:
            os.close(quarantine_fd)
        os.close(root_fd)


def remove_orphan_session_directory(name: str) -> bool:
    if SESSION_DIRECTORY_PATTERN.fullmatch(name) is None:
        return False
    root = _configured_staging_root()
    root_fd = _open_directory(root)
    quarantine_fd = None
    try:
        quarantine_fd = _ensure_child_directory(root_fd, QUARANTINE_DIRECTORY_NAME)
        _remove_named_quarantine(root_fd, quarantine_fd, name)
        try:
            metadata = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValidationError("训练视频孤儿目录无效或包含符号链接")
        os.rename(name, name, src_dir_fd=root_fd, dst_dir_fd=quarantine_fd)
        return _remove_named_quarantine(root_fd, quarantine_fd, name)
    finally:
        if quarantine_fd is not None:
            os.close(quarantine_fd)
        os.close(root_fd)


def remove_quarantined_session_directory(name: str) -> bool:
    if SESSION_DIRECTORY_PATTERN.fullmatch(name) is None:
        return False
    root = _configured_staging_root()
    root_fd = _open_directory(root)
    quarantine_fd = None
    try:
        quarantine_fd = _ensure_child_directory(root_fd, QUARANTINE_DIRECTORY_NAME)
        return _remove_named_quarantine(root_fd, quarantine_fd, name)
    finally:
        if quarantine_fd is not None:
            os.close(quarantine_fd)
        os.close(root_fd)


def staging_directory_entries() -> tuple[Path, list[Path], list[Path]]:
    root = _configured_staging_root()
    sessions = []
    quarantined = []
    for path in root.iterdir():
        if path.name == QUARANTINE_DIRECTORY_NAME:
            _reject_existing_symlink(path, "训练视频隔离目录不能是符号链接")
            if path.is_dir():
                quarantined.extend(path.iterdir())
            continue
        sessions.append(path)
    return root, sessions, quarantined
