from datetime import timedelta
from unittest.mock import Mock

import pytest
from celery.exceptions import Retry
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError
from django.utils import timezone
from kombu.serialization import dumps

from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.training.models import (
    QiniuCleanupTombstone,
    TrainingRecord,
    TrainingVideo,
    TrainingVideoSegment,
    VideoAssemblyJob,
)
from apps.training.video_assembly import AssemblyResult, VideoProbe
from apps.training.video_staging import segment_path, session_root


def _video_tasks():
    from apps.training import video_tasks

    return video_tasks


def test_video_assembly_job_task_routes_to_dedicated_queue():
    from config.celery import app as celery_app
    from apps.training import tasks as training_tasks

    module = _video_tasks()
    task_name = module.run_video_assembly_job.name

    assert task_name == "apps.training.video_tasks.run_video_assembly_job"
    route = celery_app.amqp.router.route({}, task_name, args=(), kwargs={})
    assert route["queue"].name == "video-assembly"

    default_queue_tasks = [
        module.cleanup_training_video_files,
        module.cleanup_unbound_training_video,
        module.cleanup_qiniu_tombstones,
        module.recover_training_video_cleanup,
        module.expire_stale_training_video_sessions,
        module.recover_stale_video_assembly_jobs,
        training_tasks.run_motion_analysis_job,
        training_tasks.recover_stale_motion_analysis_jobs,
    ]
    for task in default_queue_tasks:
        route = celery_app.amqp.router.route({}, task.name, args=(), kwargs={})
        assert route["queue"].name == "celery"


@pytest.mark.django_db
def test_video_assembly_task_returns_json_serializable_job_summary(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    _, job = _pending_job(project_patient, active_prescription, tmp_path)
    job.status = VideoAssemblyJob.Status.SUCCEEDED
    job.save(update_fields=["status", "updated_at"])

    result = _video_tasks().run_video_assembly_job.run(job.id)

    assert result == {
        "job_id": job.id,
        "status": VideoAssemblyJob.Status.SUCCEEDED,
    }
    dumps(result, serializer="json")


def _shoulder_press_action(prescription):
    item = ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press")
    return prescription.add_action_snapshot(
        item,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=10,
    )


def _pending_job(
    project_patient,
    active_prescription,
    tmp_path,
    *,
    duration=61,
    segment_count=2,
    segment_duration_ms=None,
):
    action = _shoulder_press_action(active_prescription)
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate() - timedelta(days=1),
        note="训练备注",
        expected_duration_seconds=duration,
        actual_duration_seconds=duration,
        expected_segment_count=segment_count,
        uploaded_segment_count=segment_count,
        finalized_at=timezone.now(),
        status=TrainingVideo.Status.QUEUED,
    )
    if segment_duration_ms is None:
        segment_duration_ms = (duration * 1000) // segment_count
    rows = []
    for index in range(segment_count):
        path = segment_path(video, index)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        rows.append(
            TrainingVideoSegment(
                training_video=video,
                index=index,
                duration_ms=segment_duration_ms,
                size_bytes=path.stat().st_size,
                sha256=f"{index:064x}",
                relative_path=path.relative_to(tmp_path).as_posix(),
                status=TrainingVideoSegment.Status.UPLOADED,
                uploaded_at=timezone.now(),
            )
        )
    TrainingVideoSegment.objects.bulk_create(rows)
    key = (
        f"training-videos/{project_patient.id}/{video.training_date:%Y/%m/%d}/"
        f"{video.client_session_id}.mp4"
    )
    job = VideoAssemblyJob.objects.create(
        training_video=video,
        qiniu_object_key=key,
    )
    return video, job


def _assembly_result(video, *, duration=61.0):
    output = session_root(video) / "working" / "final.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"assembled-video")
    return AssemblyResult(
        output_path=output,
        probe=VideoProbe(
            duration_seconds=duration,
            width=640,
            height=480,
            video_codec="h264",
            audio_codec="aac",
        ),
        size_bytes=output.stat().st_size,
        transcoded=False,
    )


def _remote_metadata(result, *, object_hash="qiniu-hash"):
    return {
        "hash": object_hash,
        "fsize": result.size_bytes,
        "mimeType": "video/mp4",
    }


@pytest.mark.django_db
def test_process_job_attaches_one_historical_training_record_after_upload(
    project_patient,
    doctor,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.QINIU_BUCKET = "motioncare-training"
    video, job = _pending_job(project_patient, active_prescription, tmp_path)
    original_action = video.prescription_action
    active_prescription.status = Prescription.Status.ARCHIVED
    active_prescription.save(update_fields=["status", "updated_at"])
    Prescription.objects.create(
        project_patient=project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    result = _assembly_result(video)
    assemble = Mock(return_value=result)
    upload = Mock(return_value=_remote_metadata(result))
    cleanup_delay = Mock()
    tombstone_delay = Mock()
    module = _video_tasks()
    monkeypatch.setattr(module, "assemble_video", assemble)
    monkeypatch.setattr(module, "upload_and_publish_local_video", upload)
    monkeypatch.setattr(module.cleanup_training_video_files, "delay", cleanup_delay)
    monkeypatch.setattr(module.cleanup_qiniu_tombstone, "delay", tombstone_delay)

    with django_capture_on_commit_callbacks(execute=True):
        attached = module.process_video_assembly_job(job.id)
        duplicate = module.process_video_assembly_job(job.id)

    video.refresh_from_db()
    job.refresh_from_db()
    record = TrainingRecord.objects.get()
    assert attached.id == duplicate.id == job.id
    assert TrainingRecord.objects.count() == 1
    assert record.project_patient == project_patient
    assert record.prescription == active_prescription
    assert record.prescription_action == original_action
    assert record.training_date == video.training_date
    assert record.actual_duration_minutes == 2
    assert record.status == TrainingRecord.Status.COMPLETED
    assert record.note == "训练备注"
    assert record.form_data == {
        "video_id": video.id,
        "video_object_key": job.qiniu_object_key,
    }
    assert video.training_record == record
    assert video.status == TrainingVideo.Status.ATTACHED
    assert video.bucket == "motioncare-training"
    assert video.object_key == job.qiniu_object_key
    tombstone = QiniuCleanupTombstone.objects.get(session_id=video.client_session_id)
    assert tombstone.bucket == "motioncare-training"
    assert tombstone.canonical_key == job.qiniu_object_key
    assert tombstone.retain_canonical is True
    assert tombstone.max_attempt_number == 1
    assert "project_patient" not in {field.name for field in tombstone._meta.fields}
    assemble.assert_called_once()
    upload.assert_called_once()
    cleanup_delay.assert_called_once_with(job.id)
    tombstone_delay.assert_called_once_with(tombstone.id)


@pytest.mark.django_db
def test_process_job_assembles_360_ordered_segments_once(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.QINIU_BUCKET = "motioncare-training"
    video, job = _pending_job(
        project_patient,
        active_prescription,
        tmp_path,
        duration=1_800,
        segment_count=360,
        segment_duration_ms=5_000,
    )
    result = _assembly_result(video, duration=1_800)
    assemble = Mock(return_value=result)
    upload = Mock(return_value=_remote_metadata(result))
    cleanup_delay = Mock()
    tombstone_delay = Mock()
    module = _video_tasks()
    monkeypatch.setattr(module, "assemble_video", assemble)
    monkeypatch.setattr(module, "upload_and_publish_local_video", upload)
    monkeypatch.setattr(module.cleanup_training_video_files, "delay", cleanup_delay)
    monkeypatch.setattr(module.cleanup_qiniu_tombstone, "delay", tombstone_delay)

    with django_capture_on_commit_callbacks(execute=True):
        first = module.process_video_assembly_job(job.id)
        second = module.process_video_assembly_job(job.id)

    expected_paths = [segment_path(video, index) for index in range(360)]
    assert assemble.call_args.args[0] == expected_paths
    assert TrainingRecord.objects.count() == 1
    assert TrainingRecord.objects.get().actual_duration_minutes == 30
    job.refresh_from_db()
    assert first.id == second.id == job.id
    assert job.status == VideoAssemblyJob.Status.SUCCEEDED
    assemble.assert_called_once()
    upload.assert_called_once()
    cleanup_delay.assert_called_once_with(job.id)
    tombstone_delay.assert_called_once()


@pytest.mark.django_db
def test_oversized_assembly_result_enters_existing_failure_flow_without_upload(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.TRAINING_VIDEO_MAX_SIZE_BYTES = 536_870_912
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    result = _assembly_result(video, duration=60.0)
    result = AssemblyResult(
        output_path=result.output_path,
        probe=result.probe,
        size_bytes=536_870_913,
        transcoded=False,
    )
    module = _video_tasks()
    assemble = Mock(return_value=result)
    upload = Mock()
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(module, "assemble_video", assemble)
    monkeypatch.setattr(module, "upload_and_publish_local_video", upload)
    monkeypatch.setattr(module.run_video_assembly_job, "retry", retry)

    with pytest.raises(Retry):
        module.run_video_assembly_job.run(job.id)
    with pytest.raises(Retry):
        module.run_video_assembly_job.run(job.id)
    final = module.run_video_assembly_job.run(job.id)

    job.refresh_from_db()
    video.refresh_from_db()
    assert final == {"job_id": job.id, "status": VideoAssemblyJob.Status.FAILED}
    assert job.status == VideoAssemblyJob.Status.FAILED
    assert video.status == TrainingVideo.Status.FAILED
    assert video.size_bytes == 0
    assert upload.call_count == 0


@pytest.mark.django_db
def test_existing_verified_final_and_qiniu_object_skip_reassembly_and_duplicate_record(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    result = _assembly_result(video, duration=60.0)
    job.output_relative_path = result.output_path.relative_to(tmp_path).as_posix()
    job.save(update_fields=["output_relative_path", "updated_at"])
    video.size_bytes = result.size_bytes
    video.duration_seconds = 60
    video.save(update_fields=["size_bytes", "duration_seconds", "updated_at"])
    module = _video_tasks()
    assemble = Mock()
    upload = Mock(return_value=_remote_metadata(result, object_hash="existing-hash"))
    monkeypatch.setattr(module, "assemble_video", assemble)
    monkeypatch.setattr(module, "probe_video", Mock(return_value=result.probe))
    monkeypatch.setattr(module, "upload_and_publish_local_video", upload)
    monkeypatch.setattr(module.cleanup_training_video_files, "delay", Mock())

    module.process_video_assembly_job(job.id)
    module.process_video_assembly_job(job.id)

    assert TrainingRecord.objects.count() == 1
    assemble.assert_not_called()
    upload.assert_called_once()


@pytest.mark.django_db
def test_qiniu_failure_reuses_final_file_and_stops_after_three_attempts(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    result = _assembly_result(video, duration=60.0)
    module = _video_tasks()
    assemble = Mock(return_value=result)
    upload = Mock(side_effect=ValidationError("七牛网络失败 /secret/local/path"))
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(module, "assemble_video", assemble)
    monkeypatch.setattr(module, "probe_video", Mock(return_value=result.probe))
    monkeypatch.setattr(module, "upload_and_publish_local_video", upload)
    monkeypatch.setattr(module.run_video_assembly_job, "retry", retry)

    with pytest.raises(Retry):
        module.run_video_assembly_job.run(job.id)
    with pytest.raises(Retry):
        module.run_video_assembly_job.run(job.id)
    final = module.run_video_assembly_job.run(job.id)

    job.refresh_from_db()
    video.refresh_from_db()
    assert final == {
        "job_id": job.id,
        "status": VideoAssemblyJob.Status.FAILED,
    }
    assert job.status == VideoAssemblyJob.Status.FAILED
    assert job.attempt_count == 3
    assert video.status == TrainingVideo.Status.FAILED
    assert result.output_path.is_file()
    assert all(path.is_file() for path in session_root(video).glob("segments/*.mp4"))
    assert "/secret/local/path" not in job.failure_reason
    assert len(job.failure_reason) <= 2000
    assert assemble.call_count == 1
    assert upload.call_count == 3
    assert retry.call_count == 2
    assert [call.kwargs["countdown"] for call in retry.call_args_list] == [60, 120]


@pytest.mark.django_db
def test_cleanup_failure_only_marks_cleanup_and_keeps_attached_record(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=video.prescription_action,
        training_date=video.training_date,
        status=TrainingRecord.Status.COMPLETED,
    )
    video.training_record = record
    video.status = TrainingVideo.Status.ATTACHED
    video.object_key = job.qiniu_object_key
    video.save(update_fields=["training_record", "status", "object_key", "updated_at"])
    module = _video_tasks()
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(
        module,
        "_remove_session_files",
        Mock(side_effect=RuntimeError("quarantine delete failed")),
    )
    monkeypatch.setattr(module.cleanup_training_video_files, "retry", retry)

    with pytest.raises(Retry):
        module.cleanup_training_video_files.run(job.id)

    job.refresh_from_db()
    video.refresh_from_db()
    assert job.cleanup_status == VideoAssemblyJob.CleanupStatus.FAILED
    assert job.cleanup_attempt_count == 1
    assert video.status == TrainingVideo.Status.ATTACHED
    assert video.training_record == record
    assert TrainingRecord.objects.filter(pk=record.id).exists()


@pytest.mark.django_db
def test_cleanup_success_removes_attached_session_and_is_idempotent(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=video.prescription_action,
        training_date=video.training_date,
        status=TrainingRecord.Status.COMPLETED,
    )
    module = _video_tasks()
    current_key = module.qiniu_attempt_object_key(video, 2)
    old_key = module.qiniu_attempt_object_key(video, 1)
    job.attempt_count = 2
    job.qiniu_object_key = current_key
    job.save()
    video.training_record = record
    video.status = TrainingVideo.Status.ATTACHED
    video.object_key = current_key
    video.save(update_fields=["training_record", "status", "object_key", "updated_at"])
    (session_root(video) / "working").mkdir(parents=True, exist_ok=True)
    (session_root(video) / "working" / "final.mp4").write_bytes(b"final")
    delete = Mock()
    tombstone_delay = Mock()
    monkeypatch.setattr(
        module,
        "stat_object_metadata_or_none",
        Mock(return_value={"hash": "old", "fsize": 1, "mimeType": "video/mp4"}),
    )
    monkeypatch.setattr(module, "delete_object_if_exists", delete)
    monkeypatch.setattr(module.cleanup_qiniu_tombstone, "delay", tombstone_delay)

    first = module.cleanup_training_video_files.run(job.id)
    second = module.cleanup_training_video_files.run(job.id)
    tombstone = QiniuCleanupTombstone.objects.get(session_id=video.client_session_id)
    module.cleanup_qiniu_tombstone.run(tombstone.id)

    job.refresh_from_db()
    assert first.id == second.id == job.id
    assert not session_root(video).exists()
    assert not TrainingVideoSegment.objects.filter(
        training_video=video,
    ).exclude(status=TrainingVideoSegment.Status.DELETED).exists()
    assert job.cleanup_status == VideoAssemblyJob.CleanupStatus.SUCCEEDED
    assert job.cleanup_error == ""
    delete.assert_called_once_with(bucket=settings.QINIU_BUCKET, key=old_key)
    tombstone_delay.assert_called_once_with(tombstone.id)


@pytest.mark.django_db
def test_expire_scan_removes_old_failed_and_unfinalized_sessions_only(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.TRAINING_VIDEO_STAGING_TTL_SECONDS = 86400
    old_recording, old_recording_job = _pending_job(
        project_patient, active_prescription, tmp_path
    )
    old_recording.status = TrainingVideo.Status.UPLOADING_SEGMENTS
    old_recording.finalized_at = None
    old_recording.save(update_fields=["status", "finalized_at", "updated_at"])
    old_failed, old_failed_job = _pending_job(project_patient, active_prescription, tmp_path)
    old_failed.status = TrainingVideo.Status.FAILED
    old_failed.save(update_fields=["status", "updated_at"])
    old_failed_job.status = VideoAssemblyJob.Status.FAILED
    old_failed_job.save(update_fields=["status", "updated_at"])
    recent, _ = _pending_job(project_patient, active_prescription, tmp_path)
    old_time = timezone.now() - timedelta(hours=25)
    TrainingVideo.objects.filter(pk__in=[old_recording.id, old_failed.id]).update(
        updated_at=old_time
    )
    VideoAssemblyJob.objects.filter(pk=old_failed_job.id).update(updated_at=old_time)
    module = _video_tasks()
    delete = Mock()
    tombstone_delay = Mock()
    monkeypatch.setattr(module, "delete_object_if_exists", delete)
    monkeypatch.setattr(module.cleanup_qiniu_tombstone, "delay", tombstone_delay)

    expired_count = module.expire_stale_training_video_sessions.run()

    old_recording.refresh_from_db()
    old_failed.refresh_from_db()
    recent.refresh_from_db()
    assert expired_count == 2
    assert old_recording.status == TrainingVideo.Status.EXPIRED
    assert old_failed.status == TrainingVideo.Status.EXPIRED
    assert recent.status == TrainingVideo.Status.QUEUED
    assert not session_root(old_recording).exists()
    assert not session_root(old_failed).exists()
    assert session_root(recent).exists()
    delete.assert_not_called()
    tombstones = QiniuCleanupTombstone.objects.filter(
        session_id__in=[old_recording.client_session_id, old_failed.client_session_id]
    )
    assert tombstones.count() == 2
    assert all(tombstone.retain_canonical is False for tombstone in tombstones)


@pytest.mark.django_db
def test_stale_recovery_skips_fresh_heartbeat_and_enqueues_stale_once(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS = 3600
    stale_video, stale = _pending_job(project_patient, active_prescription, tmp_path)
    fresh_video, fresh = _pending_job(project_patient, active_prescription, tmp_path)
    now = timezone.now()
    for video, job, heartbeat in [
        (stale_video, stale, now - timedelta(seconds=3601)),
        (fresh_video, fresh, now - timedelta(seconds=3599)),
    ]:
        video.status = TrainingVideo.Status.ASSEMBLING
        video.save(update_fields=["status", "updated_at"])
        job.status = VideoAssemblyJob.Status.RUNNING
        job.attempt_count = 2
        job.started_at = now - timedelta(hours=2)
        job.heartbeat_at = heartbeat
        job.save(
            update_fields=[
                "status",
                "attempt_count",
                "started_at",
                "heartbeat_at",
                "updated_at",
            ]
        )
    module = _video_tasks()
    delay = Mock()
    monkeypatch.setattr(module.run_video_assembly_job, "delay", delay)

    with django_capture_on_commit_callbacks(execute=True):
        first_count = module.recover_stale_video_assembly_jobs.run()
        second_count = module.recover_stale_video_assembly_jobs.run()

    stale.refresh_from_db()
    fresh.refresh_from_db()
    stale_video.refresh_from_db()
    assert first_count == 1
    assert second_count == 0
    assert stale.status == VideoAssemblyJob.Status.PENDING
    assert stale.attempt_count == 2
    assert stale_video.status == TrainingVideo.Status.QUEUED
    assert fresh.status == VideoAssemblyJob.Status.RUNNING
    delay.assert_called_once_with(stale.id)


@pytest.mark.django_db
def test_stale_recovery_fails_job_at_max_attempts_without_enqueue(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS = 3600
    video, job = _pending_job(project_patient, active_prescription, tmp_path)
    now = timezone.now()
    video.status = TrainingVideo.Status.ASSEMBLING
    video.save(update_fields=["status", "updated_at"])
    job.status = VideoAssemblyJob.Status.RUNNING
    job.attempt_count = 3
    job.started_at = now - timedelta(hours=2)
    job.heartbeat_at = now - timedelta(seconds=3601)
    job.save(
        update_fields=[
            "status",
            "attempt_count",
            "started_at",
            "heartbeat_at",
            "updated_at",
        ]
    )
    module = _video_tasks()
    delay = Mock()
    monkeypatch.setattr(module.run_video_assembly_job, "delay", delay)

    with django_capture_on_commit_callbacks(execute=True):
        recovered_count = module.recover_stale_video_assembly_jobs.run()

    job.refresh_from_db()
    video.refresh_from_db()
    assert recovered_count == 0
    assert job.status == VideoAssemblyJob.Status.FAILED
    assert job.attempt_count == 3
    assert job.finished_at is not None
    assert job.heartbeat_at is not None
    assert job.failure_reason
    assert video.status == TrainingVideo.Status.FAILED
    assert video.failure_reason == job.failure_reason
    delay.assert_not_called()


@pytest.mark.django_db
def test_job_state_updates_revalidate_locked_state_before_progressing(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    module = _video_tasks()

    video.status = TrainingVideo.Status.ATTACHED
    video.save(update_fields=["status", "updated_at"])
    claimed_job, claimed = module.claim_video_assembly_job(job.id)
    assert claimed_job.id == job.id
    assert claimed is False
    job.refresh_from_db()
    assert job.status == VideoAssemblyJob.Status.PENDING
    assert job.attempt_count == 0

    video.status = TrainingVideo.Status.ASSEMBLING
    video.save(update_fields=["status", "updated_at"])
    with pytest.raises(ValidationError):
        module.mark_uploading_qiniu(
            job.id,
            _assembly_result(video, duration=60.0),
            lease_attempt=job.attempt_count,
        )
    job.refresh_from_db()
    video.refresh_from_db()
    assert job.status == VideoAssemblyJob.Status.PENDING
    assert video.status == TrainingVideo.Status.ASSEMBLING


@pytest.mark.django_db
def test_attach_does_not_create_record_after_project_patient_unbind(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    result = _assembly_result(video, duration=60.0)
    job_id = job.id
    project_patient.delete()
    module = _video_tasks()

    with pytest.raises((ObjectDoesNotExist, ValidationError)):
        module.attach_training_video(
            job_id,
            result,
            _remote_metadata(result),
            lease_attempt=job.attempt_count,
        )

    assert not TrainingRecord.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("status", [TrainingVideo.Status.UPLOADING_QINIU, TrainingVideo.Status.ATTACHED])
def test_unbound_video_cleanup_deletes_qiniu_local_files_and_database_record(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
    status,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.QINIU_BUCKET = "motioncare-training"
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    video.status = status
    video.project_patient = None
    video.cleanup_status = TrainingVideo.CleanupStatus.PENDING
    video.cleanup_requested_at = timezone.now()
    if status == TrainingVideo.Status.ATTACHED:
        video.object_key = job.qiniu_object_key
    video.save()
    (session_root(video) / "working").mkdir(parents=True, exist_ok=True)
    (session_root(video) / "working" / "final.mp4").write_bytes(b"final")
    module = _video_tasks()
    delete = Mock()
    monkeypatch.setattr(module, "delete_object_if_exists", delete)
    cleanup_delay = Mock()
    monkeypatch.setattr(module.cleanup_qiniu_tombstone, "delay", cleanup_delay)

    cleaned = module.cleanup_unbound_training_video.run(video.id)

    assert cleaned is True
    assert not TrainingVideo.objects.filter(pk=video.id).exists()
    assert not session_root(video).exists()
    delete.assert_not_called()
    tombstone = QiniuCleanupTombstone.objects.get(session_id=video.client_session_id)
    assert tombstone.canonical_key == job.qiniu_object_key
    assert tombstone.retain_canonical is False
    cleanup_delay.assert_called_once_with(tombstone.id)


@pytest.mark.django_db
def test_unbound_video_cleanup_failure_is_durable_retried_and_beat_compensated(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    video, _ = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    video.project_patient = None
    video.cleanup_status = TrainingVideo.CleanupStatus.PENDING
    video.cleanup_requested_at = timezone.now()
    video.save()
    module = _video_tasks()
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(
        module,
        "_remove_session_files",
        Mock(side_effect=RuntimeError("local cleanup down")),
    )
    monkeypatch.setattr(module.cleanup_unbound_training_video, "retry", retry)

    with pytest.raises(Retry):
        module.cleanup_unbound_training_video.run(video.id)

    video.refresh_from_db()
    assert video.cleanup_status == TrainingVideo.CleanupStatus.FAILED
    assert video.cleanup_attempt_count == 1
    assert video.cleanup_error

    delay = Mock()
    monkeypatch.setattr(module.cleanup_unbound_training_video, "delay", delay)
    with django_capture_on_commit_callbacks(execute=True):
        recovered = module.recover_training_video_cleanup.run()

    assert recovered == 1
    delay.assert_called_once_with(video.id)


@pytest.mark.django_db
def test_attempt_count_lease_blocks_old_worker_touch_mark_and_attach(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    module = _video_tasks()
    first, claimed = module.claim_video_assembly_job(job.id)
    assert claimed is True
    first_attempt = first.attempt_count

    VideoAssemblyJob.objects.filter(pk=job.id).update(
        status=VideoAssemblyJob.Status.PENDING,
    )
    TrainingVideo.objects.filter(pk=video.id).update(status=TrainingVideo.Status.QUEUED)
    second, claimed = module.claim_video_assembly_job(job.id)
    assert claimed is True
    assert second.attempt_count == first_attempt + 1
    result = _assembly_result(video, duration=60.0)

    with pytest.raises(ValidationError, match="租约"):
        module._touch_heartbeat(job.id, first_attempt)
    with pytest.raises(ValidationError, match="租约"):
        module.mark_uploading_qiniu(job.id, result, lease_attempt=first_attempt)
    with pytest.raises(ValidationError, match="租约"):
        module.attach_training_video(
            job.id,
            result,
            _remote_metadata(result),
            lease_attempt=first_attempt,
        )
    assert not TrainingRecord.objects.exists()


@pytest.mark.django_db
def test_move_before_attach_keeps_canonical_during_crash_recovery(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.QINIU_BUCKET = "motioncare-training"
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
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

    tombstone = QiniuCleanupTombstone.objects.get(session_id=video.client_session_id)
    assert tombstone.canonical_key == job.qiniu_object_key
    assert tombstone.retain_canonical is True
    assert tombstone.max_attempt_number == 1


@pytest.mark.django_db
def test_retry_after_move_and_db_failure_reuses_canonical_and_records_publish(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
):
    from apps.training import qiniu as training_qiniu

    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.QINIU_BUCKET = "motioncare-training"
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    module = _video_tasks()
    claimed_job, claimed = module.claim_video_assembly_job(job.id)
    assert claimed is True
    result = _assembly_result(video, duration=60.0)
    attempt_key = module.qiniu_attempt_object_key(video, claimed_job.attempt_count)
    module.mark_uploading_qiniu(
        job.id,
        result,
        lease_attempt=claimed_job.attempt_count,
        attempt_key=attempt_key,
        canonical_key=job.qiniu_object_key,
    )
    metadata = _remote_metadata(result, object_hash="published-hash")
    monkeypatch.setattr(module, "publish_attempt_to_canonical", Mock(return_value=metadata))

    real_save = VideoAssemblyJob.save
    fail_publish_save = True

    def flaky_save(instance, *args, **kwargs):
        nonlocal fail_publish_save
        if (
            fail_publish_save
            and instance.pk == job.id
            and "qiniu_object_hash" in kwargs.get("update_fields", [])
        ):
            fail_publish_save = False
            raise DatabaseError("publish state write failed")
        return real_save(instance, *args, **kwargs)

    monkeypatch.setattr(VideoAssemblyJob, "save", flaky_save)
    publish_kwargs = {
        "lease_attempt": claimed_job.attempt_count,
        "bucket": settings.QINIU_BUCKET,
        "attempt_key": attempt_key,
        "canonical_key": job.qiniu_object_key,
        "expected_hash": metadata["hash"],
        "expected_size_bytes": result.size_bytes,
    }
    with pytest.raises(DatabaseError, match="publish state write failed"):
        module.publish_canonical_under_lease(job.id, **publish_kwargs)

    job.refresh_from_db()
    assert job.qiniu_object_hash == ""

    upload = Mock()
    monkeypatch.setattr(
        training_qiniu,
        "stat_object_metadata_or_none",
        Mock(return_value=metadata),
    )
    monkeypatch.setattr(training_qiniu.qiniu, "etag", Mock(return_value=metadata["hash"]))
    monkeypatch.setattr(training_qiniu, "upload_local_video", upload)
    recovered = training_qiniu.upload_and_publish_local_video(
        path=result.output_path,
        bucket=settings.QINIU_BUCKET,
        attempt_key=attempt_key,
        canonical_key=job.qiniu_object_key,
        publish_attempt=lambda **kwargs: module.publish_canonical_under_lease(
            job.id,
            lease_attempt=claimed_job.attempt_count,
            **kwargs,
        ),
    )

    assert recovered == metadata
    upload.assert_not_called()
    job.refresh_from_db()
    assert job.qiniu_object_hash == "published-hash"


@pytest.mark.django_db
def test_stale_worker_never_moves_or_deletes_canonical_after_new_attempt_attaches(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.QINIU_BUCKET = "motioncare-training"
    settings.QINIU_UPLOAD_TIMEOUT_SECONDS = 60
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    result = _assembly_result(video, duration=60.0)
    module = _video_tasks()
    monkeypatch.setattr(module, "assemble_video", Mock(return_value=result))
    monkeypatch.setattr(module.cleanup_training_video_files, "delay", Mock())

    def old_upload(*, bucket, attempt_key, canonical_key, publish_attempt, **kwargs):
        assert attempt_key.endswith("/attempt-1.mp4")
        assert canonical_key == job.qiniu_object_key
        VideoAssemblyJob.objects.filter(pk=job.id).update(status=VideoAssemblyJob.Status.PENDING)
        TrainingVideo.objects.filter(pk=video.id).update(status=TrainingVideo.Status.QUEUED)
        second, claimed = module.claim_video_assembly_job(job.id)
        assert claimed is True
        second_key = module.qiniu_attempt_object_key(video, second.attempt_count)
        module.mark_uploading_qiniu(
            job.id,
            result,
            lease_attempt=second.attempt_count,
            attempt_key=second_key,
            canonical_key=canonical_key,
        )
        module.attach_training_video(
            job.id,
            result,
            _remote_metadata(result, object_hash="new-hash"),
            lease_attempt=second.attempt_count,
            object_key=canonical_key,
        )
        return publish_attempt(
            bucket=bucket,
            attempt_key=attempt_key,
            canonical_key=canonical_key,
            expected_hash="old-hash",
            expected_size_bytes=result.size_bytes,
        )

    monkeypatch.setattr(module, "upload_and_publish_local_video", old_upload)

    with pytest.raises(ValidationError, match="租约"):
        module.process_video_assembly_job(job.id)

    video.refresh_from_db()
    assert video.status == TrainingVideo.Status.ATTACHED
    assert video.object_key == job.qiniu_object_key


@pytest.mark.django_db
def test_unbound_cleanup_deletes_video_but_keeps_durable_tombstone_for_late_upload(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.QINIU_BUCKET = "motioncare-training"
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    job.attempt_count = 2
    job.status = VideoAssemblyJob.Status.FAILED
    job.save()
    video.project_patient = None
    video.cleanup_status = TrainingVideo.CleanupStatus.PENDING
    video.cleanup_requested_at = timezone.now()
    video.save()
    module = _video_tasks()
    session_id = video.client_session_id
    expected_attempt_keys = [
        module.qiniu_attempt_object_key(video, attempt) for attempt in (1, 2)
    ]
    cleanup_delay = Mock()
    monkeypatch.setattr(module.cleanup_qiniu_tombstone, "delay", cleanup_delay)

    cleaned = module.cleanup_unbound_training_video.run(video.id)

    assert cleaned is True
    assert not TrainingVideo.objects.filter(pk=video.id).exists()
    tombstone = QiniuCleanupTombstone.objects.get(session_id=session_id)
    assert tombstone.canonical_key == job.qiniu_object_key
    assert tombstone.retain_canonical is False
    assert tombstone.max_attempt_number == 2
    cleanup_delay.assert_called_once_with(tombstone.id)

    remote_objects = {expected_attempt_keys[-1], job.qiniu_object_key}
    stat_remote = Mock(
        side_effect=lambda *, key, **kwargs: (
            {"hash": "late", "fsize": 1, "mimeType": "video/mp4"}
            if key in remote_objects
            else None
        )
    )

    def delete_remote(*, key, **kwargs):
        remote_objects.discard(key)

    monkeypatch.setattr(module, "stat_object_metadata_or_none", stat_remote)
    monkeypatch.setattr(module, "delete_object_if_exists", Mock(side_effect=delete_remote))

    module.cleanup_qiniu_tombstone.run(tombstone.id)
    assert remote_objects == set()
    tombstone.refresh_from_db()
    assert tombstone.last_seen_at is not None
    assert QiniuCleanupTombstone.objects.filter(pk=tombstone.id).exists()

    stat_remote.reset_mock()
    module.cleanup_qiniu_tombstone.run(tombstone.id)
    assert stat_remote.call_count == 3
    assert QiniuCleanupTombstone.objects.filter(pk=tombstone.id).exists()


@pytest.mark.django_db
def test_attached_tombstone_keeps_canonical_and_continues_cleaning_old_attempts(
    monkeypatch,
):
    now = timezone.now()
    tombstone = QiniuCleanupTombstone.objects.create(
        session_id="8cf99c30-9b03-4bda-b4d3-b492f3a2db12",
        bucket="motioncare-training",
        attempt_key_prefix="training-videos/attempts/session/attempt-",
        max_attempt_number=2,
        canonical_key="training-videos/1/final.mp4",
        retain_canonical=True,
        next_check_at=now,
    )
    remote_objects = {
        tombstone.canonical_key,
        f"{tombstone.attempt_key_prefix}1.mp4",
        f"{tombstone.attempt_key_prefix}2.mp4",
    }
    module = _video_tasks()
    monkeypatch.setattr(
        module,
        "stat_object_metadata_or_none",
        Mock(
            side_effect=lambda *, key, **kwargs: (
                {"hash": "remote", "fsize": 1, "mimeType": "video/mp4"}
                if key in remote_objects
                else None
            )
        ),
    )
    monkeypatch.setattr(
        module,
        "delete_object_if_exists",
        Mock(side_effect=lambda *, key, **kwargs: remote_objects.discard(key)),
    )

    module.cleanup_qiniu_tombstone.run(tombstone.id)

    assert remote_objects == {tombstone.canonical_key}
    tombstone.refresh_from_db()
    assert tombstone.last_seen_at is not None
    assert tombstone.next_check_at > now
    assert QiniuCleanupTombstone.objects.filter(pk=tombstone.id).exists()


@pytest.mark.django_db
def test_tombstone_beat_only_enqueues_due_unarchived_rows(monkeypatch):
    now = timezone.now()
    due = QiniuCleanupTombstone.objects.create(
        session_id="8cf99c30-9b03-4bda-b4d3-b492f3a2db12",
        bucket="bucket",
        attempt_key_prefix="attempts/a-",
        next_check_at=now - timedelta(seconds=1),
    )
    QiniuCleanupTombstone.objects.create(
        session_id="9cf99c30-9b03-4bda-b4d3-b492f3a2db12",
        bucket="bucket",
        attempt_key_prefix="attempts/b-",
        next_check_at=now + timedelta(days=1),
    )
    QiniuCleanupTombstone.objects.create(
        session_id="acf99c30-9b03-4bda-b4d3-b492f3a2db12",
        bucket="bucket",
        attempt_key_prefix="attempts/c-",
        next_check_at=now - timedelta(seconds=1),
        archived_at=now,
    )
    module = _video_tasks()
    delay = Mock()
    monkeypatch.setattr(module.cleanup_qiniu_tombstone, "delay", delay)

    count = module.cleanup_qiniu_tombstones.run()

    assert count == 1
    delay.assert_called_once_with(due.id)


@pytest.mark.django_db
def test_stale_takeover_stops_old_worker_before_next_file_write(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    video, job = _pending_job(project_patient, active_prescription, tmp_path, duration=60)
    module = _video_tasks()
    old_output = session_root(video) / "working" / "old-worker-write.mp4"

    def takeover_before_write(*args, on_progress, **kwargs):
        VideoAssemblyJob.objects.filter(pk=job.id).update(
            status=VideoAssemblyJob.Status.PENDING,
        )
        TrainingVideo.objects.filter(pk=video.id).update(status=TrainingVideo.Status.QUEUED)
        _, claimed = module.claim_video_assembly_job(job.id)
        assert claimed is True
        on_progress()
        old_output.write_bytes(b"must-not-be-written")

    upload = Mock()
    monkeypatch.setattr(module, "assemble_video", takeover_before_write)
    monkeypatch.setattr(module, "upload_and_publish_local_video", upload)

    with pytest.raises(ValidationError, match="租约"):
        module.process_video_assembly_job(job.id)

    assert not old_output.exists()
    upload.assert_not_called()


def test_safe_failure_reason_redacts_common_bare_credential_fields(settings):
    settings.QINIU_ACCESS_KEY = "configured-ak"
    settings.QINIU_SECRET_KEY = "configured-sk"
    module = _video_tasks()
    reason = module._safe_video_failure_reason(
        "视频处理",
        RuntimeError(
            "access_key=one accessKey=two secret_key=three "
            "credential_id=four AK=five SK=six"
        ),
    )

    for secret in ("one", "two", "three", "four", "five", "six"):
        assert secret not in reason


@pytest.mark.django_db
def test_expire_scan_removes_only_strict_old_orphans_and_old_quarantine(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.TRAINING_VIDEO_STAGING_TTL_SECONDS = 86400
    orphan = tmp_path / "999-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    malformed = tmp_path / "999-not-a-session"
    quarantine = tmp_path / ".quarantine" / "998-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    for path in (orphan, malformed, quarantine):
        path.mkdir(parents=True)
        (path / "segment.mp4").write_bytes(b"private")
    old_timestamp = (timezone.now() - timedelta(hours=25)).timestamp()
    for path in (orphan, malformed, quarantine):
        path.touch()
        import os

        os.utime(path, (old_timestamp, old_timestamp))
    module = _video_tasks()

    module.expire_stale_training_video_sessions.run()

    assert not orphan.exists()
    assert not quarantine.exists()
    assert malformed.exists()


@pytest.mark.django_db
def test_expire_scan_removes_wrong_session_uuid_for_existing_video_including_quarantine(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.TRAINING_VIDEO_STAGING_TTL_SECONDS = 86400
    video, _ = _pending_job(project_patient, active_prescription, tmp_path)
    wrong_hex = "f" * 32
    assert wrong_hex != video.client_session_id.hex
    wrong_session = tmp_path / f"{video.id}-{wrong_hex}"
    wrong_quarantine = tmp_path / ".quarantine" / f"{video.id}-{wrong_hex}"
    right_session = session_root(video)
    for path in (wrong_session, wrong_quarantine, right_session):
        path.mkdir(parents=True, exist_ok=True)
        (path / "private.mp4").write_bytes(b"private")
    old_timestamp = (timezone.now() - timedelta(hours=25)).timestamp()
    import os

    for path in (wrong_session, wrong_quarantine, right_session):
        os.utime(path, (old_timestamp, old_timestamp))

    _video_tasks().expire_stale_training_video_sessions.run()

    assert not wrong_session.exists()
    assert not wrong_quarantine.exists()
    assert right_session.exists()
