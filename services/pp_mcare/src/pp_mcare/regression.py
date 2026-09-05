from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import re
import secrets
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import psutil
from motion_analysis_contract import ClaimedJob, MotionCounts, PROTOCOL_VERSION

from .media import SourceVideoMetadata, probe_source_video
from .pipeline import run_local_pipeline
from .pose_inference import PP_TINYPOSE_MODEL_NAME
from .subject_tracker import SUBJECT_TRACKER_VERSION


EXPECTED_VIDEO_SHA256 = "f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd"
EXPECTED_DECODED_FRAME_COUNT = 8_929
EXPECTED_MANUAL_TOTAL_COUNT = 90
REPORT_FORMAT_VERSION = "3.0"
MAX_TOTAL_SECONDS = 600.0
MAX_PROCESS_RSS_BYTES = int(1.5 * 1024**3)
_CLOCK = time.monotonic
_COMMIT_PATTERN = re.compile(r"[a-f0-9]{7,40}\Z")


class RegressionFailure(RuntimeError):
    """真实样本回归未满足固定验收契约。"""


def _implementation_commit() -> str:
    value = os.environ.get("PP_MCARE_IMPLEMENTATION_COMMIT", "")
    return value if _COMMIT_PATTERN.fullmatch(value) else "unknown"


@dataclass(frozen=True)
class ResourceSnapshot:
    process_rss_bytes: int
    system_memory_used_bytes: int
    memory_available_bytes: int
    swap_used_bytes: int
    swap_free_bytes: int


def read_resource_snapshot() -> ResourceSnapshot:
    process = psutil.Process()
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return ResourceSnapshot(
        process_rss_bytes=int(process.memory_info().rss),
        system_memory_used_bytes=int(memory.used),
        memory_available_bytes=int(memory.available),
        swap_used_bytes=int(swap.used),
        swap_free_bytes=int(swap.free),
    )


class ResourceSampler:
    def __init__(self, *, reader=read_resource_snapshot, interval_seconds: float = 0.5):
        self._reader = reader
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
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
            )
        return current

    def _sample_until_stopped(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            self.sample_once()

    def __enter__(self) -> ResourceSampler:
        self.sample_once()
        self._thread = threading.Thread(target=self._sample_until_stopped, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_seconds * 2))
        self.sample_once()


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
        "st_nlink",
        "st_uid",
        "st_gid",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    return all(getattr(before, field) == getattr(after, field) for field in fields)


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
    try:
        parent = path.parent
        if parent.resolve(strict=True) != parent or not parent.is_dir():
            raise RegressionFailure("报告路径无效")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        parent_fd = os.open(parent, flags)
        try:
            existing = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(existing.st_mode):
                raise RegressionFailure("报告路径无效")
        return path, parent_fd
    except RegressionFailure:
        raise
    except OSError as exc:
        raise RegressionFailure("报告路径无效") from exc


def _atomic_write_report(path: Path, report: dict[str, object]) -> None:
    path, parent_fd = _validated_report_path(path)
    temporary_name = f".{path.name}.{secrets.token_hex(12)}"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        content = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            descriptor = None
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        try:
            existing = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(existing.st_mode):
                raise RegressionFailure("报告路径无效")
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(parent_fd)
    except RegressionFailure:
        raise
    except OSError as exc:
        raise RegressionFailure("报告写入失败") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
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
            "action_source_key": "motion-resistance-shoulder-press",
            "algorithm_version": PP_TINYPOSE_MODEL_NAME,
            "rule_version": "shoulder-press-v2",
            "parameter_version": "shoulder-press-v2-defaults",
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
    elif total_seconds > MAX_TOTAL_SECONDS:
        failures.append("all_frame_over_600_seconds")
    peak = mode.get("resource_peak")
    if not isinstance(peak, dict):
        failures.append("invalid_resource_peak")
    else:
        rss = peak.get("process_rss_bytes")
        swap = peak.get("swap_used_bytes")
        if isinstance(rss, bool) or not isinstance(rss, int) or rss < 0:
            failures.append("invalid_process_rss")
        elif rss >= MAX_PROCESS_RSS_BYTES:
            failures.append("all_frame_rss_limit_exceeded")
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
    _validated_path, report_parent_fd = _validated_report_path(report_file)
    os.close(report_parent_fd)
    if type(manual_total_count) is not int or manual_total_count != EXPECTED_MANUAL_TOTAL_COUNT:
        raise RegressionFailure("人工真值必须为 90")
    try:
        video_identity = video.lstat()
    except OSError as exc:
        raise RegressionFailure("视频路径无效") from exc
    if not stat.S_ISREG(video_identity.st_mode) or stat.S_ISLNK(video_identity.st_mode):
        raise RegressionFailure("视频路径无效")

    now = datetime.now(timezone.utc).isoformat()
    report: dict[str, object] = {
        "report_format_version": REPORT_FORMAT_VERSION,
        "status": "running",
        "started_at": now,
        "finished_at": None,
        "git_commit": _implementation_commit(),
        "versions": {},
        "hardware": {},
        "video": {},
        "model": {"name": PP_TINYPOSE_MODEL_NAME, "device": "cpu"},
        "manual_total_count": manual_total_count,
        "modes": [],
        "acceptance": {"passed": False, "failures": []},
    }
    stage = "hash_validation"
    try:
        actual_sha256 = sha256_file(video)
        if actual_sha256 != EXPECTED_VIDEO_SHA256:
            report["acceptance"] = {"passed": False, "failures": ["video_sha256_mismatch"]}
            raise RegressionFailure("视频 SHA-256 与固定样本不一致")
        if not _same_file_identity(video_identity, video.lstat()):
            raise RegressionFailure("视频在校验期间发生变化")

        stage = "video_probe"
        source = probe_source_video(video)
        report["video"] = _video_metadata(
            source,
            sha256=actual_sha256,
            size_bytes=video_identity.st_size,
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
                    _local_job(size_bytes=video_identity.st_size, object_hash=actual_sha256),
                    video,
                    output_path,
                    lambda _stage: None,
                    source_metadata=source,
                )
            total_seconds = _CLOCK() - started
        if sampler.peak is None:
            raise RegressionFailure("资源采样没有结果")
        if not _same_file_identity(video_identity, video.lstat()):
            raise RegressionFailure("视频在分析期间发生变化")
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
            "resource_peak": asdict(sampler.peak),
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
