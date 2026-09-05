import hashlib
import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.utils import timezone
from motion_analysis_contract import CompletionPayload, MotionCounts, PROTOCOL_VERSION
from rest_framework.test import APIClient

from apps.training.models import (
    MotionAnalysisJob,
    MotionResultSource,
    QiniuCleanupTombstone,
    TrainingRecord,
    TrainingVideo,
)


LEASE_TOKEN = "a" * 43
VERSIONS = {
    "algorithm_version": "PP-TinyPose_128x96",
    "rule_version": "shoulder-press-v2",
    "parameter_version": "shoulder-press-v2-defaults",
    "subject_tracker_version": "primary-subject-v1",
}


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def machine_auth(settings):
    settings.PP_MCARE_SERVICE_TOKEN_SHA256 = hashlib.sha256(b"machine-secret").hexdigest()
    return {"HTTP_AUTHORIZATION": "Bearer machine-secret"}


@pytest.fixture
def running_job_factory(
    db,
    settings,
    project_patient,
    active_prescription,
    prescription_action,
):
    settings.QINIU_BUCKET = "analysis-skeletons"

    def create(**overrides):
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
        now = timezone.now()
        values = {
            "training_video": video,
            "training_record": record,
            "project_patient": project_patient,
            "prescription_action": prescription_action,
            "status": MotionAnalysisJob.Status.RUNNING,
            "worker_id": "worker-1",
            "lease_token_hash": hashlib.sha256(LEASE_TOKEN.encode()).hexdigest(),
            "lease_expires_at": now + timedelta(minutes=5),
            "last_heartbeat_at": now,
            "started_at": now,
            "current_stage": "upload",
            "action_source_key": "motion-resistance-shoulder-press",
            **VERSIONS,
            "skeleton_bucket": "analysis-skeletons",
            "skeleton_object_key": (
                f"motion-analysis/{project_patient.id}/2026/09/"
                f"11111111-1111-4111-8111-{record.id:012d}/skeleton.mp4"
            ),
        }
        values.update(overrides)
        return MotionAnalysisJob.objects.create(**values)

    return create


def complete_url(job):
    return f"/api/internal/motion-analysis/jobs/{job.id}/complete/"


def fail_url(job):
    return f"/api/internal/motion-analysis/jobs/{job.id}/fail/"


def complete_body(job, **overrides):
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "lease_token": LEASE_TOKEN,
        "idempotency_key": "complete-001",
        **VERSIONS,
        "total_count": 90,
        "standard_count": 80,
        "nonstandard_count": 10,
        "quality_summary": {
            "confidence_level": 0.98,
            "quality_flags": ["stable"],
        },
        "result_payload": {"frames_decoded": 8929, "details": {"side": "bilateral"}},
        "skeleton": {
            "bucket": job.skeleton_bucket,
            "object_key": job.skeleton_object_key,
            "object_hash": "skeleton-hash",
            "size_bytes": 2048,
            "duration_seconds": 60.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "content_type": "video/mp4",
        },
    }
    payload.update(overrides)
    return payload


def fail_body(**overrides):
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "lease_token": LEASE_TOKEN,
        "idempotency_key": "fail-001",
        "failure_code": "subject_unstable",
        "summary": "无法稳定锁定单一训练主体",
        "stage_timings": {"download": 2.5, "inference": 71},
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_complete_verifies_object_and_updates_job_and_record_atomically(
    api_client,
    machine_auth,
    running_job_factory,
):
    job = running_job_factory()
    now_before = timezone.now()

    with patch(
        "apps.training.internal_services.verify_skeleton_upload",
        return_value={"hash": "skeleton-hash", "fsize": 2048, "mimeType": "video/mp4"},
    ) as verify:
        response = api_client.post(
            complete_url(job),
            complete_body(job),
            format="json",
            secure=True,
            **machine_auth,
        )

    assert response.status_code == 200
    assert response.data == {
        "protocol_version": PROTOCOL_VERSION,
        "job_id": job.id,
        "status": "succeeded",
        "finished_at": response.data["finished_at"],
        "total_count": 90,
        "standard_count": 80,
        "nonstandard_count": 10,
    }
    job.refresh_from_db()
    job.training_record.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.SUCCEEDED
    assert job.completion_idempotency_key == "complete-001"
    assert job.result_payload == {"frames_decoded": 8929, "details": {"side": "bilateral"}}
    assert job.skeleton_object_hash == "skeleton-hash"
    assert job.skeleton_size_bytes == 2048
    assert job.skeleton_duration_seconds == 60.0
    assert job.skeleton_width == 1920
    assert job.skeleton_height == 1080
    assert job.skeleton_fps == 30.0
    assert job.finished_at >= now_before
    assert job.lease_token_hash == ""
    assert job.lease_expires_at is None
    assert job.current_stage == "completed"
    assert job.training_record.motion_total_count == 90
    assert job.training_record.motion_standard_count == 80
    assert job.training_record.motion_nonstandard_count == 10
    assert job.training_record.motion_result_source == MotionResultSource.ALGORITHM
    assert job.training_record.motion_result_updated_by is None
    verify.assert_called_once()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "remote_error",
    [
        "七牛对象不存在 /tmp/private token=secret",
        "训练视频对象 Hash 不匹配 /tmp/private token=secret",
    ],
)
def test_complete_remote_object_failure_rolls_back_job_and_training_record(
    api_client,
    machine_auth,
    running_job_factory,
    remote_error,
):
    job = running_job_factory()
    job.training_record.motion_total_count = 7
    job.training_record.motion_standard_count = 5
    job.training_record.motion_nonstandard_count = 2
    job.training_record.motion_result_source = MotionResultSource.DOCTOR
    job.training_record.save()
    original_lease_expiry = job.lease_expires_at

    with patch(
        "apps.training.internal_services.verify_skeleton_upload",
        side_effect=ValidationError(remote_error),
    ):
        response = api_client.post(
            complete_url(job),
            complete_body(job),
            format="json",
            secure=True,
            **machine_auth,
        )

    assert response.status_code == 400
    assert "private" not in response.content.decode()
    assert "secret" not in response.content.decode()
    job.refresh_from_db()
    job.training_record.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.RUNNING
    assert job.completion_idempotency_key == ""
    assert job.result_payload == {}
    assert job.lease_expires_at == original_lease_expiry
    assert job.training_record.motion_total_count == 7
    assert job.training_record.motion_result_source == MotionResultSource.DOCTOR


@pytest.mark.django_db
@pytest.mark.parametrize("version_field", list(VERSIONS))
def test_complete_rejects_wrong_execution_version_without_remote_check_or_writes(
    api_client,
    machine_auth,
    running_job_factory,
    version_field,
):
    job = running_job_factory()

    with patch("apps.training.internal_services.verify_skeleton_upload") as verify:
        response = api_client.post(
            complete_url(job),
            complete_body(job, **{version_field: "wrong-version"}),
            format="json",
            secure=True,
            **machine_auth,
        )

    assert response.status_code == 409
    verify.assert_not_called()
    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.RUNNING
    assert job.result_payload == {}


@pytest.mark.django_db
@pytest.mark.parametrize("lease_case", ["wrong", "expired"])
def test_complete_rejects_wrong_or_expired_lease(
    api_client,
    machine_auth,
    running_job_factory,
    lease_case,
):
    overrides = {}
    body_overrides = {}
    if lease_case == "wrong":
        body_overrides["lease_token"] = "b" * 43
    else:
        overrides["lease_expires_at"] = timezone.now() - timedelta(seconds=1)
    job = running_job_factory(**overrides)

    with patch("apps.training.internal_services.verify_skeleton_upload") as verify:
        response = api_client.post(
            complete_url(job),
            complete_body(job, **body_overrides),
            format="json",
            secure=True,
            **machine_auth,
        )

    assert response.status_code == 409
    verify.assert_not_called()
    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.RUNNING


@pytest.mark.django_db
def test_duplicate_completion_does_not_reverify_or_overwrite_later_doctor_edit(
    api_client,
    machine_auth,
    running_job_factory,
    doctor,
):
    job = running_job_factory()
    body = complete_body(job)
    with patch(
        "apps.training.internal_services.verify_skeleton_upload",
        return_value={"hash": "skeleton-hash", "fsize": 2048, "mimeType": "video/mp4"},
    ):
        first = api_client.post(
            complete_url(job), body, format="json", secure=True, **machine_auth
        )
    job.refresh_from_db()
    immutable_result = job.result_payload
    doctor_edit_at = timezone.now() + timedelta(seconds=1)
    job.training_record.set_motion_result(
        MotionCounts(total_count=12, standard_count=9, nonstandard_count=3),
        {"doctor_note": "人工修正"},
        MotionResultSource.DOCTOR,
        doctor,
        doctor_edit_at,
    )
    job.training_record.save()

    with patch(
        "apps.training.internal_services.verify_skeleton_upload",
        side_effect=AssertionError("幂等重放不应访问远端对象"),
    ) as verify:
        second = api_client.post(
            complete_url(job), body, format="json", secure=True, **machine_auth
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.data == first.data
    verify.assert_not_called()
    job.refresh_from_db()
    job.training_record.refresh_from_db()
    assert job.result_payload == immutable_result
    assert job.training_record.motion_total_count == 12
    assert job.training_record.motion_result_source == MotionResultSource.DOCTOR
    assert job.training_record.motion_result_updated_by == doctor


@pytest.mark.django_db
@pytest.mark.parametrize("terminal_status", ["succeeded", "failed"])
def test_complete_rejects_conflicting_terminal_state(
    api_client,
    machine_auth,
    running_job_factory,
    terminal_status,
):
    job = running_job_factory(
        status=terminal_status,
        completion_idempotency_key="original-key",
        finished_at=timezone.now(),
    )

    response = api_client.post(
        complete_url(job),
        complete_body(job, idempotency_key="different-key"),
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 409


@pytest.mark.django_db
def test_fail_preserves_doctor_result_and_queues_idempotent_skeleton_cleanup(
    api_client,
    machine_auth,
    running_job_factory,
    doctor,
):
    job = running_job_factory()
    record = job.training_record
    record.set_motion_result(
        MotionCounts(total_count=7, standard_count=5, nonstandard_count=2),
        {"doctor_note": "保留"},
        MotionResultSource.DOCTOR,
        doctor,
        timezone.now(),
    )
    record.save()

    response = api_client.post(
        fail_url(job), fail_body(), format="json", secure=True, **machine_auth
    )

    assert response.status_code == 200
    assert response.data["status"] == "failed"
    assert "summary" not in response.data
    job.refresh_from_db()
    record.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.FAILED
    assert job.completion_idempotency_key == "fail-001"
    assert job.failure_code == "subject_unstable"
    assert job.failure_reason == "无法稳定锁定单一训练主体"
    assert job.result_payload == {
        "failure_diagnostics": {"stage_timings": {"download": 2.5, "inference": 71}}
    }
    assert job.finished_at is not None
    assert job.lease_token_hash == ""
    assert job.lease_expires_at is None
    assert job.current_stage == "failed"
    assert record.motion_total_count == 7
    assert record.motion_result_source == MotionResultSource.DOCTOR
    assert record.motion_result_updated_by == doctor
    tombstone = QiniuCleanupTombstone.objects.get()
    assert tombstone.canonical_key == job.skeleton_object_key
    assert tombstone.retain_canonical is False

    replay = api_client.post(
        fail_url(job), fail_body(), format="json", secure=True, **machine_auth
    )
    assert replay.status_code == 200
    assert QiniuCleanupTombstone.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status_value", "stored_key"),
    [(MotionAnalysisJob.Status.FAILED, "other-key"), (MotionAnalysisJob.Status.SUCCEEDED, "fail-001")],
)
def test_fail_rejects_conflicting_terminal_state(
    api_client,
    machine_auth,
    running_job_factory,
    status_value,
    stored_key,
):
    job = running_job_factory(
        status=status_value,
        completion_idempotency_key=stored_key,
        finished_at=timezone.now(),
    )

    response = api_client.post(
        fail_url(job), fail_body(), format="json", secure=True, **machine_auth
    )

    assert response.status_code == 409


@pytest.mark.django_db
@pytest.mark.parametrize(
    "summary",
    [
        "下载 https://private.example/video.mp4?token=secret 失败",
        "读取 /var/lib/motioncare/private.mp4 失败",
        "upload_token=qiniu-secret",
        "access_key=ak-sensitive",
        "secret_key=sk-sensitive",
        "credential_id=credential-sensitive",
        "x" * 2001,
    ],
)
def test_fail_rejects_sensitive_summary_without_persisting_or_echoing_it(
    api_client,
    machine_auth,
    running_job_factory,
    summary,
):
    job = running_job_factory()

    response = api_client.post(
        fail_url(job),
        fail_body(summary=summary),
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 400
    assert summary not in response.content.decode()
    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.RUNNING
    assert job.failure_reason == ""
    assert QiniuCleanupTombstone.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "stage_timings",
    [
        {"download": -1},
        {"download": True},
        {"download": "2.5"},
        {"download": {"seconds": 2.5}},
        {"../private": 1},
    ],
)
def test_fail_rejects_noncanonical_or_nonnegative_stage_timings(
    api_client,
    machine_auth,
    running_job_factory,
    stage_timings,
):
    job = running_job_factory()

    response = api_client.post(
        fail_url(job),
        fail_body(stage_timings=stage_timings),
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 400
    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.RUNNING


@pytest.mark.django_db
def test_completion_endpoints_require_https_machine_auth_without_echoing_secrets(
    api_client,
    machine_auth,
    running_job_factory,
):
    job = running_job_factory()
    body = complete_body(
        job,
        result_payload={"signed_url": "https://private.example/video?token=payload-secret"},
    )

    plain_http = api_client.post(complete_url(job), body, format="json", **machine_auth)
    no_bearer = api_client.post(complete_url(job), body, format="json", secure=True)

    assert plain_http.status_code == 403
    assert no_bearer.status_code == 403
    rendered = plain_http.content.decode() + no_bearer.content.decode()
    assert "machine-secret" not in rendered
    assert "payload-secret" not in rendered
    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.RUNNING


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_same_completion_uses_row_lock_and_verifies_once(
    running_job_factory,
):
    from apps.training import internal_services

    assert connection.vendor == "postgresql"
    job = running_job_factory()
    payload = CompletionPayload.from_dict(complete_body(job))
    first_in_verify = threading.Event()
    release_first = threading.Event()
    results = {}
    errors = {}
    backend_pids = {}

    def blocking_verify(_job, _metadata):
        first_in_verify.set()
        assert release_first.wait(10)
        return {"hash": "skeleton-hash", "fsize": 2048, "mimeType": "video/mp4"}

    def run_completion(name):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                backend_pids[name] = cursor.fetchone()[0]
            results[name] = internal_services.complete_job(
                job_id=job.id,
                lease_token=LEASE_TOKEN,
                idempotency_key="complete-001",
                payload=payload,
                now=timezone.now(),
            )
        except Exception as exc:  # pragma: no branch - thread result capture
            errors[name] = exc
        finally:
            close_old_connections()

    first = threading.Thread(target=run_completion, args=("first",), name="complete-first")
    second = threading.Thread(target=run_completion, args=("second",), name="complete-second")

    with patch.object(internal_services, "verify_skeleton_upload", side_effect=blocking_verify) as verify:
        try:
            first.start()
            assert first_in_verify.wait(10)
            second.start()
            second.join(0.25)
            assert second.is_alive(), "第二个事务应等待 PostgreSQL 行锁"
        finally:
            release_first.set()
            first.join(10)
            second.join(10)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == {}
    assert len(set(backend_pids.values())) == 2
    assert results["first"].status == MotionAnalysisJob.Status.SUCCEEDED
    assert results["second"].status == MotionAnalysisJob.Status.SUCCEEDED
    assert verify.call_count == 1
    job.training_record.refresh_from_db()
    assert job.training_record.motion_total_count == 90
