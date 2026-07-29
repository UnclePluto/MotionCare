import threading
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone

from apps.studies.models import ProjectPatient
from apps.studies.services.unbind_project_patient import unbind_project_patient
from apps.training.models import TrainingVideo, VideoAssemblyJob
from apps.training.tests.test_video_tasks import (
    _assembly_result,
    _remote_metadata,
    _video_tasks,
)


pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="需要 PostgreSQL 两连接验证 select_for_update",
    ),
]


def _database_thread(target, *, name):
    errors = []

    def runner():
        close_old_connections()
        try:
            target()
        except Exception as exc:  # pragma: no cover - surfaced by the parent assertion
            errors.append(exc)
        finally:
            close_old_connections()

    return threading.Thread(target=runner, name=name), errors


def _start_blocked_publish(
    *, module, job, result, monkeypatch, move_entered, release_move
):
    metadata = _remote_metadata(result, object_hash="published-hash")

    def blocked_move(**kwargs):
        assert kwargs["attempt_key"] == job.qiniu_attempt_object_key
        assert kwargs["canonical_key"] == job.qiniu_object_key
        move_entered.set()
        assert release_move.wait(timeout=5)
        return metadata

    monkeypatch.setattr(module, "publish_attempt_to_canonical", blocked_move)
    publish_result = []

    def publish():
        publish_result.append(
            module.publish_canonical_under_lease(
                job.id,
                lease_attempt=job.attempt_count,
                bucket="motioncare-training",
                attempt_key=job.qiniu_attempt_object_key,
                canonical_key=job.qiniu_object_key,
                expected_hash=metadata["hash"],
                expected_size_bytes=result.size_bytes,
            )
        )

    thread, errors = _database_thread(publish, name="canonical-publisher")
    thread.start()
    assert move_entered.wait(timeout=5)
    return thread, errors, publish_result


def _prepare_running_upload(
    project_patient,
    active_prescription,
    prescription_action,
    tmp_path,
    settings,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.QINIU_BUCKET = "motioncare-training"
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        actual_duration_seconds=60,
        finalized_at=timezone.now(),
        status=TrainingVideo.Status.QUEUED,
    )
    canonical_key = (
        f"training-videos/{project_patient.id}/{video.training_date:%Y/%m/%d}/"
        f"{video.client_session_id}.mp4"
    )
    job = VideoAssemblyJob.objects.create(
        training_video=video,
        qiniu_object_key=canonical_key,
    )
    module = _video_tasks()
    claimed_job, claimed = module.claim_video_assembly_job(job.id)
    assert claimed is True
    result = _assembly_result(video, duration=60.0)
    module.mark_uploading_qiniu(
        job.id,
        result,
        lease_attempt=claimed_job.attempt_count,
        attempt_key=module.qiniu_attempt_object_key(video, claimed_job.attempt_count),
        canonical_key=job.qiniu_object_key,
    )
    job.refresh_from_db()
    return module, video, job, result


def test_recovery_cannot_take_over_while_canonical_move_holds_lease_locks(
    project_patient,
    active_prescription,
    prescription_action,
    tmp_path,
    settings,
    monkeypatch,
):
    module, video, job, result = _prepare_running_upload(
        project_patient, active_prescription, prescription_action, tmp_path, settings
    )
    stale_at = timezone.now() - timedelta(
        seconds=settings.VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS + 1
    )
    VideoAssemblyJob.objects.filter(pk=job.id).update(heartbeat_at=stale_at)

    move_entered = threading.Event()
    release_move = threading.Event()
    publisher, publish_errors, publish_result = _start_blocked_publish(
        module=module,
        job=job,
        result=result,
        monkeypatch=monkeypatch,
        move_entered=move_entered,
        release_move=release_move,
    )

    recovery_done = threading.Event()
    recovered = []

    def recover():
        recovered.append(module.recover_stale_video_assembly_jobs.run())
        recovery_done.set()

    recovery, recovery_errors = _database_thread(recover, name="stale-recovery")
    recovery.start()
    assert not recovery_done.wait(timeout=0.2)

    release_move.set()
    publisher.join(timeout=5)
    recovery.join(timeout=5)

    assert not publisher.is_alive()
    assert not recovery.is_alive()
    assert publish_errors == []
    assert recovery_errors == []
    assert recovered == [0]
    assert publish_result == [_remote_metadata(result, object_hash="published-hash")]
    job.refresh_from_db()
    assert job.status == VideoAssemblyJob.Status.RUNNING
    assert job.qiniu_object_hash == "published-hash"
    assert job.heartbeat_at > stale_at


def test_unbind_waits_for_canonical_move_then_invalidates_lease_consistently(
    project_patient,
    active_prescription,
    prescription_action,
    tmp_path,
    settings,
    monkeypatch,
):
    module, video, job, result = _prepare_running_upload(
        project_patient, active_prescription, prescription_action, tmp_path, settings
    )
    move_entered = threading.Event()
    release_move = threading.Event()
    publisher, publish_errors, _ = _start_blocked_publish(
        module=module,
        job=job,
        result=result,
        monkeypatch=monkeypatch,
        move_entered=move_entered,
        release_move=release_move,
    )

    cleanup_delay = Mock()
    monkeypatch.setattr(module.cleanup_unbound_training_video, "delay", cleanup_delay)
    unbind_done = threading.Event()

    def unbind():
        locked_candidate = ProjectPatient.objects.get(pk=project_patient.pk)
        unbind_project_patient(project_patient=locked_candidate)
        unbind_done.set()

    unbinder, unbind_errors = _database_thread(unbind, name="project-unbind")
    unbinder.start()
    assert not unbind_done.wait(timeout=0.2)

    release_move.set()
    publisher.join(timeout=5)
    unbinder.join(timeout=5)

    assert not publisher.is_alive()
    assert not unbinder.is_alive()
    assert publish_errors == []
    assert unbind_errors == []
    video.refresh_from_db()
    job.refresh_from_db()
    assert video.project_patient_id is None
    assert video.cleanup_requested_at is not None
    assert job.qiniu_object_hash == "published-hash"
    cleanup_delay.assert_called_once_with(video.id)
