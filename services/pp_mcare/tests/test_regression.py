from __future__ import annotations

import hashlib
import json
import stat
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
        lambda _path: _source_metadata(frame_count=frame_count),
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
    monkeypatch.setenv("PP_MCARE_IMPLEMENTATION_COMMIT", "abc1234")
    calls, digest = _configure_success(monkeypatch, video)

    report = run_regression(video_path=video, manual_total_count=90, report_path=report_path)

    assert len(calls) == 1
    job, input_path, output_path, source = calls[0]
    assert input_path == video
    assert output_path.name == "skeleton.mp4"
    assert source.frame_count == EXPECTED_DECODED_FRAME_COUNT
    assert job.action_source_key == "motion-resistance-shoulder-press"
    assert job.rule_version == "shoulder-press-v2"
    assert report["status"] == "completed"
    assert report["git_commit"] == "abc1234"
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
    assert "unrecognized arguments" in capsys.readouterr().err


def test_regression_report_commit_does_not_accept_untrusted_environment(monkeypatch):
    monkeypatch.setenv("PP_MCARE_IMPLEMENTATION_COMMIT", "/patient/private/path")

    assert regression._implementation_commit() == "unknown"


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
        def memory_info(self):
            return SimpleNamespace(rss=300)

    fake_psutil = SimpleNamespace(
        Process=lambda: Process(),
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
