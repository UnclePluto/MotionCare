import errno
import json
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.training import pose_benchmark
from apps.training.pose_benchmark import (
    BenchmarkFailure,
    probe_video,
    read_versions,
    run_pose_smoke_benchmark,
    sha256_file,
)
from apps.training.pose_benchmark_resources import ResourceSnapshot


class FakeSampler:
    def __init__(self, peak):
        self.peak = peak

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeStream:
    def __init__(self, frames, *, source_fps=30.0):
        self.frames = frames
        self.source_fps = source_fps
        self.decoded_frame_count = len(frames)
        self.inferred_frame_count = len(frames)
        self.inference_seconds = 0.1

    def __iter__(self):
        return iter(self.frames)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def _peak(
    *,
    available=800 * 1024**2,
    swap_free=3 * 1024**3,
    swap_used=0,
    process_rss=400 * 1024**2,
):
    return ResourceSnapshot(
        process_rss_bytes=process_rss,
        system_memory_used_bytes=900 * 1024**2,
        memory_available_bytes=available,
        swap_used_bytes=swap_used,
        swap_free_bytes=swap_free,
    )


def _benchmark_result(total_count):
    return {
        "total_count": total_count,
        "standard_count": total_count,
        "nonstandard_count": 0,
        "rep_details": [],
        "quality_flags": ["camera_angle_unverified"],
    }


def _valid_acceptance_report():
    return {
        "manual_total_count": 90,
        "video": {"duration_seconds": 300.0},
        "modes": [
            {
                "name": "all_frames",
                "status": "completed",
                "sample_fps": None,
                "decoded_frame_count": 8929,
                "inferred_frame_count": 8929,
                "count_error": 0,
                "total_seconds": 445.0,
                "result": {"total_count": 90},
                "resource_peak": {
                    "process_rss_bytes": 700 * 1024**2,
                    "swap_used_bytes": 0,
                },
            },
        ],
    }


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


def test_v2_benchmark_records_manual_count_and_passes_all_gates(tmp_path):
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

    def stream_factory(path, *, sample_fps, model):
        assert path == video
        assert model is not None
        sample_modes.append(sample_fps)
        frames = [
            {"timestamp_ms": index * 100, "keypoints": {}}
            for index in range(3)
        ]
        return FakeStream(frames)

    result = run_pose_smoke_benchmark(
        video,
        report_path=report,
        summary_path=summary,
        expected_sha256=sha256_file(video),
        git_commit="abc1234",
        manual_total_count=90,
        ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
        model_factory=model_factory,
        warm_up=lambda path, *, model: None,
        stream_factory=stream_factory,
        analyzer=lambda frames: (list(frames), _benchmark_result(90))[1],
        sampler_factory=lambda: FakeSampler(_peak(swap_used=0)),
        version_reader=lambda: {"python": "3.12.3", "paddlepaddle": "3.3.0"},
        hardware_reader=lambda: {"cpu_model": "Fake CPU", "vcpu_count": 2},
    )

    assert len(model_factory_calls) == 1
    assert sample_modes == [None]
    assert [item["status"] for item in result["modes"]] == ["completed"]
    assert [item["inferred_frame_count"] for item in result["modes"]] == [3]
    assert result["report_format_version"] == "2.0"
    assert result["manual_total_count"] == 90
    assert [mode["count_error"] for mode in result["modes"]] == [0]
    assert result["acceptance"] == {"passed": True, "failures": []}
    serialized = report.read_text(encoding="utf-8")
    assert str(video) not in serialized
    assert video.name not in serialized
    assert "abc1234" in serialized
    summary_text = summary.read_text(encoding="utf-8")
    assert "全帧" in summary_text
    assert "5 FPS" not in summary_text
    assert "10 FPS" not in summary_text
    assert "人工误差=0" in summary_text
    assert "v2验收：通过" in summary_text
    assert str(video) not in summary_text
    assert video.name not in summary_text


@pytest.mark.parametrize(
    ("case", "expected_failure"),
    [
        ("full_frame_count_not_90", "all_frame_count_mismatch"),
        ("all_frame_over_600_seconds", "all_frame_over_600_seconds"),
        ("rss_at_or_over_1_5_gib", "all_frame_rss_limit_exceeded"),
        ("swap_used_nonzero", "swap_used"),
        ("all_frame_not_completed", "required_mode_not_completed"),
    ],
)
def test_v2_acceptance_rejects_each_failed_gate(case, expected_failure):
    report = _valid_acceptance_report()
    if case == "full_frame_count_not_90":
        report["modes"][0]["result"]["total_count"] = 89
        report["modes"][0]["count_error"] = -1
    elif case == "all_frame_over_600_seconds":
        report["modes"][0]["total_seconds"] = 600.0001
    elif case == "rss_at_or_over_1_5_gib":
        report["modes"][0]["resource_peak"]["process_rss_bytes"] = int(
            1.5 * 1024**3
        )
    elif case == "swap_used_nonzero":
        report["modes"][0]["resource_peak"]["swap_used_bytes"] = 4096
    else:
        report["modes"][0] = {"name": "all_frames", "status": "failed"}

    assert pose_benchmark._v2_acceptance_failures(report) == [expected_failure]


def test_v2_acceptance_allows_inclusive_time_and_exclusive_rss_boundaries():
    report = _valid_acceptance_report()
    report["modes"][0]["total_seconds"] = 600.0
    report["modes"][0]["resource_peak"]["process_rss_bytes"] = (
        int(1.5 * 1024**3) - 1
    )

    assert pose_benchmark._v2_acceptance_failures(report) == []


def test_v2_acceptance_rejects_extra_sampled_mode():
    report = _valid_acceptance_report()
    report["modes"].append(
        {
            "name": "5fps",
            "status": "completed",
            "count_error": 0,
            "result": {"total_count": 90},
        }
    )

    assert pose_benchmark._v2_acceptance_failures(report) == [
        "invalid_acceptance_report"
    ]


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("sample_fps", "missing"),
        ("sample_fps", 5.0),
        ("decoded_frame_count", "missing"),
        ("decoded_frame_count", True),
        ("decoded_frame_count", -1),
        ("inferred_frame_count", "missing"),
        ("inferred_frame_count", True),
        ("inferred_frame_count", -1),
    ],
)
def test_v2_acceptance_rejects_non_full_frame_evidence(field, invalid_value):
    report = _valid_acceptance_report()
    if invalid_value == "missing":
        report["modes"][0].pop(field)
    else:
        report["modes"][0][field] = invalid_value

    assert pose_benchmark._v2_acceptance_failures(report) == [
        "invalid_acceptance_report"
    ]


def test_v2_acceptance_rejects_dropped_decoded_frames():
    report = _valid_acceptance_report()
    report["modes"][0]["inferred_frame_count"] = 8928

    assert pose_benchmark._v2_acceptance_failures(report) == [
        "invalid_acceptance_report"
    ]


def test_v2_acceptance_requires_manual_truth_of_90():
    report = _valid_acceptance_report()
    report["manual_total_count"] = 89
    report["modes"][0]["result"]["total_count"] = 89

    assert pose_benchmark._v2_acceptance_failures(report) == [
        "invalid_acceptance_report"
    ]


def test_v2_acceptance_requires_all_frame_result():
    report = _valid_acceptance_report()
    report["modes"][0].pop("result")

    assert pose_benchmark._v2_acceptance_failures(report) == [
        "invalid_acceptance_report"
    ]


@pytest.mark.parametrize("invalid_total", [True, -1])
def test_v2_acceptance_rejects_bool_or_negative_all_frame_total(invalid_total):
    report = _valid_acceptance_report()
    report["modes"][0]["result"]["total_count"] = invalid_total

    assert pose_benchmark._v2_acceptance_failures(report) == [
        "invalid_acceptance_report"
    ]


def test_v2_acceptance_rejects_count_error_inconsistent_with_total():
    report = _valid_acceptance_report()
    report["modes"][0]["count_error"] = 1

    assert pose_benchmark._v2_acceptance_failures(report) == [
        "invalid_acceptance_report"
    ]


@pytest.mark.parametrize(
    "case",
    [
        "missing_status",
        "missing_result",
        "missing_resource_peak",
        "wrong_modes_container",
        "wrong_result_container",
        "wrong_resource_peak_container",
        "bool_count_error",
        "string_duration",
        "incomplete_mode_and_bad_duration",
    ],
)
def test_v2_acceptance_rejects_malformed_schema_without_raising(case):
    report = _valid_acceptance_report()
    expected = ["invalid_acceptance_report"]
    if case == "missing_status":
        report["modes"][0].pop("status")
        expected.append("required_mode_not_completed")
    elif case == "missing_result":
        report["modes"][0].pop("result")
    elif case == "missing_resource_peak":
        report["modes"][0].pop("resource_peak")
    elif case == "wrong_modes_container":
        report["modes"] = {}
    elif case == "wrong_result_container":
        report["modes"][0]["result"] = []
    elif case == "wrong_resource_peak_container":
        report["modes"][0]["resource_peak"] = []
    elif case == "bool_count_error":
        report["modes"][0]["count_error"] = True
    elif case == "incomplete_mode_and_bad_duration":
        report["modes"][0] = {"name": "all_frames", "status": "failed"}
        report["video"]["duration_seconds"] = float("nan")
        expected.append("required_mode_not_completed")
    else:
        report["video"]["duration_seconds"] = "300"

    assert pose_benchmark._v2_acceptance_failures(report) == expected


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "field",
    [
        "manual_total_count",
        "duration_seconds",
        "count_error",
        "total_count",
        "total_seconds",
        "process_rss_bytes",
        "swap_used_bytes",
    ],
)
def test_v2_acceptance_rejects_non_finite_numbers_without_fail_open(
    field,
    non_finite,
):
    report = _valid_acceptance_report()
    if field == "manual_total_count":
        report[field] = non_finite
    elif field == "duration_seconds":
        report["video"][field] = non_finite
    elif field == "count_error":
        report["modes"][0][field] = non_finite
    elif field == "total_count":
        report["modes"][0]["result"][field] = non_finite
    elif field == "total_seconds":
        report["modes"][0][field] = non_finite
    else:
        report["modes"][0]["resource_peak"][field] = non_finite

    assert pose_benchmark._v2_acceptance_failures(report) == [
        "invalid_acceptance_report"
    ]


def test_v2_acceptance_keeps_stable_order_and_collects_safe_failures():
    report = _valid_acceptance_report()
    report["modes"][0]["count_error"] = True
    report["modes"][0]["result"]["total_count"] = 89
    report["modes"][0]["total_seconds"] = 601.0
    report["modes"][0]["resource_peak"] = {
        "process_rss_bytes": int(1.5 * 1024**3),
        "swap_used_bytes": 4096,
    }

    assert pose_benchmark._v2_acceptance_failures(report) == [
        "invalid_acceptance_report",
        "all_frame_count_mismatch",
        "all_frame_over_600_seconds",
        "all_frame_rss_limit_exceeded",
        "swap_used",
    ]


def test_benchmark_persists_sanitized_report_before_v2_acceptance_failure(tmp_path):
    video = tmp_path / "private-patient-video.mp4"
    video.write_bytes(b"video")
    report_path = tmp_path / "report.json"
    def stream_factory(path, *, sample_fps, model):
        return FakeStream([{"timestamp_ms": 0, "keypoints": {}}])

    def analyzer(frames):
        list(frames)
        return _benchmark_result(89)

    with pytest.raises(BenchmarkFailure, match="v2 算法验收失败"):
        run_pose_smoke_benchmark(
            video,
            report_path=report_path,
            summary_path=tmp_path / "report.txt",
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
            manual_total_count=90,
            ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
            model_factory=lambda: object(),
            warm_up=lambda path, *, model: None,
            stream_factory=stream_factory,
            analyzer=analyzer,
            sampler_factory=lambda: FakeSampler(_peak(swap_used=0)),
            version_reader=lambda: {},
            hardware_reader=lambda: {},
        )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["acceptance"] == {
        "passed": False,
        "failures": ["all_frame_count_mismatch"],
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(video) not in serialized
    assert video.name not in serialized


@pytest.mark.parametrize(
    "manual_total_count",
    [0, -1, 89, 91, True, 1.0, "private-manual-value"],
)
def test_runner_rejects_manual_count_other_than_90_and_persists_sanitized_reports(
    tmp_path,
    manual_total_count,
):
    video = tmp_path / "private-patient-video.mp4"
    video.write_bytes(b"video")
    report_path = tmp_path / "report.json"
    summary_path = tmp_path / "report.txt"

    with pytest.raises(BenchmarkFailure, match="人工真值必须为 90"):
        run_pose_smoke_benchmark(
            video,
            report_path=report_path,
            summary_path=summary_path,
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
            manual_total_count=manual_total_count,
            ffprobe_runner=lambda *args, **kwargs: pytest.fail(
                "非法人工真值不得进入视频探测"
            ),
        )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["manual_total_count"] is None
    assert payload["acceptance"]["failures"] == ["invalid_acceptance_report"]
    assert payload["failure"]["stage"] == "input_validation"
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(video) not in serialized
    assert video.name not in serialized
    assert "private-manual-value" not in serialized
    summary = summary_path.read_text(encoding="utf-8")
    assert "状态: failed" in summary
    assert "v2验收：失败" in summary
    assert str(video) not in summary


def test_invalid_acceptance_data_still_persists_final_json_and_summary(tmp_path):
    video = tmp_path / "private-patient-video.mp4"
    video.write_bytes(b"video")
    report_path = tmp_path / "report.json"
    summary_path = tmp_path / "report.txt"
    peak = _peak(process_rss=None)

    with pytest.raises(BenchmarkFailure, match="v2 算法验收失败"):
        run_pose_smoke_benchmark(
            video,
            report_path=report_path,
            summary_path=summary_path,
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
            manual_total_count=90,
            ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
            model_factory=lambda: object(),
            warm_up=lambda path, *, model: None,
            stream_factory=lambda path, *, sample_fps, model: FakeStream(
                [{"timestamp_ms": 0, "keypoints": {}}]
            ),
            analyzer=lambda frames: (list(frames), _benchmark_result(90))[1],
            sampler_factory=lambda: FakeSampler(peak),
            version_reader=lambda: {},
            hardware_reader=lambda: {},
        )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["acceptance"]["failures"] == ["invalid_acceptance_report"]
    assert payload["failure"]["stage"] == "hard_acceptance"
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(video) not in serialized
    assert video.name not in serialized
    summary = summary_path.read_text(encoding="utf-8")
    assert "状态: failed" in summary
    assert "v2验收：失败" in summary
    assert str(video) not in summary


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
            manual_total_count=90,
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
            manual_total_count=90,
            model_factory=lambda: pytest.fail("路径冲突后不得加载模型"),
        )

    assert not report.exists()


@pytest.mark.parametrize(
    ("failure", "expected_summary"),
    [
        (
            MemoryError("private /path/video.mp4"),
            "推理阶段发生资源错误",
        ),
        (
            OSError(errno.ENOMEM, "private /path/video.mp4"),
            "推理阶段发生资源错误",
        ),
        (
            OSError(errno.EIO, "private /path/video.mp4"),
            "推理阶段执行失败",
        ),
    ],
)
def test_only_memory_allocation_failures_use_resource_safety_flow(
    tmp_path,
    failure,
    expected_summary,
):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"
    calls = []

    def stream_factory(path, *, sample_fps, model):
        calls.append(sample_fps)
        raise failure

    with pytest.raises(BenchmarkFailure):
        run_pose_smoke_benchmark(
            video,
            report_path=report,
            summary_path=tmp_path / "report.txt",
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
            manual_total_count=90,
            ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
            model_factory=lambda: object(),
            warm_up=lambda path, *, model: None,
            stream_factory=stream_factory,
            analyzer=lambda frames: {},
            sampler_factory=lambda: FakeSampler(_peak()),
            version_reader=lambda: {},
            hardware_reader=lambda: {},
        )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert calls == [None]
    assert [mode["status"] for mode in payload["modes"]] == ["failed"]
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

    def stream_factory(path, *, sample_fps, model):
        raise ValueError("private /path/video.mp4")

    with pytest.raises(BenchmarkFailure, match="冒烟测试执行失败"):
        run_pose_smoke_benchmark(
            video,
            report_path=report,
            summary_path=tmp_path / "report.txt",
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
            manual_total_count=90,
            ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
            model_factory=lambda: object(),
            warm_up=lambda path, *, model: None,
            stream_factory=stream_factory,
            analyzer=lambda frames: {},
            sampler_factory=lambda: FakeSampler(_peak()),
            version_reader=lambda: {},
            hardware_reader=lambda: {},
        )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["modes"][0]["status"] == "failed"
    assert payload["modes"][0]["failure_stage"] == "all_frames_inference"
    assert payload["modes"][0]["error_type"] == "ValueError"
    assert payload["modes"][0]["error_summary"] == "推理阶段执行失败"
    assert payload["acceptance"]["failures"] == ["required_mode_not_completed"]
    assert "private /path" not in json.dumps(payload, ensure_ascii=False)
    assert str(video) not in json.dumps(payload, ensure_ascii=False)


def test_all_frames_resource_failure_fails_v2_acceptance(tmp_path):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"
    calls = []

    def stream_factory(path, *, sample_fps, model):
        calls.append(sample_fps)
        if sample_fps is None:
            raise MemoryError("private /path/video.mp4")
        return FakeStream([{"timestamp_ms": 0, "keypoints": {}}])

    with pytest.raises(BenchmarkFailure, match="v2 算法验收失败"):
        run_pose_smoke_benchmark(
            video,
            report_path=report,
            summary_path=tmp_path / "report.txt",
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
            manual_total_count=90,
            ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
            model_factory=lambda: object(),
            warm_up=lambda path, *, model: None,
            stream_factory=stream_factory,
            analyzer=lambda frames: (list(frames), _benchmark_result(1))[1],
            sampler_factory=lambda: FakeSampler(_peak()),
            version_reader=lambda: {},
            hardware_reader=lambda: {},
        )

    assert calls == [None]
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["modes"][0]["status"] == "failed"
    assert result["acceptance"]["failures"] == ["required_mode_not_completed"]
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
            manual_total_count=90,
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
            manual_total_count=90,
        )

    assert isinstance(raised.value.__cause__, OSError)
