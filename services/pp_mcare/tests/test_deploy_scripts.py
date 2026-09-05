from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_ROOT = REPOSITORY_ROOT / "deploy" / "pp-mcare"
BOOTSTRAP_SCRIPT = DEPLOY_ROOT / "bootstrap.sh"
INSTALL_SCRIPT = DEPLOY_ROOT / "install-release.sh"
REGRESSION_SCRIPT = DEPLOY_ROOT / "run-regression.sh"
SERVICE_UNIT = DEPLOY_ROOT / "pp-mcare.service"
ENV_EXAMPLE = DEPLOY_ROOT / "env.example"


def source_and_call(
    script: Path,
    function: str,
    *arguments: object,
    executable_directory: Path | None = None,
):
    environment = os.environ.copy()
    if executable_directory is not None:
        python312 = executable_directory / "python3.12"
        python312.symlink_to(sys.executable)
        environment["PATH"] = f"{executable_directory}:{environment['PATH']}"
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; shift; function="$1"; shift; "$function" "$@"',
            "test-shell",
            str(script),
            function,
            *(str(argument) for argument in arguments),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )


def _write_archive(path: Path, *, member_name: str, member_type: bytes) -> None:
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo(member_name)
        member.type = member_type
        if member_type == tarfile.REGTYPE:
            content = b"safe"
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        else:
            member.linkname = "safe-target"
            archive.addfile(member)


def _run_regression_with_fake_boundaries(tmp_path: Path):
    analysis_root = tmp_path / "analysis"
    run_id = "20260906T120000Z"
    video = analysis_root / "input" / f"pp-mcare-{run_id}.mp4"
    current = analysis_root / "current"
    reports = analysis_root / "reports"
    bin_dir = tmp_path / "bin"
    cwd_log = tmp_path / "runuser.cwd"
    for directory in (video.parent, current, reports, bin_dir):
        directory.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"fixed-regression-video")

    copied_script = tmp_path / "run-regression.sh"
    copied_script.write_text(
        REGRESSION_SCRIPT.read_text(encoding="utf-8").replace(
            'readonly ANALYSIS_ROOT="/opt/motioncare-analysis"',
            f'readonly ANALYSIS_ROOT="{analysis_root}"',
        ),
        encoding="utf-8",
    )
    fake_commands = {
        "python3.12": "#!/usr/bin/env bash\nexit 0\n",
        "stat": (
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' 'motioncare-analysis:motioncare-analysis:600:1'\n"
        ),
        "sha256sum": (
            "#!/usr/bin/env bash\n"
            "printf '%s  %s\\n' "
            "'f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd' "
            '"$1"\n'
        ),
        "runuser": "#!/usr/bin/env bash\npwd > \"${PP_MCARE_TEST_CWD_LOG}\"\n",
    }
    for name, content in fake_commands.items():
        command = bin_dir / name
        command.write_text(content, encoding="utf-8")
        command.chmod(0o700)

    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["PP_MCARE_TEST_CWD_LOG"] = str(cwd_log)
    completed = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; shift; _run_regression "$@"',
            "test-shell",
            str(copied_script),
            str(video),
            "f59b6e773200588453f55c11a1aea796440efd34",
            run_id,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
        cwd=tmp_path,
    )
    return completed, video, current, cwd_log


def test_install_release_rejects_non_commit_release_name(tmp_path):
    completed = source_and_call(INSTALL_SCRIPT, "_install_release", tmp_path, "latest")

    assert completed.returncode == 2
    assert "latest" not in completed.stderr


@pytest.mark.parametrize(
    ("member_name", "member_type"),
    [
        ("../escape", tarfile.REGTYPE),
        ("/absolute", tarfile.REGTYPE),
        ("link", tarfile.SYMTYPE),
        ("hardlink", tarfile.LNKTYPE),
        ("device", tarfile.CHRTYPE),
        ("fifo", tarfile.FIFOTYPE),
    ],
)
def test_install_release_rejects_unsafe_archive_members(
    tmp_path, member_name, member_type
):
    archive_path = tmp_path / "release.tar.gz"
    _write_archive(archive_path, member_name=member_name, member_type=member_type)

    completed = source_and_call(
        INSTALL_SCRIPT,
        "_validate_archive_members",
        archive_path,
        executable_directory=tmp_path,
    )

    assert completed.returncode != 0


def test_install_release_accepts_safe_regular_archive_members(tmp_path):
    archive_path = tmp_path / "release.tar.gz"
    _write_archive(
        archive_path,
        member_name="services/pp_mcare/pyproject.toml",
        member_type=tarfile.REGTYPE,
    )

    completed = source_and_call(
        INSTALL_SCRIPT,
        "_validate_archive_members",
        archive_path,
        executable_directory=tmp_path,
    )

    assert completed.returncode == 0, completed.stderr


def test_install_release_rejects_non_object_manifest_without_traceback(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "artifact-manifest.json").write_text("1\n", encoding="utf-8")

    completed = source_and_call(
        INSTALL_SCRIPT,
        "_validate_artifact_manifest",
        candidate,
        "a" * 40,
        executable_directory=tmp_path,
    )

    assert completed.returncode != 0
    assert completed.stderr.strip() == "构建产物清单无效"


def test_systemd_unit_runs_unprivileged_without_inbound_port():
    unit = SERVICE_UNIT.read_text(encoding="utf-8")

    assert "User=motioncare-analysis" in unit
    assert "ExecStart=/opt/motioncare-analysis/current/.venv/bin/python -m pp_mcare" in unit
    assert "--host" not in unit and "--port" not in unit
    assert "EnvironmentFile=/etc/pp-mcare.env" in unit
    assert "UMask=0077" in unit
    assert "NoNewPrivileges=true" in unit
    assert "Restart=on-failure" in unit


def test_worker_environment_example_has_only_approved_runtime_variables():
    lines = [
        line
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]

    assert lines == [
        "PP_MCARE_API_BASE_URL=https://mcare-api.whestsun.com",
        "PP_MCARE_SERVICE_TOKEN=",
        "PP_MCARE_WORKER_ID=pp-mcare-01",
        "PP_MCARE_POLL_INTERVAL_SECONDS=900",
        "PADDLE_PDX_CACHE_HOME=/opt/motioncare-analysis/model-cache",
    ]
    content = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "QINIU_ACCESS_KEY" not in content
    assert "QINIU_SECRET_KEY" not in content
    assert "DATABASE_URL" not in content
    assert "REDIS_URL" not in content


def test_bootstrap_and_installer_have_root_gates_and_no_unsafe_shell_execution():
    for script in (BOOTSTRAP_SCRIPT, INSTALL_SCRIPT, REGRESSION_SCRIPT):
        content = script.read_text(encoding="utf-8")
        assert "EUID" in content
        assert "eval " not in content
        assert "curl" not in content
        assert "rm -rf" not in content

    bootstrap = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    assert "motioncare-analysis" in bootstrap
    assert "0700" in bootstrap
    assert "model-cache" in bootstrap
    assert '_validate_directory "${ANALYSIS_ROOT}/tmp/jobs"' in bootstrap
    assert "swapon" in bootstrap


def test_install_release_verifies_artifacts_and_switches_current_atomically():
    content = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "artifact-manifest.json" in content
    assert "release-manifest.json" in content
    assert "installed_distribution_sha256" in content
    assert "python3.12 -m venv" in content
    assert "import cv2" in content
    assert "import paddle" in content
    assert "import paddlex" in content
    assert "pytest" in content
    assert "mv -T" in content
    assert "current" in content


def test_regression_script_uses_real_cli_and_create_once_report():
    content = REGRESSION_SCRIPT.read_text(encoding="utf-8")

    assert "-m pp_mcare regression" in content
    assert "--manual-total-count 90" in content
    assert "--report" in content
    assert "pp-mcare-v2-${implementation_commit}-${run_id}.json" in content
    assert "unlink" in content


def test_regression_script_cleans_validated_input_after_function_scope_ends(tmp_path):
    completed, video, _current, _cwd_log = _run_regression_with_fake_boundaries(tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert video.exists() is False
    assert "unbound variable" not in completed.stderr


def test_regression_script_runs_worker_from_current_release_directory(tmp_path):
    completed, _video, current, cwd_log = _run_regression_with_fake_boundaries(tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert cwd_log.read_text(encoding="utf-8").strip() == str(current)
