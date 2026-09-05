import os
import stat
import time

import pytest

import pp_mcare.workspace as workspace_module
from pp_mcare.workspace import TaskWorkspace, cleanup_stale_workspaces


def test_task_workspace_cleans_everything_on_exception_and_baseexception(tmp_path):
    for error in (RuntimeError("boom"), KeyboardInterrupt()):
        with pytest.raises(type(error)):
            with TaskWorkspace.create(tmp_path, 42) as workspace:
                workspace.input_path.write_bytes(b"private")
                workspace.output_path.write_bytes(b"published")
                raise error
        assert list(tmp_path.iterdir()) == []


def test_task_workspace_is_private_unique_and_rejects_bad_job_ids(tmp_path):
    first = TaskWorkspace.create(tmp_path, 1)
    second = TaskWorkspace.create(tmp_path, 1)
    try:
        assert first.path != second.path
        assert first.path.name.startswith("job-1-")
        assert stat.S_IMODE(first.path.stat().st_mode) == 0o700
    finally:
        first.cleanup()
        second.cleanup()

    for bad in (0, -1, True, "1"):
        with pytest.raises((TypeError, ValueError)):
            TaskWorkspace.create(tmp_path, bad)


def test_cleanup_never_follows_symlinks_or_deletes_external_hardlink_content(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.mp4"
    secret.write_bytes(b"patient")

    with TaskWorkspace.create(tmp_path / "jobs", 7) as workspace:
        (workspace.path / "outside-link").symlink_to(outside, target_is_directory=True)
        os.link(secret, workspace.path / "hard-link")

    assert secret.read_bytes() == b"patient"
    assert list(outside.iterdir()) == [secret]


def test_startup_cleanup_is_strict_old_and_bounded(tmp_path):
    root = tmp_path / "jobs"
    root.mkdir(mode=0o700)
    old_names = [f"job-{number}-{'a' * 32}" for number in range(1, 4)]
    for name in old_names:
        path = root / name
        path.mkdir(mode=0o700)
        os.utime(path, (1, 1))
    fresh = root / f"job-9-{'b' * 32}"
    fresh.mkdir(mode=0o700)
    outsider = tmp_path / "outside"
    outsider.mkdir()
    link = root / f"job-10-{'c' * 32}"
    link.symlink_to(outsider, target_is_directory=True)
    (root / "unrelated").mkdir()

    result = cleanup_stale_workspaces(root, max_age_seconds=10, limit=2, now=time.time())

    assert result.scanned <= 4
    assert result.removed == 2
    assert fresh.exists()
    assert link.is_symlink()
    assert (root / "unrelated").exists()
    assert outsider.exists()


def test_workspace_creation_rejects_root_symlink(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "jobs"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(OSError):
        TaskWorkspace.create(link, 1)

    assert list(real.iterdir()) == []


def test_workspace_creation_detects_leaf_replacement_race(tmp_path, monkeypatch):
    root = tmp_path / "jobs"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    original_mkdir = workspace_module.os.mkdir

    def racing_mkdir(path, mode=0o777, *, dir_fd=None):
        result = original_mkdir(path, mode=mode, dir_fd=dir_fd)
        if dir_fd is not None and isinstance(path, str) and path.startswith("job-"):
            full_path = root / path
            full_path.rmdir()
            full_path.symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(workspace_module.os, "mkdir", racing_mkdir)
    with pytest.raises(OSError):
        TaskWorkspace.create(root, 12)

    assert list(outside.iterdir()) == []
