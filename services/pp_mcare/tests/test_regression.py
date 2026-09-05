from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from motion_analysis_contract import MotionCounts

from pp_mcare import regression
from pp_mcare.media import SourceVideoMetadata, VideoMetadata
from pp_mcare.cli import main
from pp_mcare.regression import (
    EXPECTED_DECODED_FRAME_COUNT,
    RegressionFailure,
    ResourceSampler,
    ResourceSnapshot,
    read_resource_snapshot,
    run_regression,
)


def test_regression_cli_rejects_manual_count_other_than_90(capsys, tmp_path):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")

    exit_code = main(
        [
            "regression",
            "--video",
            str(video),
            "--manual-total-count",
            "89",
            "--report",
            str(tmp_path / "report.json"),
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "manual-total-count" in captured.err
    assert str(video) not in captured.err


def _source_metadata(*, frame_count=8_929):
    return SourceVideoMetadata(
        width=1920,
        height=1080,
        fps=8_929 / 300,
        frame_count=frame_count,
        duration_seconds=300.0,
        codec_name="hevc",
    )


def _pipeline_result(**changes):
    result_payload = {
        "total_count": 90,
        "standard_count": 85,
        "nonstandard_count": 5,
        "left_event_count": 89,
        "right_event_count": 90,
        "processed_frames": 8_900,
        "quality_flags": ["camera_angle_unverified"],
    }
    values = {
        "counts": MotionCounts(90, 85, 5),
        "result_payload": result_payload,
        "decoded_frame_count": 8_929,
        "inferred_frame_count": 8_929,
        "encoded_frame_count": 8_929,
        "inference_seconds": 120.5,
        "encoding_seconds": 30.25,
        "tracking_summary": {"subject_coverage_ratio": 0.99},
        "media_metadata": VideoMetadata(
            width=1920,
            height=1080,
            fps=8_929 / 300,
            frame_count=8_929,
            duration_seconds=300.0,
            codec_name="h264",
            pixel_format="yuv420p",
            has_audio=False,
            faststart=True,
        ),
    }
    values.update(changes)
    return SimpleNamespace(
        **values,
        result_payload_json=lambda: dict(values["result_payload"]),
        tracking_summary_json=lambda: dict(values["tracking_summary"]),
    )


class _FakeSampler:
    def __init__(self):
        self.peak = ResourceSnapshot(
            process_rss_bytes=900_000_000,
            system_memory_used_bytes=1_000_000_000,
            memory_available_bytes=700_000_000,
            swap_used_bytes=0,
            swap_free_bytes=4_000_000_000,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def _configure_success(monkeypatch, video, *, result=None, frame_count=8_929):
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    monkeypatch.setattr(regression, "EXPECTED_VIDEO_SHA256", digest)
    monkeypatch.setattr(
        regression,
        "probe_source_video",
        lambda _path, **_kwargs: _source_metadata(frame_count=frame_count),
    )
    calls = []

    def fake_pipeline(job, input_path, output_path, heartbeat, *, source_metadata):
        calls.append((job, input_path, output_path, source_metadata))
        heartbeat("inference")
        return result or _pipeline_result()

    monkeypatch.setattr(regression, "run_local_pipeline", fake_pipeline)
    monkeypatch.setattr(regression, "ResourceSampler", _FakeSampler)
    monkeypatch.setattr(
        regression,
        "read_versions",
        lambda: {
            "python": "3.12.12",
            "paddlepaddle": "3.3.0",
            "paddlex": "3.7.2",
            "opencv": "4.10.0",
            "ffmpeg": "7.1",
        },
    )
    monkeypatch.setattr(
        regression,
        "read_hardware",
        lambda: {
            "cpu_model": "test cpu",
            "vcpu_count": 2,
            "physical_memory_bytes": 2_000_000_000,
            "swap_total_bytes": 4_000_000_000,
        },
    )
    ticks = iter((10.0, 13.0))
    monkeypatch.setattr(regression, "_CLOCK", lambda: next(ticks))
    return calls, digest


def test_regression_runs_formal_pipeline_once_and_writes_full_frame_evidence(
    monkeypatch,
    tmp_path,
):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"real fixture bytes")
    report_path = tmp_path / "report.json"
    monkeypatch.setenv("PP_MCARE_IMPLEMENTATION_COMMIT", "deadbee")
    calls, digest = _configure_success(monkeypatch, video)

    report = run_regression(video_path=video, manual_total_count=90, report_path=report_path)

    assert len(calls) == 1
    job, input_path, output_path, source = calls[0]
    assert input_path != video
    assert output_path.name == "skeleton.mp4"
    assert source.frame_count == EXPECTED_DECODED_FRAME_COUNT
    assert job.action_source_key == "motion-resistance-shoulder-press"
    assert job.rule_version == "shoulder-press-v2"
    assert report["status"] == "completed"
    assert report["git_commit"] != "deadbee"
    assert report["implementation"]["git_commit"] == report["git_commit"]
    assert report["implementation"]["package_name"] == "pp-mcare"
    assert report["implementation"]["package_version"] == "0.1.0"
    assert len(report["implementation"]["implementation_sha256"]) == 64
    assert report["implementation"]["capability"] == {
        "protocol_version": "1",
        "action_source_key": "motion-resistance-shoulder-press",
        "algorithm_version": "PP-TinyPose_128x96",
        "rule_version": "shoulder-press-v2",
        "parameter_version": "shoulder-press-v2-defaults",
        "subject_tracker_version": "primary-subject-v1",
    }
    assert report["video"] == {
        "sha256": digest,
        "size_bytes": len(b"real fixture bytes"),
        "duration_seconds": 300.0,
        "width": 1920,
        "height": 1080,
        "fps": 8_929 / 300,
        "frame_count": 8_929,
        "codec_name": "hevc",
    }
    assert len(report["modes"]) == 1
    mode = report["modes"][0]
    assert mode["name"] == "all_frames"
    assert mode["sample_fps"] is None
    assert mode["decoded_frame_count"] == 8_929
    assert mode["inferred_frame_count"] == 8_929
    assert mode["encoded_frame_count"] == 8_929
    assert mode["result"]["left_event_count"] == 89
    assert mode["result"]["right_event_count"] == 90
    assert mode["result"]["total_count"] == 90
    assert mode["inference_seconds"] == 120.5
    assert mode["encoding_seconds"] == 30.25
    assert mode["total_seconds"] == 3.0
    assert mode["resource_peak"]["process_rss_bytes"] == 900_000_000
    assert mode["resource_peak"]["memory_available_bytes"] == 700_000_000
    assert mode["resource_peak"]["swap_used_bytes"] == 0
    assert report["acceptance"] == {"passed": True, "failures": []}
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    serialized = report_path.read_text(encoding="utf-8")
    assert str(video) not in serialized
    assert str(report_path) not in serialized
    assert not list(tmp_path.glob(".report.json.*"))
    assert not list(tmp_path.glob("pp-mcare-regression-*"))
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600


def test_regression_cli_returns_one_with_only_sanitized_failure(capsys, tmp_path):
    video = tmp_path / "patient-name-private.mp4"
    video.write_bytes(b"wrong fixture")
    report_path = tmp_path / "report.json"

    exit_code = main(
        [
            "regression",
            "--video",
            str(video),
            "--manual-total-count",
            "90",
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "回归失败" in captured.err
    assert str(video) not in captured.err
    assert "patient-name-private" not in captured.err


def test_regression_cli_has_no_sampled_mode_option(capsys):
    exit_code = main(
        [
            "regression",
            "--video",
            "/private/video.mp4",
            "--manual-total-count",
            "90",
            "--report",
            "/private/report.json",
            "--mode",
            "5fps",
        ]
    )

    assert exit_code == 2
    assert "参数无效" in capsys.readouterr().err


@pytest.mark.parametrize(
    "arguments",
    [
        [
            "regression",
            "--video",
            "/private/patient-name.mp4",
            "--manual-total-count",
            "secret-token-value",
            "--report",
            "/private/patient-report.json",
        ],
        [
            "regression",
            "--video",
            "/private/patient-name.mp4",
            "--manual-total-count",
            "90",
            "--report",
            "/private/patient-report.json",
            "--unknown",
            "Bearer-secret-token",
        ],
    ],
)
def test_regression_cli_parse_errors_never_echo_arguments(capsys, arguments):
    assert main(arguments) == 2

    captured = capsys.readouterr()
    assert captured.err == (
        "用法: pp_mcare regression --video <路径> "
        "--manual-total-count 90 --report <路径>\n"
        "pp_mcare: 参数无效\n"
    )
    for private_value in (
        "/private/patient-name.mp4",
        "/private/patient-report.json",
        "secret-token-value",
        "Bearer-secret-token",
    ):
        assert private_value not in captured.err


def test_regression_cli_help_remains_available(capsys):
    assert main(["regression", "--help"]) == 0

    captured = capsys.readouterr()
    assert "--video" in captured.out
    assert "--manual-total-count" in captured.out
    assert captured.err == ""


def test_implementation_sha256_is_deterministic_and_detects_source_tampering(tmp_path):
    package_root = tmp_path / "pp_mcare"
    package_root.mkdir()
    (package_root / "cli.py").write_text("first", encoding="utf-8")
    (package_root / "pipeline.py").write_text("second", encoding="utf-8")

    initial = regression._implementation_sha256(
        package_root,
        relative_paths=("cli.py", "pipeline.py"),
    )
    repeated = regression._implementation_sha256(
        package_root,
        relative_paths=("pipeline.py", "cli.py"),
    )
    (package_root / "pipeline.py").write_text("tampered", encoding="utf-8")
    tampered = regression._implementation_sha256(
        package_root,
        relative_paths=("cli.py", "pipeline.py"),
    )

    assert initial == repeated
    assert len(initial) == 64
    assert tampered != initial


def test_video_identity_ignores_access_time_but_detects_content_metadata_change():
    before = SimpleNamespace(
        st_dev=1,
        st_ino=2,
        st_mode=stat.S_IFREG | 0o600,
        st_nlink=1,
        st_uid=500,
        st_gid=500,
        st_size=100,
        st_mtime_ns=10,
        st_ctime_ns=11,
        st_atime_ns=12,
    )
    after_read = SimpleNamespace(**(vars(before) | {"st_atime_ns": 13}))
    changed = SimpleNamespace(**(vars(before) | {"st_mtime_ns": 14}))

    assert regression._same_file_identity(before, after_read)
    assert not regression._same_file_identity(before, changed)


@pytest.mark.parametrize(
    ("changes", "failure"),
    [
        ({"decoded_frame_count": 8_928}, "decoded_frame_count_mismatch"),
        ({"inferred_frame_count": 8_928}, "inferred_frame_count_mismatch"),
        ({"encoded_frame_count": 8_928}, "encoded_frame_count_mismatch"),
        (
            {
                "result_payload": {
                    "total_count": 90,
                    "standard_count": 85,
                    "nonstandard_count": 5,
                    "left_event_count": 88,
                    "right_event_count": 89,
                }
            },
            "side_max_count_mismatch",
        ),
    ],
)
def test_regression_rejects_non_full_frame_or_side_max_evidence(
    monkeypatch,
    tmp_path,
    changes,
    failure,
):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"real fixture bytes")
    result = _pipeline_result(**changes)
    _configure_success(monkeypatch, video, result=result)
    report_path = tmp_path / "report.json"

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=report_path)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert failure in report["acceptance"]["failures"]
    assert str(video) not in report_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("result", "peak", "ticks", "failure"),
    [
        (_pipeline_result(counts=MotionCounts(89, 84, 5), result_payload={
            "total_count": 89,
            "standard_count": 84,
            "nonstandard_count": 5,
            "left_event_count": 88,
            "right_event_count": 89,
        }), None, (10.0, 13.0), "manual_total_count_mismatch"),
        (_pipeline_result(), ResourceSnapshot(
            process_rss_bytes=int(1.5 * 1024**3),
            system_memory_used_bytes=1_000_000_000,
            memory_available_bytes=400_000_000,
            swap_used_bytes=0,
            swap_free_bytes=4_000_000_000,
        ), (10.0, 13.0), "all_frame_rss_limit_exceeded"),
        (_pipeline_result(), ResourceSnapshot(
            process_rss_bytes=900_000_000,
            system_memory_used_bytes=1_000_000_000,
            memory_available_bytes=400_000_000,
            swap_used_bytes=1,
            swap_free_bytes=3_999_999_999,
        ), (10.0, 13.0), "swap_used"),
        (_pipeline_result(), None, (10.0, 610.1), "all_frame_over_600_seconds"),
    ],
)
def test_regression_does_not_replace_algorithm_result_and_enforces_resource_gates(
    monkeypatch,
    tmp_path,
    result,
    peak,
    ticks,
    failure,
):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"real fixture bytes")
    _configure_success(monkeypatch, video, result=result)
    if peak is not None:
        class CustomSampler(_FakeSampler):
            def __init__(self):
                self.peak = peak

        monkeypatch.setattr(regression, "ResourceSampler", CustomSampler)
    clock = iter(ticks)
    monkeypatch.setattr(regression, "_CLOCK", lambda: next(clock))
    report_path = tmp_path / "report.json"

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=report_path)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert failure in report["acceptance"]["failures"]
    if failure == "manual_total_count_mismatch":
        assert report["modes"][0]["result"]["total_count"] == 89


def test_regression_rejects_wrong_video_hash_before_probe_or_pipeline(monkeypatch, tmp_path):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"wrong fixture")
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(regression, "EXPECTED_VIDEO_SHA256", "f" * 64)
    monkeypatch.setattr(
        regression,
        "probe_source_video",
        lambda _path: pytest.fail("hash mismatch must stop before probing"),
    )
    monkeypatch.setattr(
        regression,
        "run_local_pipeline",
        lambda *_a, **_k: pytest.fail("hash mismatch must stop before inference"),
    )

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=report_path)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["failure"] == {
        "stage": "hash_validation",
        "error_summary": "视频校验失败",
    }
    assert report["acceptance"]["failures"] == ["video_sha256_mismatch"]
    assert str(video) not in report_path.read_text(encoding="utf-8")


def test_regression_rejects_wrong_real_fixture_frame_count_before_pipeline(
    monkeypatch,
    tmp_path,
):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"real fixture bytes")
    report_path = tmp_path / "report.json"
    calls, _ = _configure_success(monkeypatch, video, frame_count=8_928)

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=report_path)

    assert calls == []
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["acceptance"]["failures"] == ["source_frame_count_mismatch"]


def test_regression_rejects_symlink_video_and_report_without_overwriting_target(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"private")
    video = tmp_path / "video.mp4"
    video.symlink_to(source)
    report_target = tmp_path / "report-target.json"
    report_target.write_text("keep", encoding="utf-8")
    report = tmp_path / "report.json"
    report.symlink_to(report_target)

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=report)

    assert report_target.read_text(encoding="utf-8") == "keep"


def test_regression_rejects_report_that_is_the_video_before_hashing(monkeypatch, tmp_path):
    video = tmp_path / "private-video.mp4"
    original = b"private video that must survive"
    video.write_bytes(original)
    monkeypatch.setattr(
        regression,
        "sha256_file",
        lambda _path: pytest.fail("colliding report must be rejected before hashing"),
    )

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=video)

    assert video.read_bytes() == original


def test_regression_rejects_existing_report_hardlink_to_video_without_writing(tmp_path):
    video = tmp_path / "private-video.mp4"
    original = b"private video that must survive"
    video.write_bytes(original)
    report = tmp_path / "report.json"
    os.link(video, report)

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=report)

    assert video.read_bytes() == original
    assert report.read_bytes() == original


def test_regression_hash_probe_and_pipeline_share_open_fd_when_path_is_replaced(
    monkeypatch,
    tmp_path,
):
    video = tmp_path / "private-video.mp4"
    original = b"validated original bytes"
    video.write_bytes(original)
    replacement = tmp_path / "unvalidated-replacement.mp4"
    replacement.write_bytes(b"unvalidated replacement bytes")
    report = tmp_path / "report.json"
    expected_digest = hashlib.sha256(original).hexdigest()
    monkeypatch.setattr(regression, "EXPECTED_VIDEO_SHA256", expected_digest)
    observed_paths = []

    original_sha256_file = regression.sha256_file

    def recording_hash(path):
        observed_paths.append(Path(path))
        return original_sha256_file(path)

    def replacing_probe(path, **_kwargs):
        observed_paths.append(Path(path))
        os.replace(replacement, video)
        assert Path(path).read_bytes() == original
        return _source_metadata()

    def reading_pipeline(_job, input_path, _output_path, _heartbeat, **_kwargs):
        observed_paths.append(Path(input_path))
        assert Path(input_path).read_bytes() == original
        return _pipeline_result()

    monkeypatch.setattr(regression, "sha256_file", recording_hash)
    monkeypatch.setattr(regression, "probe_source_video", replacing_probe)
    monkeypatch.setattr(regression, "run_local_pipeline", reading_pipeline)
    monkeypatch.setattr(regression, "ResourceSampler", _FakeSampler)
    monkeypatch.setattr(regression, "read_versions", lambda: {})
    monkeypatch.setattr(regression, "read_hardware", lambda: {})
    ticks = iter((10.0, 13.0))
    monkeypatch.setattr(regression, "_CLOCK", lambda: next(ticks))

    result = run_regression(video_path=video, manual_total_count=90, report_path=report)

    assert result["status"] == "completed"
    assert len(observed_paths) == 3
    assert len(set(observed_paths)) == 1
    assert observed_paths[0] != video
    assert video.read_bytes() == b"unvalidated replacement bytes"


@pytest.mark.parametrize(
    ("platform_name", "prefix"),
    [("linux", "/proc/self/fd/"), ("darwin", "/dev/fd/")],
)
def test_open_fd_path_is_explicit_and_platform_scoped(monkeypatch, platform_name, prefix):
    monkeypatch.setattr(regression.sys, "platform", platform_name)

    assert str(regression._open_fd_path(41)) == f"{prefix}41"


def test_open_fd_path_fails_closed_on_unsupported_platform(monkeypatch):
    monkeypatch.setattr(regression.sys, "platform", "win32")

    with pytest.raises(RegressionFailure):
        regression._open_fd_path(41)


def test_regression_closes_video_fd_when_initial_fstat_fails(monkeypatch, tmp_path):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"private")
    report = tmp_path / "report.json"
    original_open = regression.os.open
    original_fstat = regression.os.fstat
    video_descriptor = None

    def recording_open(path, flags, *args, **kwargs):
        nonlocal video_descriptor
        descriptor = original_open(path, flags, *args, **kwargs)
        if Path(path) == video:
            video_descriptor = descriptor
        return descriptor

    def failing_fstat(descriptor):
        if descriptor == video_descriptor:
            raise OSError("private fstat detail")
        return original_fstat(descriptor)

    monkeypatch.setattr(regression.os, "open", recording_open)
    monkeypatch.setattr(regression.os, "fstat", failing_fstat)

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=report)

    assert video_descriptor is not None
    with pytest.raises(OSError):
        original_fstat(video_descriptor)


def test_resource_snapshot_and_sampler_preserve_peak_rss_memory_and_swap(monkeypatch):
    class Memory:
        total = 2_000
        used = 1_100
        available = 900

    class Swap:
        total = 4_000
        used = 100
        free = 3_900

    class Process:
        pid = 1

        def children(self, *, recursive):
            assert recursive is True
            return []

        def memory_info(self):
            return SimpleNamespace(rss=300)

    fake_psutil = SimpleNamespace(
        Process=lambda: Process(),
        NoSuchProcess=type("NoSuchProcess", (Exception,), {}),
        AccessDenied=type("AccessDenied", (Exception,), {}),
        virtual_memory=lambda: Memory(),
        swap_memory=lambda: Swap(),
    )
    monkeypatch.setattr(regression, "psutil", fake_psutil)

    assert read_resource_snapshot() == ResourceSnapshot(300, 1_100, 900, 100, 3_900)

    snapshots = iter(
        [
            ResourceSnapshot(100, 500, 900, 10, 990),
            ResourceSnapshot(300, 700, 600, 40, 960),
            ResourceSnapshot(200, 650, 750, 20, 980),
        ]
    )
    sampler = ResourceSampler(reader=lambda: next(snapshots), interval_seconds=60)
    sampler.sample_once()
    sampler.sample_once()
    sampler.sample_once()
    assert sampler.peak == ResourceSnapshot(300, 700, 600, 40, 960)


def test_resource_snapshot_sums_unique_recursive_child_processes(monkeypatch):
    class Gone(Exception):
        pass

    class Denied(Exception):
        pass

    class Process:
        def __init__(self, pid, rss=0, failure=None):
            self.pid = pid
            self._rss = rss
            self._failure = failure

        def memory_info(self):
            if self._failure is not None:
                raise self._failure
            return SimpleNamespace(rss=self._rss)

    child = Process(2, rss=200)
    gone = Process(3, failure=Gone())
    denied = Process(4, failure=Denied())
    root = Process(1, rss=100)
    root.children = lambda recursive: [child, child, gone, denied]
    memory = SimpleNamespace(total=2_000, used=1_100, available=900)
    swap = SimpleNamespace(total=4_000, used=100, free=3_900)
    monkeypatch.setattr(
        regression,
        "psutil",
        SimpleNamespace(
            Process=lambda: root,
            NoSuchProcess=Gone,
            AccessDenied=Denied,
            virtual_memory=lambda: memory,
            swap_memory=lambda: swap,
        ),
    )

    snapshot = read_resource_snapshot()

    assert snapshot.process_rss_bytes == 300
    assert snapshot.unreadable_process_count == 1


def test_resource_sampler_fails_closed_and_stops_after_background_reader_error():
    background_called = threading.Event()
    calls = 0

    def reader():
        nonlocal calls
        calls += 1
        if calls == 1:
            return ResourceSnapshot(100, 500, 900, 0, 1_000)
        background_called.set()
        raise RuntimeError("private process detail")

    sampler = ResourceSampler(reader=reader, interval_seconds=0.001)

    with pytest.raises(RegressionFailure, match="资源采样失败"):
        with sampler:
            assert background_called.wait(timeout=1)

    assert sampler._thread is not None
    assert not sampler._thread.is_alive()


def test_acceptance_rss_gate_uses_process_tree_peak_field():
    mode = {
        "decoded_frame_count": 8_929,
        "inferred_frame_count": 8_929,
        "encoded_frame_count": 8_929,
        "total_seconds": 100.0,
        "result": {
            "total_count": 90,
            "standard_count": 85,
            "nonstandard_count": 5,
            "left_event_count": 89,
            "right_event_count": 90,
        },
        "resource_peak": {
            "process_rss_bytes": 1,
            "peak_rss_bytes": int(1.5 * 1024**3),
            "swap_used_bytes": 0,
            "unreadable_process_count": 0,
        },
    }

    assert "all_frame_rss_limit_exceeded" in regression._acceptance_failures(mode)


def test_module_entrypoint_dispatches_regression_without_reading_worker_settings(monkeypatch):
    import pp_mcare.__main__ as entrypoint
    import pp_mcare.cli as cli

    calls = []
    monkeypatch.setattr(cli, "main", lambda arguments: calls.append(tuple(arguments)) or 7)
    monkeypatch.setattr(
        entrypoint.Settings,
        "from_env",
        lambda: pytest.fail("regression must not read worker settings"),
    )

    assert entrypoint.main(["regression", "--manual-total-count", "90"]) == 7
    assert calls == [("regression", "--manual-total-count", "90")]
