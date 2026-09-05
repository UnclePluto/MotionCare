from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import subprocess
import threading
import time
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


_PRODUCTION_REPORT_PUBLISHER = regression._publish_report


@pytest.fixture(autouse=True)
def _darwin_test_only_report_publisher(monkeypatch):
    if regression.sys.platform != "darwin":
        return

    def publish(parent_descriptor: int, final_name: str, content: bytes) -> None:
        descriptor = os.open(
            final_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_descriptor,
        )
        try:
            regression._write_all(descriptor, content)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(parent_descriptor)

    monkeypatch.setattr(regression, "_publish_report", publish)


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
    assert report["report_format_version"] == "4.0"
    assert report["status"] == "completed"
    assert report["git_commit"] != "deadbee"
    assert report["implementation"]["git_commit"] == report["git_commit"]
    assert report["implementation"]["package_name"] == "pp-mcare"
    assert report["implementation"]["package_version"] == "0.1.0"
    assert len(report["implementation"]["regression_runtime_sha256"]) == 64
    assert len(report["implementation"]["distribution_content_sha256"]) == 64
    assert report["implementation"]["release_artifact"] == {
        "manifest_status": "source_checkout",
        "wheel_sha256": None,
    }
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


def test_regression_cli_returns_one_without_replacing_existing_report(capsys, tmp_path):
    video = tmp_path / "patient-name-private.mp4"
    video.write_bytes(b"private video")
    report_path = tmp_path / "patient-report.json"
    report_path.write_bytes(b"existing report")

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
    assert report_path.read_bytes() == b"existing report"
    captured = capsys.readouterr()
    assert captured.err == "pp-mcare 回归失败，详情见脱敏报告\n"
    assert str(video) not in captured.err
    assert str(report_path) not in captured.err


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
    assert "目标必须不存在" in captured.out
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


def test_source_distribution_digest_covers_all_package_metadata_and_license_files(tmp_path):
    project_root = tmp_path / "service"
    package_root = project_root / "src" / "pp_mcare"
    package_root.mkdir(parents=True)
    (package_root / "pipeline.py").write_text("pipeline-v1", encoding="utf-8")
    (package_root / "api_client.py").write_text("client-v1", encoding="utf-8")
    (project_root / "pyproject.toml").write_text(
        '[project]\nname="pp-mcare"\nversion="0.1.0"\ndependencies=["httpx"]\n',
        encoding="utf-8",
    )
    (project_root / "LICENSE.paddledetection").write_text("license-v1", encoding="utf-8")
    (project_root / "NOTICE").write_text("notice-v1", encoding="utf-8")
    digest_reader = getattr(regression, "_distribution_content_sha256", None)

    assert digest_reader is not None
    initial = digest_reader(package_root)
    assert digest_reader(package_root) == initial

    for path, changed_content in (
        (package_root / "api_client.py", "client-v2"),
        (project_root / "pyproject.toml", '[project]\nname="pp-mcare"\nversion="0.1.0"\ndependencies=["qiniu"]\n'),
        (project_root / "LICENSE.paddledetection", "license-v2"),
        (project_root / "NOTICE", "notice-v2"),
    ):
        original_content = path.read_text(encoding="utf-8")
        path.write_text(changed_content, encoding="utf-8")
        assert digest_reader(package_root) != initial
        path.write_text(original_content, encoding="utf-8")


def test_installed_distribution_digest_ignores_unrelated_ancestor_pyproject(
    monkeypatch,
    tmp_path,
):
    package_root = tmp_path / "site-packages" / "pp_mcare"
    package_root.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("unrelated", encoding="utf-8")
    monkeypatch.setattr(
        regression,
        "_installed_distribution_entries",
        lambda: [("pp_mcare/worker.py", b"installed-wheel-content")],
    )

    digest = regression._distribution_content_sha256(package_root)

    assert digest == regression._digest_named_content(
        [("pp_mcare/worker.py", b"installed-wheel-content")]
    )


def test_implementation_identity_names_core_and_full_distribution_digests(monkeypatch):
    distribution_calls = []
    monkeypatch.setattr(
        regression,
        "_distribution_content_sha256",
        lambda package_root: distribution_calls.append(package_root) or "d" * 64,
        raising=False,
    )

    identity = regression.read_implementation_identity()

    assert distribution_calls == [Path(regression.__file__).resolve().parent]
    assert identity["distribution_content_sha256"] == "d" * 64
    assert len(identity["regression_runtime_sha256"]) == 64
    assert "implementation_sha256" not in identity


def test_release_manifest_wheel_identity_is_only_accepted_when_install_digest_matches(
    monkeypatch,
    tmp_path,
):
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": "1",
                "package_name": "pp-mcare",
                "package_version": "0.1.0",
                "wheel_sha256": "a" * 64,
                "installed_distribution_sha256": "d" * 64,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(regression, "_RELEASE_MANIFEST_PATH", manifest, raising=False)
    monkeypatch.setattr(regression, "_distribution_content_sha256", lambda _root: "d" * 64, raising=False)
    monkeypatch.setattr(regression, "_source_checkout_identity", lambda _root: None)

    identity = regression.read_implementation_identity()

    assert identity["release_artifact"] == {
        "manifest_status": "verified",
        "wheel_sha256": "a" * 64,
    }

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["installed_distribution_sha256"] = "e" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RegressionFailure, match="发布清单身份不匹配"):
        regression.read_implementation_identity()


def test_source_checkout_rejects_repo_ancestor_site_packages(monkeypatch, tmp_path):
    repository_root = tmp_path / "repository"
    package_root = repository_root / "backend" / ".venv" / "site-packages" / "pp_mcare"
    package_root.mkdir(parents=True)
    commit = "a" * 40

    def fake_run(arguments, **_kwargs):
        if arguments[-1] == "--show-toplevel":
            return SimpleNamespace(stdout=f"{repository_root}\n")
        if arguments[-1] == "HEAD":
            return SimpleNamespace(stdout=f"{commit}\n")
        raise AssertionError(arguments)

    monkeypatch.setattr(regression.subprocess, "run", fake_run)

    assert regression._source_checkout_commit(package_root) is None


def test_source_checkout_rejects_exact_but_untracked_package_copy(monkeypatch, tmp_path):
    repository_root = tmp_path / "repository"
    project_root = repository_root / "services" / "pp_mcare"
    package_root = project_root / "src" / "pp_mcare"
    package_root.mkdir(parents=True)
    (project_root / "pyproject.toml").write_text(
        '[project]\nname="pp-mcare"\nversion="0.1.0"\n',
        encoding="utf-8",
    )
    commit = "b" * 40

    def fake_run(arguments, **_kwargs):
        if arguments[-1] == "--show-toplevel":
            return SimpleNamespace(stdout=f"{repository_root}\n")
        if "ls-files" in arguments:
            raise subprocess.CalledProcessError(1, arguments)
        if arguments[-1] == "HEAD":
            return SimpleNamespace(stdout=f"{commit}\n")
        raise AssertionError(arguments)

    monkeypatch.setattr(regression.subprocess, "run", fake_run)

    assert regression._source_checkout_commit(package_root) is None


def test_source_checkout_rejects_non_pp_mcare_or_malformed_adjacent_project(tmp_path):
    project_root = tmp_path / "service"
    package_root = project_root / "src" / "pp_mcare"
    package_root.mkdir(parents=True)
    pyproject = project_root / "pyproject.toml"

    pyproject.write_text('[project]\nname="other-package"\n', encoding="utf-8")
    assert regression._source_project_root(package_root) is None

    pyproject.write_text('project="not-a-table"\n', encoding="utf-8")
    assert regression._source_project_root(package_root) is None


def test_git_command_failure_reports_no_commit_or_dirty_state(monkeypatch):
    monkeypatch.setattr(
        regression.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("git unavailable")),
    )

    identity = regression.read_implementation_identity()

    assert identity["git_commit"] is None
    assert identity["git_dirty"] is None
    assert identity["release_artifact"]["manifest_status"] == "not_present"


def test_source_checkout_identity_reports_actual_head_and_dirty_semantics():
    package_root = Path(regression.__file__).resolve().parent
    repository_root = Path(
        subprocess.run(
            ["git", "-C", str(package_root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    expected_commit = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    project_root = package_root.parent.parent
    expected_dirty = bool(
        subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
                str(project_root.relative_to(repository_root)),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )

    identity = regression.read_implementation_identity()

    assert identity["git_commit"] == expected_commit
    assert identity["git_dirty"] is expected_dirty


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


def test_regression_report_is_create_once_and_preserves_existing_regular_file(
    monkeypatch,
    tmp_path,
):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"private video")
    report = tmp_path / "report.json"
    report.write_bytes(b"existing report must survive")
    monkeypatch.setattr(
        regression,
        "sha256_file",
        lambda _path: pytest.fail("existing report must be rejected before hashing"),
    )

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=report)

    assert report.read_bytes() == b"existing report must survive"


def test_regression_closes_report_parent_fd_when_create_once_precheck_fails(
    monkeypatch,
    tmp_path,
):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"private video")
    report = tmp_path / "report.json"
    report.write_bytes(b"existing report")
    original_open = regression.os.open
    parent_descriptor = None

    def recording_open(path, flags, *args, **kwargs):
        nonlocal parent_descriptor
        descriptor = original_open(path, flags, *args, **kwargs)
        if Path(path) == tmp_path:
            parent_descriptor = descriptor
        return descriptor

    monkeypatch.setattr(regression.os, "open", recording_open)

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=report)

    assert parent_descriptor is not None
    with pytest.raises(OSError):
        os.fstat(parent_descriptor)


def test_atomic_report_commit_never_replaces_target_created_after_entry_validation(
    monkeypatch,
    tmp_path,
):
    video = tmp_path / "private-video.mp4"
    original = b"validated original bytes"
    video.write_bytes(original)
    report = tmp_path / "report.json"
    _configure_success(monkeypatch, video)
    configured_pipeline = regression.run_local_pipeline

    def racing_pipeline(*args, **kwargs):
        result = configured_pipeline(*args, **kwargs)
        os.replace(video, report)
        return result

    monkeypatch.setattr(regression, "run_local_pipeline", racing_pipeline)

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=report)

    assert report.read_bytes() == original
    assert not list(tmp_path.glob(".report.json.*"))


def test_atomic_report_publish_never_links_a_rebound_temporary_name(
    monkeypatch,
    tmp_path,
):
    report = tmp_path / "report.json"
    input_video = tmp_path / "private-video.mp4"
    original_video = b"attacker must not publish this inode"
    input_video.write_bytes(original_video)
    expected_report = {"status": "completed", "count": 90}
    original_link = regression.os.link

    def rebind_temporary_name(source, destination, *, src_dir_fd, dst_dir_fd, **kwargs):
        os.unlink(source, dir_fd=src_dir_fd)
        original_link(input_video, source, dst_dir_fd=src_dir_fd)
        return original_link(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            **kwargs,
        )

    monkeypatch.setattr(regression.os, "link", rebind_temporary_name)

    try:
        regression._atomic_write_report(report, expected_report)
    except RegressionFailure:
        pass

    assert input_video.read_bytes() == original_video
    if report.exists():
        assert json.loads(report.read_text(encoding="utf-8")) == expected_report
    assert not list(tmp_path.glob(".report.json.*"))


def test_linux_linkat_publishes_only_the_open_fd_to_the_validated_basename(monkeypatch):
    calls = []

    descriptor_identity = SimpleNamespace(st_dev=11, st_ino=12)
    original_stat = os.stat

    def stat_proc_descriptor(path, *args, **kwargs):
        if path == "/proc/self/fd/41":
            calls.append(("stat", path, kwargs.get("follow_symlinks")))
            return descriptor_identity
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(
        regression.os,
        "stat",
        stat_proc_descriptor,
    )
    monkeypatch.setattr(
        regression.os,
        "fstat",
        lambda descriptor: calls.append(("fstat", descriptor)) or descriptor_identity,
    )

    class LinkAt:
        argtypes = None
        restype = None

        def __call__(self, *arguments):
            calls.append(arguments)
            return 0

    linkat = LinkAt()
    library = SimpleNamespace(linkat=linkat)
    monkeypatch.setattr(
        regression.ctypes,
        "CDLL",
        lambda name, *, use_errno: (
            calls.append(("CDLL", name, use_errno)) or library
        ),
    )

    regression._link_anonymous_file_linux(41, 42, "report.json")

    assert calls == [
        ("stat", "/proc/self/fd/41", True),
        ("fstat", 41),
        ("CDLL", None, True),
        (
            regression._AT_FDCWD,
            b"/proc/self/fd/41",
            42,
            b"report.json",
            regression._AT_SYMLINK_FOLLOW,
        ),
    ]
    assert linkat.argtypes == [
        regression.ctypes.c_int,
        regression.ctypes.c_char_p,
        regression.ctypes.c_int,
        regression.ctypes.c_char_p,
        regression.ctypes.c_int,
    ]
    assert linkat.restype is regression.ctypes.c_int


def test_linux_linkat_fails_closed_when_proc_self_fd_is_unavailable(monkeypatch):
    original_stat = os.stat

    def reject_proc_descriptor(path, *args, **kwargs):
        if path == "/proc/self/fd/41":
            raise FileNotFoundError(errno.ENOENT, "proc unavailable")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(
        regression.os,
        "stat",
        reject_proc_descriptor,
    )
    monkeypatch.setattr(
        regression.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: pytest.fail("libc must not run without /proc/self/fd"),
    )

    with pytest.raises(RegressionFailure, match="当前 Linux 不支持安全报告发布"):
        regression._link_anonymous_file_linux(41, 42, "report.json")


def test_linux_linkat_fails_closed_when_proc_path_is_not_the_open_fd(monkeypatch):
    original_stat = os.stat

    def stat_wrong_inode(path, *args, **kwargs):
        if path == "/proc/self/fd/41":
            return SimpleNamespace(st_dev=11, st_ino=99)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(regression.os, "stat", stat_wrong_inode)
    monkeypatch.setattr(
        regression.os,
        "fstat",
        lambda _descriptor: SimpleNamespace(st_dev=11, st_ino=12),
    )
    monkeypatch.setattr(
        regression.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: pytest.fail("libc must not run for a mismatched proc fd"),
    )

    with pytest.raises(RegressionFailure, match="当前 Linux 不支持安全报告发布"):
        regression._link_anonymous_file_linux(41, 42, "report.json")


def test_linux_linkat_avoids_capability_dependent_empty_path(monkeypatch):
    descriptor_identity = SimpleNamespace(st_dev=11, st_ino=12)
    original_stat = os.stat
    monkeypatch.setattr(
        regression.os,
        "stat",
        lambda path, *args, **kwargs: (
            descriptor_identity
            if path == "/proc/self/fd/41"
            else original_stat(path, *args, **kwargs)
        ),
    )
    monkeypatch.setattr(regression.os, "fstat", lambda _descriptor: descriptor_identity)

    class LinkAt:
        argtypes = None
        restype = None

        def __call__(self, old_dir_fd, old_path, *_arguments):
            if old_dir_fd == 41 and old_path == b"":
                return -1
            return 0

    monkeypatch.setattr(
        regression.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: SimpleNamespace(linkat=LinkAt()),
    )
    monkeypatch.setattr(regression.ctypes, "get_errno", lambda: errno.ENOENT)

    regression._link_anonymous_file_linux(41, 42, "report.json")


@pytest.mark.parametrize("invalid_name", ["../report.json", ".", "..", "nested/report.json"])
def test_linux_linkat_rejects_arbitrary_paths_and_preserves_errno(monkeypatch, invalid_name):
    monkeypatch.setattr(
        regression.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: pytest.fail("invalid basename must not call libc"),
    )
    with pytest.raises(RegressionFailure, match="报告文件名无效"):
        regression._link_anonymous_file_linux(41, 42, invalid_name)

    class LinkAt:
        argtypes = None
        restype = None

        def __call__(self, *_arguments):
            return -1

    monkeypatch.setattr(
        regression.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: SimpleNamespace(linkat=LinkAt()),
    )
    descriptor_identity = SimpleNamespace(st_dev=11, st_ino=12)
    original_stat = os.stat
    monkeypatch.setattr(
        regression.os,
        "stat",
        lambda path, *args, **kwargs: (
            descriptor_identity
            if path == "/proc/self/fd/41"
            else original_stat(path, *args, **kwargs)
        ),
    )
    monkeypatch.setattr(regression.os, "fstat", lambda _descriptor: descriptor_identity)
    monkeypatch.setattr(regression.ctypes, "get_errno", lambda: errno.EEXIST)
    with pytest.raises(OSError) as captured:
        regression._link_anonymous_file_linux(41, 42, "report.json")
    assert captured.value.errno == errno.EEXIST


@pytest.mark.parametrize("invalid_descriptor", [-1, True, "41/../../private"])
def test_linux_linkat_rejects_non_numeric_fd_path_injection(monkeypatch, invalid_descriptor):
    monkeypatch.setattr(
        regression.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: pytest.fail("invalid descriptor must not call libc"),
    )

    with pytest.raises(RegressionFailure, match="报告文件描述符无效"):
        regression._link_anonymous_file_linux(invalid_descriptor, 42, "report.json")


def test_linux_report_publisher_keeps_anonymous_fd_open_through_linkat(monkeypatch):
    calls = []
    temporary_flag = 0x410000
    monkeypatch.setattr(regression.os, "O_TMPFILE", temporary_flag, raising=False)
    monkeypatch.setattr(
        regression.os,
        "open",
        lambda path, flags, mode, *, dir_fd: (
            calls.append(("open", path, flags, mode, dir_fd)) or 51
        ),
    )
    monkeypatch.setattr(regression, "_write_all", lambda fd, data: calls.append(("write", fd, data)))
    monkeypatch.setattr(regression.os, "fsync", lambda fd: calls.append(("fsync", fd)))
    monkeypatch.setattr(
        regression.os,
        "fstat",
        lambda fd: SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_nlink=0),
    )
    monkeypatch.setattr(
        regression,
        "_link_anonymous_file_linux",
        lambda fd, parent_fd, name: calls.append(("linkat", fd, parent_fd, name)),
    )
    monkeypatch.setattr(regression.os, "close", lambda fd: calls.append(("close", fd)))

    regression._publish_report_linux(50, "report.json", b"canonical-json")

    assert calls == [
        (
            "open",
            ".",
            os.O_WRONLY | temporary_flag | getattr(os, "O_CLOEXEC", 0),
            0o600,
            50,
        ),
        ("write", 51, b"canonical-json"),
        ("fsync", 51),
        ("linkat", 51, 50, "report.json"),
        ("fsync", 50),
        ("close", 51),
    ]


def test_production_report_publisher_fails_closed_outside_linux(monkeypatch):
    monkeypatch.setattr(regression.sys, "platform", "darwin")
    with pytest.raises(RegressionFailure, match="当前平台不支持安全报告发布"):
        _PRODUCTION_REPORT_PUBLISHER(41, "report.json", b"canonical-json")


def test_production_report_publisher_dispatches_only_to_linux_fd_publisher(monkeypatch):
    calls = []
    monkeypatch.setattr(regression.sys, "platform", "linux")
    monkeypatch.setattr(
        regression,
        "_publish_report_linux",
        lambda parent_fd, name, content: calls.append((parent_fd, name, content)),
    )

    _PRODUCTION_REPORT_PUBLISHER(41, "report.json", b"canonical-json")

    assert calls == [(41, "report.json", b"canonical-json")]


def test_linux_report_publisher_closes_fd_when_atomic_link_fails(monkeypatch):
    temporary_flag = 0x410000
    closed = []
    monkeypatch.setattr(regression.os, "O_TMPFILE", temporary_flag, raising=False)
    monkeypatch.setattr(regression.os, "open", lambda *_args, **_kwargs: 51)
    monkeypatch.setattr(regression, "_write_all", lambda *_args: None)
    monkeypatch.setattr(regression.os, "fsync", lambda *_args: None)
    monkeypatch.setattr(
        regression.os,
        "fstat",
        lambda _fd: SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_nlink=0),
    )
    monkeypatch.setattr(
        regression,
        "_link_anonymous_file_linux",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EEXIST, "exists")),
    )
    monkeypatch.setattr(regression.os, "close", lambda fd: closed.append(fd))

    with pytest.raises(RegressionFailure, match="报告写入失败"):
        regression._publish_report_linux(50, "report.json", b"canonical-json")

    assert closed == [51]


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
    assert len(observed_paths) == 4
    assert len(set(observed_paths)) == 1
    assert observed_paths[0] != video
    assert video.read_bytes() == b"unvalidated replacement bytes"


def test_regression_pipeline_reads_private_snapshot_after_source_inode_is_rewritten(
    monkeypatch,
    tmp_path,
):
    video = tmp_path / "private-video.mp4"
    original = b"validated-content-A"
    unvalidated = b"untrusted-content-B"
    assert len(original) == len(unvalidated)
    video.write_bytes(original)
    report = tmp_path / "report.json"
    calls, _digest = _configure_success(monkeypatch, video)
    configured_pipeline = regression.run_local_pipeline
    pipeline_inputs: list[bytes] = []

    def reading_pipeline(*args, **kwargs):
        pipeline_inputs.append(Path(args[1]).read_bytes())
        return configured_pipeline(*args, **kwargs)

    monkeypatch.setattr(regression, "run_local_pipeline", reading_pipeline)
    expected_digest = hashlib.sha256(original).hexdigest()
    monkeypatch.setattr(regression, "EXPECTED_VIDEO_SHA256", expected_digest)
    original_hash = regression.sha256_file
    source_times = video.stat()
    hash_calls = 0

    def rewrite_source_then_hash(path):
        nonlocal hash_calls
        hash_calls += 1
        if hash_calls == 1:
            video.write_bytes(unvalidated)
            os.utime(
                video,
                ns=(source_times.st_atime_ns, source_times.st_mtime_ns),
            )
        return original_hash(path)

    monkeypatch.setattr(regression, "sha256_file", rewrite_source_then_hash)

    result = run_regression(video_path=video, manual_total_count=90, report_path=report)

    assert result["status"] == "completed"
    assert len(calls) == 1
    assert pipeline_inputs == [original]
    assert video.read_bytes() == unvalidated


def test_regression_fails_when_source_inode_changes_while_snapshot_is_copied(
    monkeypatch,
    tmp_path,
):
    video = tmp_path / "private-video.mp4"
    original = b"validated-content-A"
    unvalidated = b"untrusted-content-B"
    assert len(original) == len(unvalidated)
    video.write_bytes(original)
    source_times = video.stat()
    source_identity = (source_times.st_dev, source_times.st_ino)
    report = tmp_path / "report.json"
    calls, _digest = _configure_success(monkeypatch, video)
    original_read = regression.os.read
    changed = False

    def racing_read(descriptor, size):
        nonlocal changed
        content = original_read(descriptor, size)
        descriptor_stat = os.fstat(descriptor)
        descriptor_identity = (descriptor_stat.st_dev, descriptor_stat.st_ino)
        if content and not changed and descriptor_identity == source_identity:
            changed = True
            video.write_bytes(unvalidated)
            os.utime(
                video,
                ns=(source_times.st_atime_ns, source_times.st_mtime_ns),
            )
        return content

    monkeypatch.setattr(regression.os, "read", racing_read)

    with pytest.raises(RegressionFailure):
        run_regression(video_path=video, manual_total_count=90, report_path=report)

    assert changed is True
    assert calls == []


def test_regression_rejects_fifo_without_waiting_for_a_writer(tmp_path):
    video = tmp_path / "private-video.fifo"
    os.mkfifo(video)
    report = tmp_path / "report.json"
    errors: list[BaseException] = []

    def run() -> None:
        try:
            run_regression(video_path=video, manual_total_count=90, report_path=report)
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=run, daemon=True)
    started = time.monotonic()
    worker.start()
    worker.join(timeout=0.25)
    finished_without_writer = not worker.is_alive()
    if worker.is_alive():
        writer = os.open(video, os.O_WRONLY | os.O_NONBLOCK)
        os.close(writer)
        worker.join(timeout=1)

    assert finished_without_writer
    assert time.monotonic() - started < 0.5
    assert len(errors) == 1
    assert isinstance(errors[0], RegressionFailure)
    assert not report.exists()


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


def test_resource_sampler_exit_has_a_deadline_when_background_reader_blocks(monkeypatch):
    background_started = threading.Event()
    release_reader = threading.Event()
    calls = 0

    def reader():
        nonlocal calls
        calls += 1
        if calls == 1:
            return ResourceSnapshot(100, 500, 900, 0, 1_000)
        background_started.set()
        release_reader.wait()
        return ResourceSnapshot(200, 600, 800, 0, 1_000)

    monkeypatch.setattr(ResourceSampler, "JOIN_TIMEOUT_SECONDS", 0.05, raising=False)
    sampler = ResourceSampler(reader=reader, interval_seconds=0.001)
    errors: list[BaseException] = []

    def sample() -> None:
        try:
            with pytest.raises(RegressionFailure, match="资源采样失败"):
                with sampler:
                    assert background_started.wait(timeout=1)
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=sample, daemon=True)
    worker.start()
    assert background_started.wait(timeout=1)
    worker.join(timeout=0.25)
    finished_within_deadline = not worker.is_alive()
    release_reader.set()
    worker.join(timeout=2)

    assert finished_within_deadline
    assert errors == []


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
