import logging
from datetime import timedelta

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from apps.training.models import (
    MotionAnalysisJob,
    MotionResultSource,
    QiniuCleanupTombstone,
    TrainingRecord,
    TrainingVideo,
)


@pytest.fixture
def analysis_job_factory(
    db,
    project_patient,
    active_prescription,
    prescription_action,
):
    def create(*, created_at=None, **overrides):
        record = TrainingRecord.objects.create(
            project_patient=project_patient,
            prescription=active_prescription,
            prescription_action=prescription_action,
            training_date=timezone.localdate(),
            status=TrainingRecord.Status.COMPLETED,
        )
        video = TrainingVideo.objects.create(
            project_patient=project_patient,
            prescription=active_prescription,
            prescription_action=prescription_action,
            training_record=record,
            bucket="original-videos",
            object_key=f"training-videos/{record.id}/original.mp4",
            object_hash="original-hash",
            content_type="video/mp4",
            size_bytes=1024,
            duration_seconds=60,
            status=TrainingVideo.Status.ATTACHED,
        )
        values = {
            "training_video": video,
            "training_record": record,
            "project_patient": project_patient,
            "prescription_action": prescription_action,
            "status": MotionAnalysisJob.Status.PENDING,
            "action_source_key": "motion-resistance-shoulder-press",
            "algorithm_version": "PP-TinyPose_128x96",
            "rule_version": "shoulder-press-v2",
            "parameter_version": "shoulder-press-v2-defaults",
            "subject_tracker_version": "primary-subject-v1",
            "skeleton_bucket": "analysis-skeletons",
            "skeleton_object_key": (
                f"motion-analysis/{project_patient.id}/2026/09/"
                f"22222222-2222-4222-8222-{record.id:012d}/skeleton.mp4"
            ),
        }
        values.update(overrides)
        job = MotionAnalysisJob.objects.create(**values)
        if created_at is not None:
            MotionAnalysisJob.objects.filter(pk=job.pk).update(created_at=created_at)
            job.refresh_from_db()
        return job

    return create


@pytest.mark.django_db
def test_expire_stale_jobs_uses_strict_lease_boundary_and_queues_cleanup_once(
    analysis_job_factory,
    doctor,
):
    from apps.training.motion_analysis_monitoring import expire_stale_motion_analysis_jobs

    now = timezone.now()
    expired = analysis_job_factory(
        status=MotionAnalysisJob.Status.RUNNING,
        worker_id="worker-1",
        lease_token_hash="old-lease-hash",
        lease_expires_at=now - timedelta(microseconds=1),
        last_heartbeat_at=now - timedelta(minutes=5),
        started_at=now - timedelta(minutes=10),
        current_stage="upload",
    )
    exactly_now = analysis_job_factory(
        status=MotionAnalysisJob.Status.RUNNING,
        lease_token_hash="boundary-lease-hash",
        lease_expires_at=now,
        last_heartbeat_at=now - timedelta(minutes=1),
        started_at=now - timedelta(minutes=2),
    )
    future = analysis_job_factory(
        status=MotionAnalysisJob.Status.RUNNING,
        lease_token_hash="live-lease-hash",
        lease_expires_at=now + timedelta(seconds=1),
    )
    pending = analysis_job_factory(status=MotionAnalysisJob.Status.PENDING)
    expired.training_record.motion_total_count = 7
    expired.training_record.motion_standard_count = 5
    expired.training_record.motion_nonstandard_count = 2
    expired.training_record.motion_result_source = MotionResultSource.DOCTOR
    expired.training_record.motion_result_updated_by = doctor
    expired.training_record.save()

    assert expire_stale_motion_analysis_jobs(now=now) == 1
    assert expire_stale_motion_analysis_jobs(now=now) == 0

    expired.refresh_from_db()
    expired.training_record.refresh_from_db()
    exactly_now.refresh_from_db()
    future.refresh_from_db()
    pending.refresh_from_db()
    assert expired.status == MotionAnalysisJob.Status.FAILED
    assert expired.failure_code == "lease_expired"
    assert expired.failure_reason == "动作分析任务租约已过期"
    assert expired.finished_at == now
    assert expired.lease_token_hash == ""
    assert expired.lease_expires_at is None
    assert expired.current_stage == "lease_expired"
    assert expired.training_record.motion_total_count == 7
    assert expired.training_record.motion_result_source == MotionResultSource.DOCTOR
    assert exactly_now.status == MotionAnalysisJob.Status.RUNNING
    assert future.status == MotionAnalysisJob.Status.RUNNING
    assert pending.status == MotionAnalysisJob.Status.PENDING
    assert QiniuCleanupTombstone.objects.count() == 1
    assert QiniuCleanupTombstone.objects.get().canonical_key == expired.skeleton_object_key


@pytest.mark.django_db
def test_recovery_task_delegates_to_expiry_without_requeue(monkeypatch):
    from apps.training import tasks

    calls = []
    monkeypatch.setattr(
        tasks,
        "expire_stale_motion_analysis_jobs",
        lambda now=None: calls.append(now) or 3,
    )

    assert tasks.recover_stale_motion_analysis_jobs() == 3
    assert calls == [None]


@pytest.mark.django_db
def test_health_snapshot_reports_only_stable_queue_and_lease_metrics(analysis_job_factory):
    from apps.training.motion_analysis_monitoring import motion_analysis_health_snapshot

    now = timezone.now()
    analysis_job_factory(created_at=now - timedelta(seconds=1250))
    analysis_job_factory(created_at=now - timedelta(seconds=50))
    analysis_job_factory(
        status=MotionAnalysisJob.Status.RUNNING,
        started_at=now - timedelta(seconds=400),
        last_heartbeat_at=now - timedelta(seconds=200),
        lease_expires_at=now - timedelta(seconds=1),
    )
    analysis_job_factory(
        status=MotionAnalysisJob.Status.RUNNING,
        started_at=now - timedelta(seconds=300),
        last_heartbeat_at=now - timedelta(seconds=100),
        lease_expires_at=now + timedelta(seconds=200),
    )
    analysis_job_factory(status=MotionAnalysisJob.Status.SUCCEEDED, finished_at=now)

    snapshot = motion_analysis_health_snapshot(now=now)

    assert snapshot.pending_count == 2
    assert snapshot.oldest_pending_age_seconds == 1250
    assert snapshot.running_count == 2
    assert snapshot.oldest_running_lease_age_seconds == 200
    assert snapshot.expired_running_lease_count == 1
    assert snapshot.to_dict() == {
        "pending_count": 2,
        "oldest_pending_age_seconds": 1250,
        "running_count": 2,
        "oldest_running_lease_age_seconds": 200,
        "expired_running_lease_count": 1,
    }


@pytest.mark.django_db
def test_health_recording_warns_with_redacted_structured_metrics_only(
    analysis_job_factory,
    caplog,
    settings,
):
    from apps.training import tasks

    settings.PP_MCARE_PENDING_WARNING_SECONDS = 1200
    now = timezone.now()
    secret_values = {
        "patient": "private-patient-name",
        "signed_url": "https://private.example/video?token=url-secret",
        "traceback": "/var/lib/private/trace.py",
    }
    job = analysis_job_factory(
        created_at=now - timedelta(seconds=1201),
        result_payload=secret_values,
        failure_reason="token=job-secret /private/path",
    )

    def monkeypatch_now():
        return now

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(tasks.timezone, "now", monkeypatch_now)
        with caplog.at_level(logging.INFO, logger="apps.training.tasks"):
            payload = tasks.record_motion_analysis_health_snapshot()

    assert payload["pending_count"] == 1
    warning = next(
        record
        for record in caplog.records
        if getattr(record, "reason_code", None) == "oldest_pending_age_exceeded"
    )
    assert warning.pending_count == 1
    assert warning.oldest_pending_age_seconds == 1201
    assert warning.warning_threshold_seconds == 1200
    rendered = "\n".join(f"{record.getMessage()} {record.__dict__!r}" for record in caplog.records)
    for forbidden in (
        *secret_values.values(),
        job.training_video.object_key,
        job.skeleton_object_key,
        job.project_patient.patient.name,
        "job-secret",
        "Authorization",
        "lease_token",
    ):
        assert forbidden not in rendered


@pytest.mark.django_db
@pytest.mark.parametrize(
    "setting_name",
    ["PP_MCARE_MONITOR_INTERVAL_SECONDS", "PP_MCARE_PENDING_WARNING_SECONDS"],
)
def test_monitoring_runtime_settings_fail_closed(setting_name, settings):
    from apps.training import tasks

    setattr(settings, setting_name, 0)

    with pytest.raises(ImproperlyConfigured):
        if setting_name == "PP_MCARE_MONITOR_INTERVAL_SECONDS":
            tasks.recover_stale_motion_analysis_jobs()
        else:
            tasks.record_motion_analysis_health_snapshot()


def test_celery_beat_runs_expiry_and_health_recording_every_monitor_interval(settings):
    expiry = settings.CELERY_BEAT_SCHEDULE["recover-stale-motion-analysis-jobs"]
    health = settings.CELERY_BEAT_SCHEDULE["record-motion-analysis-health-snapshot"]

    assert settings.PP_MCARE_MONITOR_INTERVAL_SECONDS == 300
    assert expiry["schedule"] == 300
    assert health["schedule"] == 300
    assert expiry["task"] == "apps.training.tasks.recover_stale_motion_analysis_jobs"
    assert health["task"] == "apps.training.tasks.record_motion_analysis_health_snapshot"
