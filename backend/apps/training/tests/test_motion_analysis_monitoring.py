import logging
import threading
from datetime import timedelta

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import close_old_connections, connection
from django.test.utils import CaptureQueriesContext
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


def _bulk_analysis_jobs(
    template,
    *,
    count,
    start=0,
    status=MotionAnalysisJob.Status.FAILED,
):
    return MotionAnalysisJob.objects.bulk_create(
        [
            MotionAnalysisJob(
                training_video=template.training_video,
                training_record=template.training_record,
                project_patient=template.project_patient,
                prescription_action=template.prescription_action,
                status=status,
                skeleton_bucket="analysis-skeletons",
                skeleton_object_key=(
                    f"motion-analysis/{template.project_patient_id}/2026/09/"
                    f"bulk-{status}-{index:06d}/skeleton.mp4"
                ),
            )
            for index in range(start, start + count)
        ]
    )


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
def test_expiry_reaches_terminal_when_cleanup_registration_fails_and_retries_safely(
    analysis_job_factory,
    monkeypatch,
    caplog,
):
    from apps.training import motion_analysis_monitoring as monitoring

    now = timezone.now()
    job = analysis_job_factory(
        status=MotionAnalysisJob.Status.RUNNING,
        lease_token_hash="old-lease-hash",
        lease_expires_at=now - timedelta(seconds=1),
        current_stage="upload",
    )
    provider_detail = (
        f"token=provider-secret path=/private/patient.mp4 key={job.skeleton_object_key}"
    )

    monkeypatch.setattr(
        monitoring,
        "queue_skeleton_cleanup",
        lambda _job: (_ for _ in ()).throw(RuntimeError(provider_detail)),
    )
    with caplog.at_level(logging.CRITICAL, logger=monitoring.__name__):
        assert monitoring.expire_stale_motion_analysis_jobs(now=now) == 1

    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.FAILED
    assert job.failure_code == "lease_expired"
    assert job.lease_expires_at is None
    assert QiniuCleanupTombstone.objects.count() == 0
    diagnostic = next(
        record
        for record in caplog.records
        if getattr(record, "reason_code", None)
        == "skeleton_cleanup_registration_failed"
    )
    assert diagnostic.job_id == job.id
    rendered = "\n".join(
        f"{record.getMessage()} {record.__dict__!r}" for record in caplog.records
    )
    for forbidden in (
        provider_detail,
        "provider-secret",
        "/private/patient.mp4",
        job.skeleton_object_key,
        job.project_patient.patient.name,
    ):
        assert forbidden not in rendered

    monkeypatch.undo()
    assert monitoring.reconcile_motion_analysis_cleanup_tombstones() == 1
    assert monitoring.reconcile_motion_analysis_cleanup_tombstones() == 0
    assert QiniuCleanupTombstone.objects.get().canonical_key == job.skeleton_object_key


@pytest.mark.django_db
def test_cleanup_reconciliation_excludes_existing_tombstones_before_database_limit(
    analysis_job_factory,
    monkeypatch,
):
    from apps.training import motion_analysis_monitoring as monitoring
    from apps.training.motion_analysis_storage import queue_skeleton_cleanup

    template = analysis_job_factory(status=MotionAnalysisJob.Status.FAILED)
    existing = [template, *_bulk_analysis_jobs(template, count=24)]
    missing = _bulk_analysis_jobs(template, count=3, start=24)
    succeeded = _bulk_analysis_jobs(
        template,
        count=1,
        status=MotionAnalysisJob.Status.SUCCEEDED,
    )[0]
    for job in existing:
        queue_skeleton_cleanup(job)
    succeeded_tombstone = queue_skeleton_cleanup(succeeded)
    succeeded_tombstone.retain_canonical = True
    succeeded_tombstone.save(update_fields=["retain_canonical", "updated_at"])
    monkeypatch.setattr(monitoring, "_CLEANUP_RECONCILIATION_BATCH_SIZE", 3)

    with CaptureQueriesContext(connection) as queries:
        assert monitoring.reconcile_motion_analysis_cleanup_tombstones() == 3

    assert set(
        QiniuCleanupTombstone.objects.filter(
            canonical_key__in=[job.skeleton_object_key for job in missing],
            retain_canonical=False,
        ).values_list("canonical_key", flat=True)
    ) == {job.skeleton_object_key for job in missing}
    succeeded_tombstone.refresh_from_db()
    assert succeeded_tombstone.retain_canonical is True
    candidate_queries = [
        query["sql"]
        for query in queries.captured_queries
        if query["sql"].lstrip().upper().startswith("SELECT")
        and 'FROM "training_motionanalysisjob"' in query["sql"]
        and "FOR UPDATE" in query["sql"]
    ]
    assert len(candidate_queries) == 1
    assert "NOT EXISTS" in candidate_queries[0]
    assert "LIMIT 3" in candidate_queries[0]
    assert "SKIP LOCKED" in candidate_queries[0]


@pytest.mark.django_db
def test_cleanup_reconciliation_limits_attempts_and_rotates_persistent_failures(
    analysis_job_factory,
    monkeypatch,
    caplog,
):
    from apps.training import motion_analysis_monitoring as monitoring

    template = analysis_job_factory(status=MotionAnalysisJob.Status.FAILED)
    _bulk_analysis_jobs(template, count=1000)
    attempted_ids = []
    provider_detail = (
        f"Bearer provider-secret C:\\private key={template.skeleton_object_key}"
    )

    def always_fail(job):
        attempted_ids.append(job.id)
        raise RuntimeError(provider_detail)

    monkeypatch.setattr(monitoring, "queue_skeleton_cleanup", always_fail)
    with caplog.at_level(logging.CRITICAL, logger=monitoring.__name__):
        assert monitoring.reconcile_motion_analysis_cleanup_tombstones() == 0

    first_attempt_ids = set(attempted_ids)
    assert len(first_attempt_ids) == 500
    diagnostics = [
        record
        for record in caplog.records
        if getattr(record, "reason_code", None)
        == "skeleton_cleanup_reconciliation_failed"
    ]
    assert len(diagnostics) == 1
    assert diagnostics[0].attempted_count == 500
    assert diagnostics[0].succeeded_count == 0
    assert diagnostics[0].failed_count == 500
    rendered = "\n".join(
        f"{record.getMessage()} {record.__dict__!r}" for record in caplog.records
    )
    for forbidden in (
        provider_detail,
        "provider-secret",
        template.skeleton_object_key,
        template.project_patient.patient.name,
    ):
        assert forbidden not in rendered

    attempted_ids.clear()
    caplog.clear()
    with caplog.at_level(logging.CRITICAL, logger=monitoring.__name__):
        assert monitoring.reconcile_motion_analysis_cleanup_tombstones() == 0

    assert len(attempted_ids) == 500
    assert first_attempt_ids.isdisjoint(attempted_ids)
    assert len(
        [
            record
            for record in caplog.records
            if getattr(record, "reason_code", None)
            == "skeleton_cleanup_reconciliation_failed"
        ]
    ) == 1


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_cleanup_reconciliation_claims_distinct_jobs(
    analysis_job_factory,
    monkeypatch,
    caplog,
):
    from apps.training import motion_analysis_monitoring as monitoring

    assert connection.vendor == "postgresql"
    jobs = [
        analysis_job_factory(status=MotionAnalysisJob.Status.FAILED),
        analysis_job_factory(status=MotionAnalysisJob.Status.FAILED),
    ]
    original_queue = monitoring.queue_skeleton_cleanup
    both_claimed = threading.Barrier(2)
    results = []
    errors = []

    def synchronized_queue(job):
        both_claimed.wait(timeout=5)
        return original_queue(job)

    def run_reconciliation():
        close_old_connections()
        try:
            results.append(monitoring.reconcile_motion_analysis_cleanup_tombstones())
        except Exception as exc:  # pragma: no branch - thread result capture
            errors.append(exc)
        finally:
            close_old_connections()

    monkeypatch.setattr(monitoring, "_CLEANUP_RECONCILIATION_BATCH_SIZE", 1)
    monkeypatch.setattr(monitoring, "queue_skeleton_cleanup", synchronized_queue)
    threads = [threading.Thread(target=run_reconciliation) for _ in range(2)]
    with caplog.at_level(logging.CRITICAL, logger=monitoring.__name__):
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(results) == [1, 1]
    assert QiniuCleanupTombstone.objects.filter(
        canonical_key__in=[job.skeleton_object_key for job in jobs],
        retain_canonical=False,
    ).count() == 2
    assert not any(
        getattr(record, "reason_code", None)
        in {
            "skeleton_cleanup_registration_failed",
            "skeleton_cleanup_reconciliation_failed",
        }
        for record in caplog.records
    )


@pytest.mark.django_db
def test_recovery_task_delegates_to_expiry_without_requeue(monkeypatch):
    from apps.training import tasks

    calls = []
    monkeypatch.setattr(
        tasks,
        "expire_stale_motion_analysis_jobs",
        lambda now=None: calls.append(now) or 3,
    )
    monkeypatch.setattr(
        tasks,
        "reconcile_motion_analysis_cleanup_tombstones",
        lambda: calls.append("cleanup") or 1,
    )

    assert tasks.recover_stale_motion_analysis_jobs() == 3
    assert calls == ["cleanup", None]


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
