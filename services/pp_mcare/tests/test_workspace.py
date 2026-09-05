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
    assert list(root.iterdir()) == []


def test_workspace_creation_rolls_back_when_child_permission_step_fails(tmp_path, monkeypatch):
    root = tmp_path / "jobs"
    root.mkdir()
    original_fchmod = workspace_module.os.fchmod
    calls = 0

    def failing_child_fchmod(fd, mode):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic permission failure")
        return original_fchmod(fd, mode)

    monkeypatch.setattr(workspace_module.os, "fchmod", failing_child_fchmod)
    with pytest.raises(OSError):
        TaskWorkspace.create(root, 14)

    assert list(root.iterdir()) == []


def test_workspace_holds_directory_identity_across_parent_replacement(tmp_path):
    root = tmp_path / "jobs"
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = TaskWorkspace.create(root, 13)
    original = workspace.path.with_name("saved-original")
    workspace.path.rename(original)
    workspace.path.symlink_to(outside, target_is_directory=True)

    fd = workspace.create_file("original.mp4")
    os.write(fd, b"private")
    os.close(fd)
    workspace.cleanup()

    assert list(root.iterdir()) == []
    assert list(outside.iterdir()) == []


def test_stale_cleanup_cursor_prevents_prefix_starvation(tmp_path):
    root = tmp_path / "jobs"
    root.mkdir(mode=0o700)
    for index in range(24):
        (root / f"aaa-unrelated-{index:02d}").mkdir()
    old = root / f"job-99-{'d' * 32}"
    old.mkdir(mode=0o700)
    os.utime(old, (1, 1))

    for _ in range(8):
        cleanup_stale_workspaces(root, max_age_seconds=10, limit=2, now=time.time())
        if not old.exists():
            break

    assert not old.exists()
    cursor = root / ".pp-mcare-cleanup-cursor"
    assert cursor.is_file()
    assert stat.S_IMODE(cursor.stat().st_mode) == 0o600


def test_stale_cleanup_rechecks_age_after_open(tmp_path, monkeypatch):
    root = tmp_path / "jobs"
    root.mkdir(mode=0o700)
    name = f"job-88-{'e' * 32}"
    candidate = root / name
    candidate.mkdir(mode=0o700)
    os.utime(candidate, (1, 1))
    original_open = workspace_module.os.open

    def touching_open(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        if path == name and kwargs.get("dir_fd") is not None:
            os.utime(candidate, None)
        return fd

    monkeypatch.setattr(workspace_module.os, "open", touching_open)
    result = cleanup_stale_workspaces(root, max_age_seconds=10, limit=2, now=time.time())

    assert candidate.exists()
    assert result.removed == 0


@pytest.mark.parametrize("cursor_kind", ["directory", "symlink"])
def test_damaged_cursor_is_advisory_and_never_blocks_cleanup(tmp_path, cursor_kind):
    root = tmp_path / "jobs"
    root.mkdir(mode=0o700)
    old = root / f"job-91-{'f' * 32}"
    old.mkdir(mode=0o700)
    os.utime(old, (1, 1))
    cursor = root / ".pp-mcare-cleanup-cursor"
    outside = tmp_path / "outside"
    outside.write_text("do-not-touch")
    if cursor_kind == "directory":
        cursor.mkdir()
    else:
        cursor.symlink_to(outside)

    result = cleanup_stale_workspaces(root, max_age_seconds=10, limit=2, now=time.time())

    assert not old.exists()
    assert result.removed == 1
    assert result.failed >= 1
    assert outside.read_text() == "do-not-touch"
    assert not list(root.glob(".cleanup-cursor-*.tmp"))
    assert stat.S_ISREG(cursor.lstat().st_mode)


def test_cursor_write_failure_is_advisory_and_cleans_owned_temp(tmp_path, monkeypatch):
    root = tmp_path / "jobs"
    root.mkdir(mode=0o700)
    old = root / f"job-92-{'a' * 32}"
    old.mkdir(mode=0o700)
    os.utime(old, (1, 1))
    original_write = workspace_module.os.write

    def fail_cursor_write(fd, data):
        if data.startswith(b"job-"):
            raise OSError("cursor storage unavailable")
        return original_write(fd, data)

    monkeypatch.setattr(workspace_module.os, "write", fail_cursor_write)
    result = cleanup_stale_workspaces(root, max_age_seconds=10, limit=2, now=time.time())

    assert not old.exists()
    assert result.removed == 1
    assert result.failed == 1
    assert not list(root.glob(".cleanup-cursor-*.tmp"))


def test_cursor_replace_failure_is_advisory_and_cleans_owned_temp(tmp_path, monkeypatch):
    root = tmp_path / "jobs"
    root.mkdir(mode=0o700)
    old = root / f"job-94-{'b' * 32}"
    old.mkdir(mode=0o700)
    os.utime(old, (1, 1))
    original_replace = workspace_module.os.replace

    def fail_cursor_replace(source, destination, **kwargs):
        if destination == ".pp-mcare-cleanup-cursor":
            raise OSError("cursor replace unavailable")
        return original_replace(source, destination, **kwargs)

    monkeypatch.setattr(workspace_module.os, "replace", fail_cursor_replace)
    result = cleanup_stale_workspaces(root, max_age_seconds=10, limit=2, now=time.time())

    assert not old.exists()
    assert result.removed == 1
    assert result.failed == 1
    assert not list(root.glob(".cleanup-cursor-*.tmp"))


def test_nonregular_cursor_inode_is_advisory(tmp_path):
    root = tmp_path / "jobs"
    root.mkdir(mode=0o700)
    old = root / f"job-95-{'c' * 32}"
    old.mkdir(mode=0o700)
    os.utime(old, (1, 1))
    cursor = root / ".pp-mcare-cleanup-cursor"
    os.mkfifo(cursor, mode=0o600)
    writer = os.open(cursor, os.O_RDWR | os.O_NONBLOCK)
    try:
        result = cleanup_stale_workspaces(root, max_age_seconds=10, limit=2, now=time.time())
    finally:
        os.close(writer)

    assert not old.exists()
    assert result.removed == 1
    assert result.failed >= 1
    assert not list(root.glob(".cleanup-cursor-*.tmp"))


def test_creation_rollback_tracks_renamed_owned_directory_without_inode_scan(tmp_path, monkeypatch):
    root = tmp_path / "jobs"
    outside = tmp_path / "outside"
    outside.mkdir()
    original_fchmod = workspace_module.os.fchmod
    calls = 0

    def rename_then_fail(fd, mode):
        nonlocal calls
        calls += 1
        if calls == 2:
            created = next(root.glob("job-*"))
            created.rename(root / "attacker-chosen-name")
            created.symlink_to(outside, target_is_directory=True)
            raise OSError("permission setup failed")
        return original_fchmod(fd, mode)

    monkeypatch.setattr(workspace_module.os, "fchmod", rename_then_fail)
    with pytest.raises(OSError):
        TaskWorkspace.create(root, 93)

    assert list(root.iterdir()) == []
    assert list(outside.iterdir()) == []


def test_creation_rollback_tracks_directory_renamed_before_open(tmp_path, monkeypatch):
    root = tmp_path / "jobs"
    outside = tmp_path / "outside"
    outside.mkdir()
    original_open = workspace_module.os.open
    attacked = False

    def rename_before_open(path, flags, *args, **kwargs):
        nonlocal attacked
        if not attacked and isinstance(path, str) and path.startswith("job-"):
            attacked = True
            created = root / path
            created.rename(root / "attacker-chosen-name")
            created.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(workspace_module.os, "open", rename_before_open)
    with pytest.raises(OSError):
        TaskWorkspace.create(root, 96)

    assert list(root.iterdir()) == []
    assert list(outside.iterdir()) == []
