import errno
import json
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.training.pose_benchmark import (
    BenchmarkFailure,
    probe_video,
    read_versions,
    run_pose_smoke_benchmark,
    sha256_file,
)
from apps.training.pose_benchmark_resources import ResourceSnapshot
from apps.training.pose_inference import VideoKeypointExtraction


class FakeSampler:
    def __init__(self, peak):
        self.peak = peak

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _peak(*, available=800 * 1024**2, swap_free=3 * 1024**3):
    return ResourceSnapshot(
        process_rss_bytes=400 * 1024**2,
        system_memory_used_bytes=900 * 1024**2,
        memory_available_bytes=available,
        swap_used_bytes=100 * 1024**2,
        swap_free_bytes=swap_free,
    )


def _probe_payload():
    return subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1920,
                        "height": 1080,
                        "r_frame_rate": "30/1",
                        "avg_frame_rate": "8929/300",
                        "nb_frames": "8929",
                    },
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "300", "size": "384318737"},
            }
        ),
        stderr="",
    )


def test_motion_analysis_extra_has_one_opencv_provider_compatible_with_paddlex():
    pyproject_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    providers = [
        dependency
        for dependency in pyproject["project"]["optional-dependencies"]["motion-analysis"]
        if dependency.lower().startswith("opencv-")
    ]

    assert providers == ["opencv-contrib-python==4.10.0.84"]


def test_read_versions_reports_imported_cv2_runtime_version(monkeypatch):
    metadata_versions = {
        "paddlepaddle": "3.3.0",
        "paddlex": "3.7.2",
        "opencv-contrib-python": "9.9.9",
        "opencv-python-headless": "4.14.0.94",
    }
    monkeypatch.setattr(
        "apps.training.pose_benchmark.importlib.metadata.version",
        metadata_versions.__getitem__,
    )
    monkeypatch.setattr(
        "apps.training.pose_benchmark.importlib.import_module",
        lambda name: SimpleNamespace(__version__="4.10.0"),
    )
    monkeypatch.setattr(
        "apps.training.pose_benchmark.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="ffmpeg version 6.1.1\n",
            stderr="",
        ),
    )

    versions = read_versions()

    assert versions["opencv-contrib-python"] == "4.10.0"


def test_read_versions_rejects_cv2_without_runtime_version(monkeypatch):
    monkeypatch.setattr(
        "apps.training.pose_benchmark.importlib.metadata.version",
        lambda distribution: {
            "paddlepaddle": "3.3.0",
            "paddlex": "3.7.2",
            "opencv-python-headless": "4.14.0.94",
        }[distribution],
    )
    monkeypatch.setattr(
        "apps.training.pose_benchmark.importlib.import_module",
        lambda name: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "apps.training.pose_benchmark.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="ffmpeg version 6.1.1\n",
            stderr="",
        ),
    )

    with pytest.raises(BenchmarkFailure, match="OpenCV 运行时版本不可用"):
        read_versions()


def test_probe_video_preserves_nominal_and_average_rates(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")

    result = probe_video(
        video,
        ffprobe_path="ffprobe",
        runner=lambda *args, **kwargs: _probe_payload(),
    )

    assert result["nominal_frame_rate"] == "30/1"
    assert result["average_frame_rate"] == "8929/300"
    assert result["reported_frame_count"] == 8929


def test_runs_all_modes_with_one_model_and_writes_sanitized_reports(tmp_path):
    video = tmp_path / "patient-name-must-not-leak.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"
    summary = tmp_path / "report.txt"
    model = object()
    model_factory_calls = []
    sample_modes = []

    def model_factory():
        model_factory_calls.append(True)
        return model

    def extractor(path, *, sample_fps, model):
        assert path == video
        assert model is not None
        sample_modes.append(sample_fps)
        count = {5.0: 2, 10.0: 3, None: 5}[sample_fps]
        frames = [
            {"timestamp_ms": index * 100, "keypoints": {}}
            for index in range(count)
        ]
        return VideoKeypointExtraction(frames, 5, count, 30.0)

    result = run_pose_smoke_benchmark(
        video,
        report_path=report,
        summary_path=summary,
        expected_sha256=sha256_file(video),
        git_commit="abc1234",
        ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
        model_factory=model_factory,
        warm_up=lambda path, *, model: None,
        extractor=extractor,
        analyzer=lambda frames: {
            "total_count": len(frames),
            "standard_count": len(frames),
            "nonstandard_count": 0,
            "rep_details": [],
            "quality_flags": ["camera_angle_unverified"],
        },
        sampler_factory=lambda: FakeSampler(_peak()),
        version_reader=lambda: {"python": "3.12.3", "paddlepaddle": "3.3.0"},
        hardware_reader=lambda: {"cpu_model": "Fake CPU", "vcpu_count": 2},
    )

    assert len(model_factory_calls) == 1
    assert sample_modes == [5.0, 10.0, None]
    assert [item["status"] for item in result["modes"]] == ["completed"] * 3
    assert [item["inferred_frame_count"] for item in result["modes"]] == [2, 3, 5]
    serialized = report.read_text(encoding="utf-8")
    assert str(video) not in serialized
    assert video.name not in serialized
    assert "abc1234" in serialized
    assert result["manual_total_count"] == "not_provided"
    summary_text = summary.read_text(encoding="utf-8")
    assert "5 FPS" in summary_text
    assert str(video) not in summary_text
    assert video.name not in summary_text


@pytest.mark.parametrize(
    ("available", "swap_free", "reason"),
    [
        (200 * 1024**2, 3 * 1024**3, "memory_available_below_256_mib"),
        (800 * 1024**2, 400 * 1024**2, "swap_free_below_512_mib"),
    ],
)
def test_skips_all_frames_when_ten_fps_exhausts_safety_reserve(
    tmp_path,
    available,
    swap_free,
    reason,
):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    peaks = iter([_peak(), _peak(available=available, swap_free=swap_free)])
    modes = []

    result = run_pose_smoke_benchmark(
        video,
        report_path=tmp_path / "report.json",
        summary_path=tmp_path / "report.txt",
        expected_sha256=sha256_file(video),
        git_commit="abc1234",
        ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
        model_factory=lambda: object(),
        warm_up=lambda path, *, model: None,
        extractor=lambda path, *, sample_fps, model: (
            modes.append(sample_fps)
            or VideoKeypointExtraction(
                [{"timestamp_ms": 0, "keypoints": {}}], 1, 1, 30.0
            )
        ),
        analyzer=lambda frames: {
            "total_count": 0,
            "standard_count": 0,
            "nonstandard_count": 0,
            "rep_details": [],
            "quality_flags": [],
        },
        sampler_factory=lambda: FakeSampler(next(peaks)),
        version_reader=lambda: {},
        hardware_reader=lambda: {},
    )

    assert modes == [5.0, 10.0]
    assert result["status"] == "completed"
    assert result["modes"][2]["status"] == "skipped_for_resource_safety"
    assert result["modes"][2]["reason"] == reason


def test_hash_mismatch_writes_failed_report_before_model_load(tmp_path):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"

    with pytest.raises(BenchmarkFailure, match="SHA-256"):
        run_pose_smoke_benchmark(
            video,
            report_path=report,
            summary_path=tmp_path / "report.txt",
            expected_sha256="0" * 64,
            git_commit="abc1234",
            model_factory=lambda: pytest.fail("哈希失败后不得加载模型"),
        )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert str(video) not in json.dumps(payload, ensure_ascii=False)
    assert "private-video" not in json.dumps(payload, ensure_ascii=False)


def test_benchmark_rejects_report_and_summary_resolving_to_same_path(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "reports" / "report.json"
    summary = report.parent / "nested" / ".." / report.name

    with pytest.raises(BenchmarkFailure, match="报告与摘要不能使用同一路径"):
        run_pose_smoke_benchmark(
            video,
            report_path=report,
            summary_path=summary,
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
            model_factory=lambda: pytest.fail("路径冲突后不得加载模型"),
        )

    assert not report.exists()


def test_resource_failure_is_sanitized_and_stops_higher_modes(tmp_path):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"
    calls = []

    def extractor(path, *, sample_fps, model):
        calls.append(sample_fps)
        raise MemoryError("private /path/video.mp4")

    with pytest.raises(BenchmarkFailure, match="硬验收"):
        run_pose_smoke_benchmark(
            video,
            report_path=report,
            summary_path=tmp_path / "report.txt",
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
            ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
            model_factory=lambda: object(),
            warm_up=lambda path, *, model: None,
            extractor=extractor,
            analyzer=lambda frames: {},
            sampler_factory=lambda: FakeSampler(_peak()),
            version_reader=lambda: {},
            hardware_reader=lambda: {},
        )

    result = json.loads(report.read_text(encoding="utf-8"))
    assert calls == [5.0]
    assert result["status"] == "failed"
    assert result["modes"][0]["status"] == "failed"
    assert result["modes"][0]["error_type"] == "MemoryError"
    assert result["modes"][1]["status"] == "skipped_for_resource_safety"
    assert result["modes"][2]["status"] == "skipped_for_resource_safety"
    serialized = report.read_text(encoding="utf-8")
    assert "private /path" not in serialized
    assert str(video) not in serialized


@pytest.mark.parametrize(
    ("failure", "expected_summary", "expected_mode_statuses"),
    [
        (
            MemoryError("private /path/video.mp4"),
            "推理阶段发生资源错误",
            ["failed", "skipped_for_resource_safety", "skipped_for_resource_safety"],
        ),
        (
            OSError(errno.ENOMEM, "private /path/video.mp4"),
            "推理阶段发生资源错误",
            ["failed", "skipped_for_resource_safety", "skipped_for_resource_safety"],
        ),
        (
            OSError(errno.EIO, "private /path/video.mp4"),
            "推理阶段执行失败",
            ["failed"],
        ),
    ],
)
def test_only_memory_allocation_failures_use_resource_safety_flow(
    tmp_path,
    failure,
    expected_summary,
    expected_mode_statuses,
):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"
    calls = []

    def extractor(path, *, sample_fps, model):
        calls.append(sample_fps)
        raise failure

    with pytest.raises(BenchmarkFailure):
        run_pose_smoke_benchmark(
            video,
            report_path=report,
            summary_path=tmp_path / "report.txt",
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
            ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
            model_factory=lambda: object(),
            warm_up=lambda path, *, model: None,
            extractor=extractor,
            analyzer=lambda frames: {},
            sampler_factory=lambda: FakeSampler(_peak()),
            version_reader=lambda: {},
            hardware_reader=lambda: {},
        )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert calls == [5.0]
    assert [mode["status"] for mode in payload["modes"]] == expected_mode_statuses
    assert payload["modes"][0]["error_type"] == type(failure).__name__
    assert payload["modes"][0]["error_summary"] == expected_summary
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "private /path" not in serialized
    assert str(video) not in serialized


def test_non_resource_mode_failure_is_sanitized_and_marks_current_mode_failed(
    tmp_path,
):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"

    def extractor(path, *, sample_fps, model):
        raise ValueError("private /path/video.mp4")

    with pytest.raises(BenchmarkFailure, match="冒烟测试执行失败"):
        run_pose_smoke_benchmark(
            video,
            report_path=report,
            summary_path=tmp_path / "report.txt",
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
            ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
            model_factory=lambda: object(),
            warm_up=lambda path, *, model: None,
            extractor=extractor,
            analyzer=lambda frames: {},
            sampler_factory=lambda: FakeSampler(_peak()),
            version_reader=lambda: {},
            hardware_reader=lambda: {},
        )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["modes"][0]["status"] == "failed"
    assert payload["modes"][0]["failure_stage"] == "5fps_inference"
    assert payload["modes"][0]["error_type"] == "ValueError"
    assert payload["modes"][0]["error_summary"] == "推理阶段执行失败"
    assert "private /path" not in json.dumps(payload, ensure_ascii=False)
    assert str(video) not in json.dumps(payload, ensure_ascii=False)


def test_all_frames_resource_failure_does_not_fail_required_modes(tmp_path):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"
    calls = []

    def extractor(path, *, sample_fps, model):
        calls.append(sample_fps)
        if sample_fps is None:
            raise MemoryError("private /path/video.mp4")
        return VideoKeypointExtraction(
            [{"timestamp_ms": 0, "keypoints": {}}],
            1,
            1,
            30.0,
        )

    result = run_pose_smoke_benchmark(
        video,
        report_path=report,
        summary_path=tmp_path / "report.txt",
        expected_sha256=sha256_file(video),
        git_commit="abc1234",
        ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
        model_factory=lambda: object(),
        warm_up=lambda path, *, model: None,
        extractor=extractor,
        analyzer=lambda frames: {
            "total_count": 0,
            "standard_count": 0,
            "nonstandard_count": 0,
            "rep_details": [],
            "quality_flags": [],
        },
        sampler_factory=lambda: FakeSampler(_peak()),
        version_reader=lambda: {},
        hardware_reader=lambda: {},
    )

    assert calls == [5.0, 10.0, None]
    assert result["status"] == "completed"
    assert result["modes"][2]["status"] == "failed"
    assert "private /path" not in report.read_text(encoding="utf-8")


def test_summary_write_failure_leaves_failed_json_report_and_is_wrapped(tmp_path):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"
    summary_directory = tmp_path / "summary-target"
    summary_directory.mkdir()

    with pytest.raises(BenchmarkFailure, match="摘要写入失败") as raised:
        run_pose_smoke_benchmark(
            video,
            report_path=report,
            summary_path=summary_directory,
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
        )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failure"]["error_summary"] == "冒烟测试执行失败"
    assert isinstance(raised.value.__cause__, OSError)
    assert str(summary_directory) not in json.dumps(payload, ensure_ascii=False)


def test_json_report_write_failure_is_wrapped_as_benchmark_failure(tmp_path):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")
    report_directory = tmp_path / "report-target"
    report_directory.mkdir()

    with pytest.raises(BenchmarkFailure, match="报告写入失败") as raised:
        run_pose_smoke_benchmark(
            video,
            report_path=report_directory,
            summary_path=tmp_path / "report.txt",
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
        )

    assert isinstance(raised.value.__cause__, OSError)
