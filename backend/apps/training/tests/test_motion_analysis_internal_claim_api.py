import hashlib
import logging
import os
import subprocess
import sys
import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import close_old_connections, connection
from django.utils import timezone
from motion_analysis_contract import (
    PROTOCOL_VERSION,
    ClaimedJob,
    DownloadGrant,
    UploadGrant,
    WorkerCapability,
)
from rest_framework.test import APIClient

from apps.training.models import MotionAnalysisJob, TrainingRecord, TrainingVideo
from apps.training.motion_analysis_storage import AnalysisStorageGrant


CLAIM_URL = "/api/internal/motion-analysis/jobs/claim/"
CAPABILITY = {
    "action_source_key": "motion-resistance-shoulder-press",
    "algorithm_version": "PP-TinyPose_128x96",
    "rule_version": "shoulder-press-v2",
    "parameter_version": "shoulder-press-v2-defaults",
}
CLAIM_BODY = {
    "worker_id": "worker-1",
    "protocol_version": PROTOCOL_VERSION,
    "capabilities": [CAPABILITY],
}
HEARTBEAT_BODY = {
    "protocol_version": PROTOCOL_VERSION,
    "lease_token": "placeholder",
    "stage": "inference",
}


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def machine_auth(settings):
    settings.PP_MCARE_SERVICE_TOKEN_SHA256 = hashlib.sha256(b"machine-secret").hexdigest()
    return {"HTTP_AUTHORIZATION": "Bearer machine-secret"}


@pytest.fixture
def analysis_job_factory(
    db,
    settings,
    project_patient,
    active_prescription,
    prescription_action,
):
    settings.QINIU_ACCESS_KEY = "ak-test"
    settings.QINIU_SECRET_KEY = "sk-test"
    settings.QINIU_DOWNLOAD_DOMAIN = "https://private.example.com"
    settings.QINIU_BUCKET = "analysis-skeletons"

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
            "action_source_key": CAPABILITY["action_source_key"],
            "algorithm_version": CAPABILITY["algorithm_version"],
            "rule_version": CAPABILITY["rule_version"],
            "parameter_version": CAPABILITY["parameter_version"],
            "subject_tracker_version": "primary-subject-v1",
            "skeleton_bucket": "analysis-skeletons",
            "skeleton_object_key": (
                f"motion-analysis/{project_patient.id}/2026/09/"
                f"11111111-1111-4111-8111-{record.id:012d}/skeleton.mp4"
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
def test_claim_requires_exact_bearer_token(api_client, settings):
    settings.PP_MCARE_SERVICE_TOKEN_SHA256 = hashlib.sha256(b"machine-secret").hexdigest()

    response = api_client.post(CLAIM_URL, CLAIM_BODY, format="json", secure=True)

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer wrong-secret",
        "bearer machine-secret",
        "Bearer  machine-secret",
        "Bearer machine-secret extra",
        "Bearer\tmachine-secret",
        "Basic machine-secret",
        "Bearer ",
    ],
)
def test_claim_rejects_wrong_or_malformed_bearer_credentials(
    api_client,
    settings,
    authorization,
):
    settings.PP_MCARE_SERVICE_TOKEN_SHA256 = hashlib.sha256(b"machine-secret").hexdigest()

    response = api_client.post(
        CLAIM_URL,
        CLAIM_BODY,
        format="json",
        secure=True,
        HTTP_AUTHORIZATION=authorization,
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_doctor_session_does_not_bypass_machine_auth(api_client, doctor, settings):
    settings.PP_MCARE_SERVICE_TOKEN_SHA256 = hashlib.sha256(b"machine-secret").hexdigest()
    api_client.force_authenticate(user=doctor)

    response = api_client.post(CLAIM_URL, CLAIM_BODY, format="json", secure=True)

    assert response.status_code == 403


@pytest.mark.django_db
def test_claim_rejects_plain_http_even_with_correct_bearer(
    api_client,
    machine_auth,
    analysis_job_factory,
):
    job = analysis_job_factory()

    response = api_client.post(CLAIM_URL, CLAIM_BODY, format="json", **machine_auth)

    assert response.status_code == 403
    assert "machine-secret" not in response.content.decode()
    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.PENDING


@pytest.mark.django_db
def test_claim_accepts_trusted_forwarded_https(api_client, machine_auth):
    response = api_client.post(
        CLAIM_URL,
        CLAIM_BODY,
        format="json",
        HTTP_X_FORWARDED_PROTO="https",
        **machine_auth,
    )

    assert response.status_code == 204


@pytest.mark.django_db
def test_claim_locks_oldest_compatible_job(
    api_client,
    machine_auth,
    analysis_job_factory,
):
    now = timezone.now()
    oldest = analysis_job_factory(created_at=now - timedelta(minutes=2))
    analysis_job_factory(created_at=now - timedelta(minutes=1))

    response = api_client.post(
        CLAIM_URL,
        CLAIM_BODY,
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 200
    assert response.data["job_id"] == oldest.id
    oldest.refresh_from_db()
    assert oldest.status == MotionAnalysisJob.Status.RUNNING


@pytest.mark.django_db
def test_claim_terminally_skips_invalid_oldest_source_metadata(
    api_client,
    machine_auth,
    analysis_job_factory,
):
    now = timezone.now()
    invalid = analysis_job_factory(created_at=now - timedelta(minutes=2))
    invalid.training_video.object_hash = ""
    invalid.training_video.save(update_fields=["object_hash", "updated_at"])
    healthy = analysis_job_factory(created_at=now - timedelta(minutes=1))

    response = api_client.post(
        CLAIM_URL,
        CLAIM_BODY,
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 200
    assert response.data["job_id"] == healthy.id
    invalid.refresh_from_db()
    assert invalid.status == MotionAnalysisJob.Status.FAILED
    assert invalid.failure_code == "source_metadata_invalid"
    assert invalid.failure_reason == "原视频元数据无效，请医生手动填写训练结果"


@pytest.mark.django_db
def test_claim_all_invalid_sources_finishes_them_and_returns_empty(
    api_client,
    machine_auth,
    analysis_job_factory,
):
    jobs = [analysis_job_factory() for _ in range(3)]
    for job in jobs:
        job.training_video.size_bytes = 0
        job.training_video.save(update_fields=["size_bytes", "updated_at"])

    response = api_client.post(
        CLAIM_URL,
        CLAIM_BODY,
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 204
    assert not MotionAnalysisJob.objects.filter(
        id__in=[job.id for job in jobs], status=MotionAnalysisJob.Status.PENDING
    ).exists()


@pytest.mark.django_db
def test_claim_returns_shared_contract_and_hashes_one_time_lease(
    api_client,
    machine_auth,
    analysis_job_factory,
):
    job = analysis_job_factory()

    response = api_client.post(
        CLAIM_URL,
        CLAIM_BODY,
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 200
    claimed = ClaimedJob.from_dict(response.data)
    assert claimed.protocol_version == PROTOCOL_VERSION
    assert claimed.job_id == job.id
    assert claimed.action_source_key == CAPABILITY["action_source_key"]
    assert claimed.algorithm_version == CAPABILITY["algorithm_version"]
    assert claimed.rule_version == CAPABILITY["rule_version"]
    assert claimed.parameter_version == CAPABILITY["parameter_version"]
    assert claimed.subject_tracker_version == "primary-subject-v1"
    assert claimed.heartbeat_interval_seconds == 60
    assert claimed.download.bucket == "original-videos"
    assert claimed.download.object_key == job.training_video.object_key
    assert claimed.download.object_hash == job.training_video.object_hash
    assert claimed.download.size_bytes == 1024
    assert claimed.download.content_type == "video/mp4"
    assert claimed.upload.bucket == "analysis-skeletons"
    assert claimed.upload.object_key == job.skeleton_object_key

    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.RUNNING
    assert job.worker_id == "worker-1"
    assert job.started_at == job.last_heartbeat_at
    assert job.lease_expires_at - job.last_heartbeat_at == timedelta(seconds=300)
    assert job.lease_token_hash == hashlib.sha256(claimed.lease_token.encode()).hexdigest()
    assert len(claimed.lease_token) >= 43
    assert claimed.lease_token not in repr(claimed)
    assert claimed.upload.token not in repr(claimed)
    assert all(
        claimed.lease_token not in value
        for value in job.__dict__.values()
        if isinstance(value, str)
    )


@pytest.mark.django_db
def test_claim_returns_204_when_queue_is_empty(api_client, machine_auth):
    response = api_client.post(
        CLAIM_URL,
        CLAIM_BODY,
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 204
    assert not response.content


@pytest.mark.django_db
def test_empty_queue_does_not_log_capability_mismatch(api_client, machine_auth, caplog):
    with caplog.at_level(logging.WARNING, logger="apps.training.internal_services"):
        response = api_client.post(
            CLAIM_URL,
            CLAIM_BODY,
            format="json",
            secure=True,
            **machine_auth,
        )

    assert response.status_code == 204
    assert not any(
        getattr(record, "reason_code", None) == "no_compatible_capability"
        for record in caplog.records
    )


@pytest.mark.django_db
def test_incompatible_pending_job_logs_structured_redacted_diagnostic(
    api_client,
    machine_auth,
    analysis_job_factory,
    caplog,
):
    job = analysis_job_factory(result_payload={"patient_note": "private-patient-note"})
    declared = {
        "action_source_key": ("https://evil.example/private.mp4?token=client-url-secret"),
        "algorithm_version": "algorithm-secret-token-abc123",
        "rule_version": "patient-alice-sensitive",
        "parameter_version": "upload-token-qiniu-sensitive-xyz",
    }
    body = {
        **CLAIM_BODY,
        "worker_id": "worker-diagnostic-1",
        "capabilities": [declared],
    }

    with caplog.at_level(logging.WARNING, logger="apps.training.internal_services"):
        response = api_client.post(
            CLAIM_URL,
            body,
            format="json",
            secure=True,
            **machine_auth,
        )

    assert response.status_code == 204
    diagnostic = next(
        record
        for record in caplog.records
        if getattr(record, "reason_code", None) == "no_compatible_capability"
    )
    assert diagnostic.oldest_pending_job_id == job.id
    assert diagnostic.required_capability == CAPABILITY
    assert diagnostic.worker_id == "worker-diagnostic-1"
    assert diagnostic.declared_capability_count == 1
    assert diagnostic.declared_capabilities_sha256 == (
        "1bc029c30b264b9e9054fe7203d814ff6886ce549b059ba9ecaed8fd53da6ee5"
    )
    assert "declared_capabilities" not in diagnostic.__dict__
    rendered = "\n".join(f"{record.getMessage()}\n{record.__dict__!r}" for record in caplog.records)
    for forbidden in (
        *declared.values(),
        "machine-secret",
        "private-patient-note",
        job.project_patient.patient.name,
        job.training_video.object_key,
        job.skeleton_object_key,
        "Authorization",
        "lease_token",
        "signed_url",
        "upload_token",
    ):
        assert forbidden not in rendered
        assert forbidden not in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("action_source_key", "motion-resistance-row"),
        ("algorithm_version", "other-algorithm"),
        ("rule_version", "shoulder-press-v1"),
        ("rule_version", "shoulder-press-v2 "),
        ("parameter_version", "other-parameters"),
    ],
)
def test_claim_does_not_take_job_when_any_capability_dimension_differs(
    api_client,
    machine_auth,
    analysis_job_factory,
    field,
    value,
):
    job = analysis_job_factory()
    body = {**CLAIM_BODY, "capabilities": [{**CAPABILITY, field: value}]}

    response = api_client.post(CLAIM_URL, body, format="json", secure=True, **machine_auth)

    assert response.status_code == 204
    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.PENDING
    assert not job.worker_id
    assert not job.lease_token_hash


@pytest.mark.django_db
@pytest.mark.parametrize("protocol_version", [None, "0", "2", " 1 ", 1])
def test_claim_rejects_missing_or_incompatible_protocol_version(
    api_client,
    machine_auth,
    analysis_job_factory,
    protocol_version,
):
    job = analysis_job_factory()
    body = {**CLAIM_BODY, "protocol_version": protocol_version}

    response = api_client.post(CLAIM_URL, body, format="json", secure=True, **machine_auth)

    assert response.status_code == 400
    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.PENDING


@pytest.mark.django_db
@pytest.mark.parametrize(
    "worker_id",
    [123, " worker-1", "worker-1 ", "worker 1", "worker/1"],
)
def test_claim_rejects_non_string_or_non_canonical_worker_id(
    api_client,
    machine_auth,
    worker_id,
):
    body = {**CLAIM_BODY, "worker_id": worker_id}

    response = api_client.post(
        CLAIM_URL,
        body,
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_claim_storage_grant_failure_rolls_back_running_state(
    api_client,
    machine_auth,
    analysis_job_factory,
    monkeypatch,
):
    job = analysis_job_factory()
    from apps.training import internal_services

    monkeypatch.setattr(
        internal_services,
        "issue_storage_grant",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValidationError("secret failure")),
    )

    response = api_client.post(CLAIM_URL, CLAIM_BODY, format="json", secure=True, **machine_auth)

    assert response.status_code == 503
    assert "secret failure" not in response.content.decode()
    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.PENDING
    assert not job.worker_id
    assert not job.lease_token_hash
    assert job.started_at is None


@pytest.mark.django_db
def test_motion_analysis_job_persists_restricted_current_stage(analysis_job_factory):
    job = analysis_job_factory(current_stage="inference")

    persisted = MotionAnalysisJob.objects.get(pk=job.pk)

    assert persisted.current_stage == "inference"
    assert "current_stage" not in persisted.result_payload


@pytest.mark.django_db
def test_valid_heartbeat_renews_from_supplied_now_and_stores_safe_stage(
    analysis_job_factory,
    settings,
):
    from apps.training.internal_services import heartbeat_job

    settings.PP_MCARE_JOB_LEASE_SECONDS = 300
    lease_token = "a" * 43
    initial_now = timezone.now()
    job = analysis_job_factory(
        status=MotionAnalysisJob.Status.RUNNING,
        worker_id="worker-1",
        lease_token_hash=hashlib.sha256(lease_token.encode()).hexdigest(),
        lease_expires_at=initial_now + timedelta(seconds=10),
        last_heartbeat_at=initial_now,
        started_at=initial_now,
    )
    heartbeat_now = initial_now + timedelta(seconds=5)

    renewed = heartbeat_job(
        job_id=job.id,
        lease_token=lease_token,
        stage="encoding_video",
        now=heartbeat_now,
    )

    assert renewed.current_stage == "encoding_video"
    assert renewed.last_heartbeat_at == heartbeat_now
    assert renewed.lease_expires_at == heartbeat_now + timedelta(seconds=300)
    assert renewed.result_payload == {}


@pytest.mark.django_db
@pytest.mark.parametrize("stage", ["", "free text", "../secret", "https://example.com", "x" * 33])
def test_heartbeat_rejects_free_text_paths_urls_and_overlong_stages(
    api_client,
    machine_auth,
    analysis_job_factory,
    stage,
):
    lease_token = "a" * 43
    before = timezone.now()
    job = analysis_job_factory(
        status=MotionAnalysisJob.Status.RUNNING,
        lease_token_hash=hashlib.sha256(lease_token.encode()).hexdigest(),
        lease_expires_at=before + timedelta(minutes=1),
        last_heartbeat_at=before,
        started_at=before,
    )
    body = {**HEARTBEAT_BODY, "lease_token": lease_token, "stage": stage}

    response = api_client.post(
        f"/api/internal/motion-analysis/jobs/{job.id}/heartbeat/",
        body,
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 400
    job.refresh_from_db()
    assert job.last_heartbeat_at == before
    assert job.current_stage == ""


@pytest.mark.django_db
@pytest.mark.parametrize("condition", ["wrong_token", "expired", "succeeded", "failed"])
def test_heartbeat_rejects_invalid_lease_without_extension(
    api_client,
    machine_auth,
    analysis_job_factory,
    condition,
):
    correct_token = "a" * 43
    supplied_token = correct_token
    before = timezone.now()
    status = MotionAnalysisJob.Status.RUNNING
    expires_at = before + timedelta(minutes=1)
    if condition == "wrong_token":
        supplied_token = "b" * 43
    elif condition == "expired":
        expires_at = before - timedelta(seconds=1)
    else:
        status = condition
    job = analysis_job_factory(
        status=status,
        lease_token_hash=hashlib.sha256(correct_token.encode()).hexdigest(),
        lease_expires_at=expires_at,
        last_heartbeat_at=before,
        started_at=before,
    )
    body = {**HEARTBEAT_BODY, "lease_token": supplied_token}

    response = api_client.post(
        f"/api/internal/motion-analysis/jobs/{job.id}/heartbeat/",
        body,
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 409
    job.refresh_from_db()
    assert job.lease_expires_at == expires_at
    assert job.last_heartbeat_at == before
    assert job.current_stage == ""


@pytest.mark.django_db
def test_heartbeat_requires_shared_protocol_version(
    api_client,
    machine_auth,
    analysis_job_factory,
):
    now = timezone.now()
    lease_token = "a" * 43
    job = analysis_job_factory(
        status=MotionAnalysisJob.Status.RUNNING,
        lease_token_hash=hashlib.sha256(lease_token.encode()).hexdigest(),
        lease_expires_at=now + timedelta(minutes=1),
        last_heartbeat_at=now,
        started_at=now,
    )
    body = {**HEARTBEAT_BODY, "protocol_version": "2", "lease_token": lease_token}

    response = api_client.post(
        f"/api/internal/motion-analysis/jobs/{job.id}/heartbeat/",
        body,
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 400
    job.refresh_from_db()
    assert job.last_heartbeat_at == now


@pytest.mark.django_db
def test_valid_heartbeat_api_returns_renewed_lease_without_echoing_token(
    api_client,
    machine_auth,
    analysis_job_factory,
):
    before = timezone.now()
    lease_token = "a" * 43
    job = analysis_job_factory(
        status=MotionAnalysisJob.Status.RUNNING,
        lease_token_hash=hashlib.sha256(lease_token.encode()).hexdigest(),
        lease_expires_at=before + timedelta(minutes=1),
        last_heartbeat_at=before,
        started_at=before,
    )
    body = {**HEARTBEAT_BODY, "lease_token": lease_token, "stage": "upload"}

    response = api_client.post(
        f"/api/internal/motion-analysis/jobs/{job.id}/heartbeat/",
        body,
        format="json",
        secure=True,
        **machine_auth,
    )

    assert response.status_code == 200
    assert response.data["current_stage"] == "upload"
    assert response.data["heartbeat_interval_seconds"] == 60
    assert lease_token not in response.content.decode()
    job.refresh_from_db()
    assert job.lease_expires_at - job.last_heartbeat_at == timedelta(seconds=300)
    assert job.current_stage == "upload"


@pytest.mark.django_db
def test_heartbeat_rejects_plain_http_even_with_correct_bearer(
    api_client,
    machine_auth,
    analysis_job_factory,
):
    before = timezone.now()
    lease_token = "a" * 43
    expires_at = before + timedelta(minutes=1)
    job = analysis_job_factory(
        status=MotionAnalysisJob.Status.RUNNING,
        lease_token_hash=hashlib.sha256(lease_token.encode()).hexdigest(),
        lease_expires_at=expires_at,
        last_heartbeat_at=before,
        started_at=before,
    )

    response = api_client.post(
        f"/api/internal/motion-analysis/jobs/{job.id}/heartbeat/",
        {**HEARTBEAT_BODY, "lease_token": lease_token},
        format="json",
        **machine_auth,
    )

    assert response.status_code == 403
    assert lease_token not in response.content.decode()
    job.refresh_from_db()
    assert job.lease_expires_at == expires_at
    assert job.last_heartbeat_at == before


@pytest.mark.django_db
def test_invalid_runtime_lease_settings_fail_closed(analysis_job_factory, settings):
    from apps.training.internal_services import claim_next_job

    analysis_job_factory()
    settings.PP_MCARE_JOB_LEASE_SECONDS = 0

    with pytest.raises(ImproperlyConfigured):
        claim_next_job(
            worker_id="worker-1",
            capabilities=[WorkerCapability(**CAPABILITY)],
            now=timezone.now(),
        )

    assert not MotionAnalysisJob.objects.filter(status=MotionAnalysisJob.Status.RUNNING).exists()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PP_MCARE_JOB_LEASE_SECONDS", "0"),
        ("PP_MCARE_HEARTBEAT_INTERVAL_SECONDS", "300"),
        ("PP_MCARE_SERVICE_TOKEN_SHA256", "not-a-valid-secret-digest"),
    ],
)
def test_invalid_pp_mcare_environment_settings_fail_at_startup(settings, name, value):
    environment = {**os.environ, name: value}

    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=settings.BASE_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    if name == "PP_MCARE_SERVICE_TOKEN_SHA256":
        assert value not in result.stderr


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_claim_gives_single_job_to_only_one_worker(
    analysis_job_factory,
    settings,
):
    from apps.training import internal_services

    assert connection.vendor == "postgresql"
    settings.PP_MCARE_JOB_LEASE_SECONDS = 300
    job = analysis_job_factory()
    first_has_lock = threading.Event()
    release_first = threading.Event()
    results = {}
    errors = {}
    backend_pids = {}

    grant = AnalysisStorageGrant(
        download=DownloadGrant(
            url="https://private.example.com/original.mp4?token=redacted",
            bucket="original-videos",
            object_key=job.training_video.object_key,
            object_hash=job.training_video.object_hash,
            expires_at="2026-09-05T10:00:00+00:00",
            size_bytes=1024,
            content_type="video/mp4",
        ),
        upload=UploadGrant(
            bucket="analysis-skeletons",
            object_key=job.skeleton_object_key,
            token="sensitive-upload-token",
            expires_at="2026-09-05T12:00:00+00:00",
        ),
    )

    def blocking_grant(_job, _now):
        first_has_lock.set()
        assert release_first.wait(10)
        return grant

    def run_claim(worker_id):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                backend_pids[worker_id] = cursor.fetchone()[0]
            results[worker_id] = internal_services.claim_next_job(
                worker_id=worker_id,
                capabilities=[WorkerCapability(**CAPABILITY)],
                now=timezone.now(),
            )
        except Exception as exc:  # pragma: no branch - thread result capture
            errors[worker_id] = exc
        finally:
            close_old_connections()

    first = threading.Thread(target=run_claim, args=("worker-1",), name="worker-1")
    second = threading.Thread(target=run_claim, args=("worker-2",), name="worker-2")

    with patch.object(internal_services, "issue_storage_grant", side_effect=blocking_grant):
        try:
            first.start()
            assert first_has_lock.wait(10)
            second.start()
            second.join(10)
            assert not second.is_alive()
            assert results["worker-2"] is None
        finally:
            release_first.set()
            first.join(10)
            second.join(10)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == {}
    assert len(set(backend_pids.values())) == 2
    assert results["worker-1"].job.id == job.id
    assert results["worker-2"] is None
    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.RUNNING
    assert job.worker_id == "worker-1"


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_claim_skips_one_invalid_head_without_duplicate(
    analysis_job_factory,
):
    from apps.training import internal_services

    assert connection.vendor == "postgresql"
    now = timezone.now()
    invalid = analysis_job_factory(created_at=now - timedelta(minutes=3))
    invalid.training_video.object_hash = ""
    invalid.training_video.save(update_fields=["object_hash", "updated_at"])
    healthy = {
        analysis_job_factory(created_at=now - timedelta(minutes=2)).id,
        analysis_job_factory(created_at=now - timedelta(minutes=1)).id,
    }
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def claim(worker_id):
        close_old_connections()
        try:
            barrier.wait(10)
            result = internal_services.claim_next_job(
                worker_id=worker_id,
                capabilities=[WorkerCapability(**CAPABILITY)],
                now=timezone.now(),
            )
            results.append(result.job.id if result else None)
        except Exception as exc:  # pragma: no cover - assertion below captures detail
            errors.append(exc)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=claim, args=(f"worker-{index}",)) for index in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert set(results) == healthy
    invalid.refresh_from_db()
    assert invalid.status == MotionAnalysisJob.Status.FAILED
