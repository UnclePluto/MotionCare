import fcntl
import hashlib
import uuid
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

from .models import TrainingVideo


class SegmentConflict(Exception):
    pass


class SessionConflict(Exception):
    pass


def session_root(video: TrainingVideo) -> Path:
    root = Path(settings.TRAINING_VIDEO_STAGING_ROOT).resolve()
    candidate = (root / video.client_session_id.hex).resolve()
    if not candidate.is_relative_to(root):
        raise ValidationError("训练视频临时目录无效")
    return candidate


def segment_path(video: TrainingVideo, index: int) -> Path:
    root = session_root(video)
    candidate = (root / "segments" / f"{index:06d}.mp4").resolve()
    if not candidate.is_relative_to(root):
        raise ValidationError("训练视频分段路径无效")
    return candidate


@contextmanager
def segment_install_lock(video: TrainingVideo, index: int):
    root = session_root(video)
    lock_directory = (root / "locks").resolve()
    lock_path = (lock_directory / f"{index:06d}.lock").resolve()
    if not lock_path.is_relative_to(root):
        raise ValidationError("训练视频分段锁路径无效")
    lock_directory.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def write_uploaded_segment(video, index, uploaded_file) -> tuple[Path, int, str]:
    destination = segment_path(video, index)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f".mp4.{uuid.uuid4().hex}.part")
    digest = hashlib.sha256()
    written = 0
    try:
        with temporary.open("xb") as output:
            for chunk in uploaded_file.chunks():
                written += len(chunk)
                if written > settings.TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES:
                    raise ValidationError("训练视频分段过大")
                digest.update(chunk)
                output.write(chunk)
        return temporary, written, digest.hexdigest()
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
