from datetime import timedelta
from unittest.mock import Mock

import pytest
from celery.exceptions import Retry
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils import timezone

from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.training.models import (
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
        module.expire_stale_training_video_sessions,
        module.recover_stale_video_assembly_jobs,
        training_tasks.run_motion_analysis_job,
        training_tasks.recover_stale_motion_analysis_jobs,
    ]
    for task in default_queue_tasks:
        route = celery_app.amqp.router.route({}, task.name, args=(), kwargs={})
        assert route["queue"].name == "celery"


def _shoulder_press_action(prescription):
    item = ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press")
    return prescription.add_action_snapshot(
        item,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=10,
    )


def _pending_job(project_patient, active_prescription, tmp_path, *, duration=61):
    action = _shoulder_press_action(active_prescription)
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate() - timedelta(days=1),
        note="训练备注",
        expected_duration_seconds=duration,
        actual_duration_seconds=duration,
        expected_segment_count=2,
        uploaded_segment_count=2,
        finalized_at=timezone.now(),
        status=TrainingVideo.Status.QUEUED,
    )
    for index in range(2):
        path = segment_path(video, index)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"segment-{index}".encode())
        TrainingVideoSegment.objects.create(
            training_video=video,
            index=index,
            duration_ms=(duration * 1000) // 2,
            size_bytes=path.stat().st_size,
            sha256=f"{index}" * 64,
            relative_path=path.relative_to(tmp_path).as_posix(),
            status=TrainingVideoSegment.Status.UPLOADED,
            uploaded_at=timezone.now(),
        )
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
    module = _video_tasks()
    monkeypatch.setattr(module, "assemble_video", assemble)
    monkeypatch.setattr(module, "upload_local_video", upload)
    monkeypatch.setattr(module.cleanup_training_video_files, "delay", cleanup_delay)

    with django_capture_on_commit_callbacks(execute=True):
        attached = module.process_video_assembly_job(job.id)
        duplicate = module.process_video_assembly_job(job.id)

    video.refresh_from_db()
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
    assemble.assert_called_once()
    upload.assert_called_once()
    cleanup_delay.assert_called_once_with(job.id)


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
    monkeypatch.setattr(module, "upload_local_video", upload)
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
    monkeypatch.setattr(module, "upload_local_video", upload)
    monkeypatch.setattr(module.run_video_assembly_job, "retry", retry)

    with pytest.raises(Retry):
        module.run_video_assembly_job.run(job.id)
    with pytest.raises(Retry):
        module.run_video_assembly_job.run(job.id)
    final = module.run_video_assembly_job.run(job.id)

    job.refresh_from_db()
    video.refresh_from_db()
    assert final.status == VideoAssemblyJob.Status.FAILED
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
    video.save(update_fields=["training_record", "status", "updated_at"])
    outside = tmp_path / "outside"
    outside.mkdir()
    unsafe_link = session_root(video) / "working" / "unsafe-link"
    unsafe_link.parent.mkdir(parents=True, exist_ok=True)
    unsafe_link.symlink_to(outside, target_is_directory=True)
    module = _video_tasks()
    retry = Mock(side_effect=Retry())
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
    assert outside.is_dir()
    assert unsafe_link.is_symlink()


@pytest.mark.django_db
def test_cleanup_success_removes_attached_session_and_is_idempotent(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
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
    video.save(update_fields=["training_record", "status", "updated_at"])
    (session_root(video) / "working").mkdir(parents=True, exist_ok=True)
    (session_root(video) / "working" / "final.mp4").write_bytes(b"final")
    module = _video_tasks()

    first = module.cleanup_training_video_files.run(job.id)
    second = module.cleanup_training_video_files.run(job.id)

    job.refresh_from_db()
    assert first.id == second.id == job.id
    assert not session_root(video).exists()
    assert not TrainingVideoSegment.objects.filter(
        training_video=video,
    ).exclude(status=TrainingVideoSegment.Status.DELETED).exists()
    assert job.cleanup_status == VideoAssemblyJob.CleanupStatus.SUCCEEDED
    assert job.cleanup_error == ""


@pytest.mark.django_db
def test_expire_scan_removes_old_failed_and_unfinalized_sessions_only(
    project_patient,
    active_prescription,
    tmp_path,
    settings,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.TRAINING_VIDEO_STAGING_TTL_SECONDS = 86400
    old_recording, _ = _pending_job(project_patient, active_prescription, tmp_path)
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
        module.mark_uploading_qiniu(job.id, _assembly_result(video, duration=60.0))
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

    with pytest.raises(ObjectDoesNotExist):
        module.attach_training_video(job_id, result, _remote_metadata(result))

    assert not TrainingRecord.objects.exists()
