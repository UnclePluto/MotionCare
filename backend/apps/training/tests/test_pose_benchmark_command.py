import signal
import traceback
from pathlib import Path
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def test_command_passes_fixed_paths_and_deletes_input_after_success(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "reports" / "report.json"
    summary = tmp_path / "reports" / "report.txt"
    runner = Mock(return_value={"status": "completed"})
    monkeypatch.setattr(
        "apps.training.management.commands.run_pose_smoke_benchmark.run_pose_smoke_benchmark",
        runner,
    )

    call_command(
        "run_pose_smoke_benchmark",
        video=str(video),
        report=str(report),
        summary=str(summary),
        expected_sha256="f" * 64,
        git_commit="abc1234",
        manual_total_count=90,
        delete_input=True,
    )

    assert not video.exists()
    runner.assert_called_once_with(
        Path(video),
        report_path=Path(report),
        summary_path=Path(summary),
        expected_sha256="f" * 64,
        git_commit="abc1234",
        manual_total_count=90,
    )


def test_command_keeps_failed_reports_and_deletes_input_when_benchmark_fails(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "reports" / "report.json"
    summary = tmp_path / "reports" / "report.txt"

    with pytest.raises(CommandError, match="冒烟测试失败"):
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(report),
            summary=str(summary),
            expected_sha256="f" * 64,
            git_commit="abc1234",
            manual_total_count=90,
            delete_input=True,
        )

    assert not video.exists()
    assert '"status": "failed"' in report.read_text(encoding="utf-8")
    assert "状态: failed" in summary.read_text(encoding="utf-8")


def test_command_failure_traceback_does_not_expose_private_error(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    private_error = "private failure /secret/patient-video.mp4"
    monkeypatch.setattr(
        "apps.training.management.commands.run_pose_smoke_benchmark.run_pose_smoke_benchmark",
        Mock(side_effect=RuntimeError(private_error)),
    )

    with pytest.raises(CommandError, match="冒烟测试失败") as exc_info:
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(tmp_path / "reports" / "report.json"),
            summary=str(tmp_path / "reports" / "report.txt"),
            expected_sha256="f" * 64,
            git_commit="abc1234",
            manual_total_count=90,
        )

    rendered_traceback = "".join(traceback.format_exception(exc_info.value))
    assert private_error not in rendered_traceback


def test_command_deletes_input_and_restores_handler_when_interrupted(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    monkeypatch.setattr(
        "apps.training.management.commands.run_pose_smoke_benchmark.run_pose_smoke_benchmark",
        Mock(side_effect=KeyboardInterrupt("received SIGTERM")),
    )

    with pytest.raises(KeyboardInterrupt, match="received SIGTERM"):
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(tmp_path / "reports" / "report.json"),
            summary=str(tmp_path / "reports" / "report.txt"),
            expected_sha256="f" * 64,
            git_commit="abc1234",
            manual_total_count=90,
            delete_input=True,
        )

    assert not video.exists()
    assert signal.getsignal(signal.SIGTERM) is previous_sigterm


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"expected_sha256": "bad"}, "expected-sha256"),
        ({"git_commit": "not-a-commit"}, "git-commit"),
    ],
)
def test_command_rejects_invalid_identifiers(tmp_path, overrides, message):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    options = {
        "video": str(video),
        "report": str(tmp_path / "reports" / "report.json"),
        "summary": str(tmp_path / "reports" / "report.txt"),
        "expected_sha256": "f" * 64,
        "git_commit": "abc1234",
        "manual_total_count": 90,
    }
    options.update(overrides)

    with pytest.raises(CommandError, match=message):
        call_command("run_pose_smoke_benchmark", **options)


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_sha256": "bad"},
        {"git_commit": "not-a-commit"},
    ],
)
def test_command_deletes_input_when_identifier_validation_fails(tmp_path, overrides):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    options = {
        "video": str(video),
        "report": str(tmp_path / "reports" / "report.json"),
        "summary": str(tmp_path / "reports" / "report.txt"),
        "expected_sha256": "f" * 64,
        "git_commit": "abc1234",
        "manual_total_count": 90,
        "delete_input": True,
    }
    options.update(overrides)

    with pytest.raises(CommandError):
        call_command("run_pose_smoke_benchmark", **options)

    assert not video.exists()


def test_command_rejects_symlink_input(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    video = tmp_path / "link.mp4"
    video.symlink_to(source)

    with pytest.raises(CommandError, match="符号链接"):
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(tmp_path / "reports" / "report.json"),
            summary=str(tmp_path / "reports" / "report.txt"),
            expected_sha256="f" * 64,
            git_commit="abc1234",
            manual_total_count=90,
        )


def test_command_rejects_reports_in_input_directory(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")

    with pytest.raises(CommandError, match="报告不能写入输入目录"):
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(tmp_path / "report.json"),
            summary=str(tmp_path / "reports" / "report.txt"),
            expected_sha256="f" * 64,
            git_commit="abc1234",
            manual_total_count=90,
        )


def test_command_rejects_summary_in_input_directory(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")

    with pytest.raises(CommandError, match="摘要不能写入输入目录"):
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(tmp_path / "reports" / "report.json"),
            summary=str(tmp_path / "report.txt"),
            expected_sha256="f" * 64,
            git_commit="abc1234",
            manual_total_count=90,
        )


def test_command_rejects_same_report_and_summary_path_and_deletes_input(
    tmp_path,
    monkeypatch,
):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "reports" / "report.json"
    summary = report.parent / "nested" / ".." / report.name
    runner = Mock(return_value={"status": "completed"})
    monkeypatch.setattr(
        "apps.training.management.commands.run_pose_smoke_benchmark.run_pose_smoke_benchmark",
        runner,
    )

    with pytest.raises(CommandError, match="报告与摘要不能使用同一路径"):
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(report),
            summary=str(summary),
            expected_sha256="f" * 64,
            git_commit="abc1234",
            manual_total_count=90,
            delete_input=True,
        )

    assert not video.exists()
    runner.assert_not_called()


@pytest.mark.parametrize("invalid_output", ["report", "summary"])
def test_command_deletes_input_when_output_directory_validation_fails(
    tmp_path,
    invalid_output,
):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    options = {
        "video": str(video),
        "report": str(tmp_path / "reports" / "report.json"),
        "summary": str(tmp_path / "reports" / "report.txt"),
        "expected_sha256": "f" * 64,
        "git_commit": "abc1234",
        "manual_total_count": 90,
        "delete_input": True,
    }
    options[invalid_output] = str(tmp_path / f"{invalid_output}.txt")

    with pytest.raises(CommandError):
        call_command("run_pose_smoke_benchmark", **options)

    assert not video.exists()


@pytest.mark.parametrize("manual_total_count", [0, -1, "not-an-integer"])
def test_command_rejects_non_positive_or_non_integer_manual_count(
    tmp_path,
    manual_total_count,
):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")

    with pytest.raises(CommandError, match="manual-total-count"):
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(tmp_path / "reports" / "report.json"),
            summary=str(tmp_path / "reports" / "report.txt"),
            expected_sha256="f" * 64,
            git_commit="abc1234",
            manual_total_count=manual_total_count,
        )


def test_command_requires_manual_count(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")

    with pytest.raises(CommandError, match="manual-total-count"):
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(tmp_path / "reports" / "report.json"),
            summary=str(tmp_path / "reports" / "report.txt"),
            expected_sha256="f" * 64,
            git_commit="abc1234",
        )
