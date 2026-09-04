import errno
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .pose_benchmark_resources import ResourceSampler, read_linux_resource_snapshot
from .pose_inference import (
    PP_TINYPOSE_MODEL_NAME,
    create_pose_model,
    open_video_keypoint_stream,
    warm_up_pose_model,
)
from .shoulder_press_v2 import analyze_shoulder_press_keypoints_v2


MIB = 1024**2
MIN_MEMORY_AVAILABLE_BYTES = 256 * MIB
MIN_SWAP_FREE_BYTES = 512 * MIB
REPORT_FORMAT_VERSION = "2.0"


class BenchmarkFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class BenchmarkMode:
    name: str
    sample_fps: float | None


BENCHMARK_MODES = (
    BenchmarkMode("5fps", 5.0),
    BenchmarkMode("10fps", 10.0),
    BenchmarkMode("all_frames", None),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_video_unchecked(path, *, ffprobe_path, runner):
    completed = runner(
        [
            ffprobe_path,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(completed.stdout)
    streams = payload["streams"]
    video = next(item for item in streams if item.get("codec_type") == "video")
    audio = next(
        (item for item in streams if item.get("codec_type") == "audio"),
        None,
    )
    return {
        "sha256": sha256_file(path),
        "size_bytes": int(payload["format"]["size"]),
        "duration_seconds": float(payload["format"]["duration"]),
        "video_codec": str(video["codec_name"]),
        "audio_codec": None if audio is None else str(audio["codec_name"]),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "nominal_frame_rate": str(video.get("r_frame_rate") or ""),
        "average_frame_rate": str(video.get("avg_frame_rate") or ""),
        "reported_frame_count": (
            None if not video.get("nb_frames") else int(video["nb_frames"])
        ),
    }


def probe_video(
    path: Path,
    *,
    ffprobe_path: str = "/usr/bin/ffprobe",
    runner=subprocess.run,
) -> dict:
    try:
        return _probe_video_unchecked(path, ffprobe_path=ffprobe_path, runner=runner)
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        KeyError,
        StopIteration,
        TypeError,
        ValueError,
    ) as exc:
        raise BenchmarkFailure("视频探测失败") from exc


def read_versions():
    versions = {"python": platform.python_version()}
    for distribution in ("paddlepaddle", "paddlex"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "not_installed"
    try:
        cv2 = importlib.import_module("cv2")
    except (ImportError, OSError) as exc:
        raise BenchmarkFailure("OpenCV 运行时不可用") from exc
    opencv_version = getattr(cv2, "__version__", None)
    if not isinstance(opencv_version, str) or not opencv_version.strip():
        raise BenchmarkFailure("OpenCV 运行时版本不可用")
    versions["opencv-contrib-python"] = opencv_version.strip()
    completed = subprocess.run(
        ["/usr/bin/ffmpeg", "-version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    versions["ffmpeg"] = completed.stdout.splitlines()[0]
    return versions


def read_hardware():
    cpu_model = "unknown"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines():
            if line.startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    snapshot = read_linux_resource_snapshot()
    return {
        "cpu_model": cpu_model,
        "vcpu_count": os.cpu_count(),
        "physical_memory_bytes": (
            snapshot.system_memory_used_bytes + snapshot.memory_available_bytes
        ),
        "swap_total_bytes": snapshot.swap_used_bytes + snapshot.swap_free_bytes,
    }


def _atomic_write_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _write_json_report(report_path, report):
    _atomic_write_text(
        report_path,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _write_summary(summary_path, report):
    lines = [
        f"状态: {report['status']}",
        f"模型: {report['model']['name']} ({report['model']['device']})",
    ]
    for mode in report.get("modes", []):
        lines.append(
            f"{mode['label']}: {mode['status']}; "
            f"推理帧={mode.get('inferred_frame_count', '-')}; "
            f"总次数={mode.get('result', {}).get('total_count', '-')}; "
            f"人工误差={mode.get('count_error', '-')}"
        )
    lines.append(f"v2验收：{'通过' if report['acceptance']['passed'] else '失败'}")
    _atomic_write_text(summary_path, "\n".join(lines) + "\n")


def _write_report(report_path, summary_path, report):
    _write_json_report(report_path, report)
    _write_summary(summary_path, report)


def _failure_summary(stage, exc):
    if stage == "hash_validation" and isinstance(exc, BenchmarkFailure):
        return "视频 SHA-256 与预期不一致"
    if stage == "video_probe" and isinstance(exc, BenchmarkFailure):
        return "视频探测失败"
    if stage == "hard_acceptance" and isinstance(exc, BenchmarkFailure):
        return "v2 算法验收失败"
    return "冒烟测试执行失败"


def _mode_label(mode):
    if mode.sample_fps is None:
        return "全帧"
    return f"{int(mode.sample_fps)} FPS"


def _append_resource_skip(report, mode, reason):
    report["modes"].append(
        {
            "name": mode.name,
            "label": _mode_label(mode),
            "sample_fps": mode.sample_fps,
            "status": "skipped_for_resource_safety",
            "reason": reason,
        }
    )


def _v2_acceptance_failures(report: dict) -> list[str]:
    modes_by_name = {mode["name"]: mode for mode in report["modes"]}
    required_names = ("5fps", "10fps", "all_frames")
    if any(
        name not in modes_by_name or modes_by_name[name]["status"] != "completed"
        for name in required_names
    ):
        return ["required_mode_not_completed"]

    sampled_modes = [modes_by_name["5fps"], modes_by_name["10fps"]]
    all_frames = modes_by_name["all_frames"]
    failures = []
    if all_frames["result"]["total_count"] != report["manual_total_count"]:
        failures.append("all_frame_count_mismatch")
    if any(abs(mode["count_error"]) > 1 for mode in sampled_modes):
        failures.append("sampled_count_error_over_one")
    if all_frames["total_seconds"] > report["video"]["duration_seconds"] * 2:
        failures.append("all_frame_slower_than_two_times_duration")
    if all_frames["resource_peak"]["process_rss_bytes"] >= int(1.5 * 1024**3):
        failures.append("all_frame_rss_limit_exceeded")
    if all_frames["resource_peak"]["swap_used_bytes"] != 0:
        failures.append("swap_used")
    return failures


def run_pose_smoke_benchmark(
    video_path: Path,
    *,
    report_path: Path,
    summary_path: Path,
    expected_sha256: str,
    git_commit: str,
    manual_total_count: int,
    ffprobe_path="/usr/bin/ffprobe",
    ffprobe_runner=subprocess.run,
    model_factory=create_pose_model,
    warm_up=warm_up_pose_model,
    stream_factory=open_video_keypoint_stream,
    analyzer=analyze_shoulder_press_keypoints_v2,
    sampler_factory=ResourceSampler,
    version_reader=read_versions,
    hardware_reader=read_hardware,
    monotonic=time.monotonic,
) -> dict:
    video_path = Path(video_path)
    report_path = Path(report_path)
    summary_path = Path(summary_path)
    try:
        outputs_are_same = report_path.resolve() == summary_path.resolve()
    except OSError as exc:
        raise BenchmarkFailure("报告或摘要路径无法解析") from exc
    if outputs_are_same:
        raise BenchmarkFailure("报告与摘要不能使用同一路径")
    started_at = datetime.now(timezone.utc)
    report = {
        "report_format_version": REPORT_FORMAT_VERSION,
        "status": "running",
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "git_commit": git_commit,
        "versions": {},
        "hardware": {},
        "video": {},
        "model": {"name": PP_TINYPOSE_MODEL_NAME, "device": "cpu"},
        "manual_total_count": manual_total_count,
        "modes": [],
        "acceptance": {"passed": False, "failures": []},
    }
    stage = "hash_validation"

    def persist():
        _write_report(report_path, summary_path, report)

    try:
        actual_sha256 = sha256_file(video_path)
        if actual_sha256 != expected_sha256.lower():
            raise BenchmarkFailure("视频 SHA-256 与预期不一致")
        persist()

        stage = "video_probe"
        report["video"] = probe_video(
            video_path,
            ffprobe_path=ffprobe_path,
            runner=ffprobe_runner,
        )
        persist()

        stage = "version_read"
        report["versions"] = version_reader()
        persist()

        stage = "hardware_read"
        report["hardware"] = hardware_reader()
        persist()

        stage = "model_load"
        model_started = monotonic()
        model = model_factory()
        report["model"]["load_seconds"] = monotonic() - model_started
        persist()

        stage = "model_warm_up"
        warm_started = monotonic()
        warm_up(video_path, model=model)
        report["model"]["warm_up_seconds"] = monotonic() - warm_started
        persist()

        resource_abort = False
        for mode in BENCHMARK_MODES:
            if resource_abort:
                _append_resource_skip(report, mode, "prior_resource_failure")
                persist()
                continue

            if mode.sample_fps is None and report["modes"]:
                previous_peak = report["modes"][-1].get("resource_peak") or {}
                if (
                    previous_peak.get("memory_available_bytes", 0)
                    < MIN_MEMORY_AVAILABLE_BYTES
                ):
                    _append_resource_skip(
                        report,
                        mode,
                        "memory_available_below_256_mib",
                    )
                    persist()
                    continue
                if previous_peak.get("swap_free_bytes", 0) < MIN_SWAP_FREE_BYTES:
                    _append_resource_skip(
                        report,
                        mode,
                        "swap_free_below_512_mib",
                    )
                    persist()
                    continue

            mode_report = {
                "name": mode.name,
                "label": _mode_label(mode),
                "sample_fps": mode.sample_fps,
                "status": "running",
            }
            report["modes"].append(mode_report)
            persist()

            stage = f"{mode.name}_inference"
            stream = None
            sampler = None
            try:
                with sampler_factory() as sampler:
                    with stream_factory(
                        video_path,
                        sample_fps=mode.sample_fps,
                        model=model,
                    ) as stream:
                        mode_started = monotonic()
                        result = analyzer(stream)
                        total_seconds = monotonic() - mode_started
                mode_report.update(
                    {
                        "status": "completed",
                        "decoded_frame_count": stream.decoded_frame_count,
                        "inferred_frame_count": stream.inferred_frame_count,
                        "source_fps": stream.source_fps,
                        "inference_seconds": stream.inference_seconds,
                        "total_seconds": total_seconds,
                        "average_inference_ms_per_frame": (
                            stream.inference_seconds
                            * 1000
                            / stream.inferred_frame_count
                        ),
                        "count_error": result["total_count"] - manual_total_count,
                        "resource_peak": asdict(sampler.peak),
                        "result": result,
                    }
                )
            except BaseException as exc:
                is_resource_failure = isinstance(exc, MemoryError) or (
                    isinstance(exc, OSError) and exc.errno == errno.ENOMEM
                )
                mode_report.update(
                    {
                        "status": "failed",
                        "failure_stage": stage,
                        "error_type": type(exc).__name__,
                        "error_summary": (
                            "推理阶段发生资源错误"
                            if is_resource_failure
                            else "推理阶段执行失败"
                        ),
                        "resource_peak": (
                            None
                            if sampler is None or sampler.peak is None
                            else asdict(sampler.peak)
                        ),
                    }
                )
                if is_resource_failure:
                    resource_abort = True
                else:
                    raise
            finally:
                if stream is not None:
                    del stream
                gc.collect()
                persist()

        report["acceptance"]["failures"] = _v2_acceptance_failures(report)
        if report["acceptance"]["failures"]:
            stage = "hard_acceptance"
            raise BenchmarkFailure("v2 算法验收失败")

        report["acceptance"]["passed"] = True
        report["status"] = "completed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        persist()
        return report
    except BaseException as exc:
        if stage.endswith("_inference"):
            report["acceptance"]["failures"] = _v2_acceptance_failures(report)
        report["status"] = "failed"
        report["failure"] = {
            "stage": stage,
            "error_type": type(exc).__name__,
            "error_summary": _failure_summary(stage, exc),
        }
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        try:
            _write_json_report(report_path, report)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as write_exc:
            raise BenchmarkFailure("冒烟测试报告写入失败") from write_exc
        try:
            _write_summary(summary_path, report)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as write_exc:
            raise BenchmarkFailure("冒烟测试摘要写入失败") from write_exc
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise BenchmarkFailure(report["failure"]["error_summary"]) from exc
