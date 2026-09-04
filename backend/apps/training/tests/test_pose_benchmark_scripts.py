import os
import stat
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[4]
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "deploy/motion-analysis-smoke/bootstrap.sh"
RUN_SCRIPT = PROJECT_ROOT / "deploy/motion-analysis-smoke/run-benchmark.sh"


def _run_sourced(script, command, *arguments, env=None):
    return subprocess.run(
        ["bash", "-c", f'source "$1"; {command}', "shell-test", str(script), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _bootstrap_validation_environment(
    tmp_path,
    *,
    analysis_root,
    swap_path,
    invalid_path=None,
    invalid_field=None,
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    marker = tmp_path / "write-attempted"
    _write_executable(
        fake_bin / "getent",
        "#!/bin/sh\n"
        "printf 'motioncare-analysis:x:500:500::%s:/usr/sbin/nologin\\n' "
        '"$ANALYSIS_ROOT"\n',
    )
    _write_executable(
        fake_bin / "stat",
        "#!/bin/sh\n"
        'format="$2"\n'
        'path="$4"\n'
        'if [ "$path" = "$SWAP_PATH" ]; then\n'
        "  uid=0; gid=0; mode=600; links=1; size=4294967296\n"
        'elif [ "$path" = "$ANALYSIS_ROOT" ] || '
        '[ "$path" = "$ANALYSIS_ROOT/app" ]; then\n'
        "  uid=0; gid=500; mode=750; links=1; size=0\n"
        "else\n"
        "  uid=500; gid=500; mode=700; links=1; size=0\n"
        "fi\n"
        'if [ -n "${INVALID_PATH:-}" ] && [ "$path" = "$INVALID_PATH" ]; then\n'
        '  case "${INVALID_FIELD:-}" in\n'
        "    owner) uid=123 ;;\n"
        "    group) gid=123 ;;\n"
        "    mode) mode=777 ;;\n"
        "    links) links=2 ;;\n"
        "    size) size=1 ;;\n"
        "  esac\n"
        "fi\n"
        'case "$format" in\n'
        "  '%u:%g:%a') printf '%s:%s:%s\\n' \"$uid\" \"$gid\" \"$mode\" ;;\n"
        "  '%u:%g:%a:%h:%s') printf '%s:%s:%s:%s:%s\\n' "
        '"$uid" "$gid" "$mode" "$links" "$size" ;;\n'
        "  *) exit 98 ;;\n"
        "esac\n",
    )
    _write_executable(
        fake_bin / "apt-get",
        '#!/bin/sh\n: > "$WRITE_MARKER"\nexit 77\n',
    )
    login_defs = tmp_path / "login.defs"
    login_defs.write_text("SYS_UID_MIN 100\nSYS_UID_MAX 999\n", encoding="utf-8")
    env = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "ANALYSIS_ROOT": str(analysis_root),
        "SWAP_PATH": str(swap_path),
        "INVALID_PATH": "" if invalid_path is None else str(invalid_path),
        "INVALID_FIELD": "" if invalid_field is None else invalid_field,
        "WRITE_MARKER": str(marker),
    }
    return env, marker, login_defs


def test_shell_scripts_can_be_sourced_without_running_privileged_entrypoints():
    completed = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; source "$2"',
            "shell-source-test",
            str(BOOTSTRAP_SCRIPT),
            str(RUN_SCRIPT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""


@pytest.mark.parametrize(
    "arguments",
    [
        ("invalid-commit", "20260903T120000Z"),
        ("abc1234", "invalid-run-id"),
    ],
)
def test_run_script_deletes_fixed_input_when_parameter_validation_fails(
    tmp_path,
    arguments,
):
    video = tmp_path / "input" / "IMG_0383_SDR_5min.mp4"
    video.parent.mkdir()
    video.write_bytes(b"private video")

    completed = _run_sourced(
        RUN_SCRIPT,
        '_run_benchmark_after_root_gate "$2" "$3" "$4"',
        str(tmp_path),
        *arguments,
    )

    assert completed.returncode == 2
    assert not video.exists()


def test_run_script_invokes_runuser_from_deployed_backend_directory(tmp_path):
    analysis_root = tmp_path / "analysis"
    backend_directory = analysis_root / "app" / "backend"
    backend_directory.mkdir(parents=True)
    video = analysis_root / "input" / "IMG_0383_SDR_5min.mp4"
    video.parent.mkdir()
    video.write_bytes(b"private video")
    caller_directory = tmp_path / "caller"
    caller_directory.mkdir()

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    cwd_record = tmp_path / "runuser-cwd"
    args_record = tmp_path / "runuser-args"
    _write_executable(
        fake_bin / "runuser",
        '#!/bin/sh\npwd > "$CWD_RECORD"\nprintf "%s\\n" "$@" > "$ARGS_RECORD"\n',
    )
    env = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "CWD_RECORD": str(cwd_record),
        "ARGS_RECORD": str(args_record),
        "CALLER_DIRECTORY": str(caller_directory),
    }

    completed = _run_sourced(
        RUN_SCRIPT,
        'cd "$CALLER_DIRECTORY"; '
        '_run_benchmark_after_root_gate "$2" abc1234 20260903T120000Z',
        str(analysis_root),
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert cwd_record.read_text(encoding="utf-8").strip() == str(backend_directory)
    arguments = args_record.read_text(encoding="utf-8").splitlines()
    manual_count_index = arguments.index("--manual-total-count")
    assert arguments[manual_count_index : manual_count_index + 2] == [
        "--manual-total-count",
        "90",
    ]
    expected_prefix = str(analysis_root / "reports" / "pp-tinypose-v2-")
    assert f"{expected_prefix}20260903T120000Z.json" in arguments
    assert f"{expected_prefix}20260903T120000Z.txt" in arguments
    assert "pp-tinypose-smoke-" not in completed.stdout
    assert not video.exists()


def test_run_script_deletes_fixed_input_when_benchmark_command_fails(tmp_path):
    analysis_root = tmp_path / "analysis"
    (analysis_root / "app" / "backend").mkdir(parents=True)
    video = analysis_root / "input" / "IMG_0383_SDR_5min.mp4"
    video.parent.mkdir()
    video.write_bytes(b"private video")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "runuser", "#!/bin/sh\nexit 7\n")
    env = os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

    completed = _run_sourced(
        RUN_SCRIPT,
        '_run_benchmark_after_root_gate "$2" abc1234 20260903T120000Z',
        str(analysis_root),
        env=env,
    )

    assert completed.returncode == 7
    assert not video.exists()


@pytest.mark.parametrize(
    "unsafe_kind",
    ["analysis_symlink", "analysis_file", "swap_symlink", "swap_dir"],
)
def test_bootstrap_rejects_unsafe_existing_paths_before_writes(tmp_path, unsafe_kind):
    analysis_root = tmp_path / "analysis"
    swap_path = tmp_path / "swapfile"
    if unsafe_kind == "analysis_symlink":
        target = tmp_path / "analysis-target"
        target.mkdir()
        analysis_root.symlink_to(target, target_is_directory=True)
    elif unsafe_kind == "analysis_file":
        analysis_root.write_text("not a directory", encoding="utf-8")
    elif unsafe_kind == "swap_symlink":
        target = tmp_path / "swap-target"
        target.write_bytes(b"target")
        swap_path.symlink_to(target)
    else:
        swap_path.mkdir()

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "write-attempted"
    _write_executable(
        fake_bin / "apt-get",
        '#!/bin/sh\n: > "$WRITE_MARKER"\nexit 77\n',
    )
    login_defs = tmp_path / "login.defs"
    login_defs.write_text("SYS_UID_MIN 100\nSYS_UID_MAX 999\n", encoding="utf-8")
    env = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "WRITE_MARKER": str(marker),
    }

    completed = _run_sourced(
        BOOTSTRAP_SCRIPT,
        '_bootstrap_after_root_gate "$2" "$3" "$4"',
        str(analysis_root),
        str(swap_path),
        str(login_defs),
        env=env,
    )

    assert completed.returncode == 1
    assert not marker.exists()


@pytest.mark.parametrize(
    "relative_path",
    ["app", "model-cache", "input", "tmp", "reports", "logs", "venv"],
)
def test_bootstrap_rejects_each_managed_child_symlink_before_writes(
    tmp_path,
    relative_path,
):
    analysis_root = tmp_path / "analysis"
    analysis_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (analysis_root / relative_path).symlink_to(outside, target_is_directory=True)
    swap_path = tmp_path / "swapfile"
    env, marker, login_defs = _bootstrap_validation_environment(
        tmp_path,
        analysis_root=analysis_root,
        swap_path=swap_path,
    )

    completed = _run_sourced(
        BOOTSTRAP_SCRIPT,
        '_bootstrap_after_root_gate "$2" "$3" "$4"',
        str(analysis_root),
        str(swap_path),
        str(login_defs),
        env=env,
    )

    assert completed.returncode == 1
    assert not marker.exists()


@pytest.mark.parametrize(
    ("relative_path", "invalid_field"),
    [
        (relative_path, invalid_field)
        for relative_path in (
            None,
            "app",
            "model-cache",
            "input",
            "tmp",
            "reports",
            "logs",
            "venv",
        )
        for invalid_field in ("owner", "group", "mode")
    ],
)
def test_bootstrap_rejects_managed_directory_metadata_before_writes(
    tmp_path,
    relative_path,
    invalid_field,
):
    analysis_root = tmp_path / "analysis"
    for child in ("app", "model-cache", "input", "tmp", "reports", "logs", "venv"):
        (analysis_root / child).mkdir(parents=True, exist_ok=True)
    invalid_path = analysis_root if relative_path is None else analysis_root / relative_path
    swap_path = tmp_path / "swapfile"
    env, marker, login_defs = _bootstrap_validation_environment(
        tmp_path,
        analysis_root=analysis_root,
        swap_path=swap_path,
        invalid_path=invalid_path,
        invalid_field=invalid_field,
    )

    completed = _run_sourced(
        BOOTSTRAP_SCRIPT,
        '_bootstrap_after_root_gate "$2" "$3" "$4"',
        str(analysis_root),
        str(swap_path),
        str(login_defs),
        env=env,
    )

    assert completed.returncode == 1
    assert not marker.exists()


@pytest.mark.parametrize("invalid_field", ["owner", "group", "mode", "links", "size"])
def test_bootstrap_rejects_unsafe_existing_swap_metadata_before_writes(
    tmp_path,
    invalid_field,
):
    analysis_root = tmp_path / "analysis"
    swap_path = tmp_path / "swapfile"
    swap_path.write_bytes(b"existing swap")
    env, marker, login_defs = _bootstrap_validation_environment(
        tmp_path,
        analysis_root=analysis_root,
        swap_path=swap_path,
        invalid_path=swap_path,
        invalid_field=invalid_field,
    )

    completed = _run_sourced(
        BOOTSTRAP_SCRIPT,
        '_bootstrap_after_root_gate "$2" "$3" "$4"',
        str(analysis_root),
        str(swap_path),
        str(login_defs),
        env=env,
    )

    assert completed.returncode == 1
    assert not marker.exists()


@pytest.mark.parametrize(
    ("uid", "home_kind", "account_shell"),
    [
        (99, "expected", "/usr/sbin/nologin"),
        (1000, "expected", "/usr/sbin/nologin"),
        (999, "wrong", "/usr/sbin/nologin"),
        (999, "expected", "/bin/bash"),
    ],
)
def test_bootstrap_rejects_mismatched_existing_service_account_before_writes(
    tmp_path,
    uid,
    home_kind,
    account_shell,
):
    analysis_root = tmp_path / "analysis"
    account_home = analysis_root if home_kind == "expected" else tmp_path / "wrong-home"
    passwd_entry = (
        f"motioncare-analysis:x:{uid}:{uid}::{account_home}:{account_shell}"
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "write-attempted"
    _write_executable(
        fake_bin / "getent",
        '#!/bin/sh\nprintf "%s\\n" "$PASSWD_ENTRY"\n',
    )
    _write_executable(
        fake_bin / "apt-get",
        '#!/bin/sh\n: > "$WRITE_MARKER"\nexit 77\n',
    )
    login_defs = tmp_path / "login.defs"
    login_defs.write_text("SYS_UID_MIN 100\nSYS_UID_MAX 999\n", encoding="utf-8")
    env = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "PASSWD_ENTRY": passwd_entry,
        "WRITE_MARKER": str(marker),
    }

    completed = _run_sourced(
        BOOTSTRAP_SCRIPT,
        '_bootstrap_after_root_gate "$2" "$3" "$4"',
        str(analysis_root),
        str(tmp_path / "swapfile"),
        str(login_defs),
        env=env,
    )

    assert completed.returncode == 1
    assert not marker.exists()


def test_bootstrap_creates_swap_as_restricted_regular_file_without_temporary_files(tmp_path):
    swap_path = tmp_path / "swapfile"
    completed = _run_sourced(
        BOOTSTRAP_SCRIPT,
        'fallocate() { truncate -s 4294967296 "${@: -1}"; }; '
        'mkswap() { :; }; _create_swap_file "$2"',
        str(swap_path),
    )

    assert completed.returncode == 0, completed.stderr
    assert swap_path.is_file()
    assert not swap_path.is_symlink()
    assert swap_path.stat().st_size == 4294967296
    assert stat.S_IMODE(swap_path.stat().st_mode) == 0o600
    assert list(tmp_path.glob("swapfile.tmp.*")) == []


def test_bootstrap_atomic_swap_placement_does_not_overwrite_racing_target(tmp_path):
    swap_path = tmp_path / "swapfile"
    env = os.environ | {"SWAP_TARGET": str(swap_path)}
    completed = _run_sourced(
        BOOTSTRAP_SCRIPT,
        'fallocate() { truncate -s 4294967296 "${@: -1}"; '
        'printf preserved > "$SWAP_TARGET"; }; '
        'mkswap() { :; }; _create_swap_file "$2"',
        str(swap_path),
        env=env,
    )

    assert completed.returncode == 1
    assert swap_path.read_text(encoding="utf-8") == "preserved"
    assert list(tmp_path.glob("swapfile.tmp.*")) == []
