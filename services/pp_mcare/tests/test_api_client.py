import json
import logging

import httpx
import pytest
from motion_analysis_contract import (
    PROTOCOL_VERSION,
    CompletionPayload,
    MotionCounts,
    SkeletonArtifact,
)

from pp_mcare.api_client import (
    MotionCareClient,
    MotionCareConflictError,
    MotionCareProtocolError,
    MotionCareUnavailableError,
    MotionCareValidationError,
)
from pp_mcare.config import Settings
from pp_mcare.safe_logging import install_safe_logging


CAPABILITY = {
    "action_source_key": "motion-resistance-shoulder-press",
    "algorithm_version": "PP-TinyPose_128x96",
    "rule_version": "shoulder-press-v2",
    "parameter_version": "shoulder-press-v2-defaults",
}
CLAIM_RESPONSE = {
    "protocol_version": PROTOCOL_VERSION,
    "job_id": 41,
    **CAPABILITY,
    "subject_tracker_version": "primary-subject-v1",
    "lease_token": "l" * 43,
    "lease_expires_at": "2026-09-05T10:00:00+00:00",
    "heartbeat_interval_seconds": 60,
    "download": {
        "url": "https://private.example/original.mp4?e=1&token=download-secret",
        "bucket": "original-videos",
        "object_key": "training-videos/41/original.mp4",
        "expires_at": "2026-09-05T11:00:00+00:00",
        "size_bytes": 1024,
        "content_type": "video/mp4",
    },
    "upload": {
        "bucket": "analysis-skeletons",
        "object_key": "motion-analysis/41/skeleton.mp4",
        "token": "upload-secret-token",
        "expires_at": "2026-09-05T13:00:00+00:00",
    },
}


def settings():
    return Settings(
        api_base_url="https://motioncare.example",
        service_token="service-token-secret",
        worker_id="worker-1",
    )


def completion_payload():
    return CompletionPayload(
        protocol_version=PROTOCOL_VERSION,
        lease_token="l" * 43,
        idempotency_key="complete-stable-001",
        algorithm_version="PP-TinyPose_128x96",
        rule_version="shoulder-press-v2",
        parameter_version="shoulder-press-v2-defaults",
        subject_tracker_version="primary-subject-v1",
        counts=MotionCounts(90, 80, 10),
        quality_summary={"confidence_level": 0.98, "quality_flags": ["stable"]},
        result_payload={"frames_decoded": 8929},
        skeleton=SkeletonArtifact(
            bucket="analysis-skeletons",
            object_key="motion-analysis/41/skeleton.mp4",
            object_hash="skeleton-hash",
            size_bytes=2048,
            duration_seconds=60,
            width=1920,
            height=1080,
            fps=30,
            content_type="video/mp4",
        ),
    )


def test_claim_uses_fixed_https_path_bearer_and_shared_capability_contract():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=CLAIM_RESPONSE)

    client = MotionCareClient(settings(), transport=httpx.MockTransport(handler))

    job = client.claim()

    assert job.job_id == 41
    assert job.download.url.endswith("token=download-secret")
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://motioncare.example/api/internal/motion-analysis/jobs/claim/"
    assert request.headers["Authorization"] == "Bearer service-token-secret"
    assert json.loads(request.content) == {
        "worker_id": "worker-1",
        "protocol_version": PROTOCOL_VERSION,
        "capabilities": [CAPABILITY],
    }


def test_claim_returns_none_for_204_without_parsing_a_body():
    client = MotionCareClient(
        settings(),
        transport=httpx.MockTransport(lambda request: httpx.Response(204, request=request)),
    )

    assert client.claim() is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={**CLAIM_RESPONSE, "unexpected": "field"}),
        httpx.Response(200, json={**CLAIM_RESPONSE, "protocol_version": "2"}),
    ],
)
def test_claim_bad_json_or_contract_is_not_retried(response):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        response.request = request
        return response

    client = MotionCareClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(MotionCareProtocolError):
        client.claim()

    assert calls == 1


@pytest.mark.parametrize("failure", ["timeout", "connect", "server"])
def test_claim_retries_only_transient_network_failures_with_incremental_backoff(failure):
    attempts = 0
    sleeps = []

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            if failure == "timeout":
                raise httpx.ReadTimeout(
                    "signed=https://evil.example/a?token=secret", request=request
                )
            if failure == "connect":
                raise httpx.ConnectError("/private/patient.mp4 token=secret", request=request)
            return httpx.Response(503, json={"detail": "Bearer secret"}, request=request)
        return httpx.Response(200, json=CLAIM_RESPONSE, request=request)

    client = MotionCareClient(
        settings(),
        transport=httpx.MockTransport(handler),
        sleeper=sleeps.append,
    )

    assert client.claim().job_id == 41
    assert attempts == 3
    assert sleeps == [1.0, 2.0]


@pytest.mark.parametrize("status", [400, 401, 404, 422])
def test_claim_4xx_is_not_retried(status):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(status, json={"detail": "invalid"}, request=request)

    client = MotionCareClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(MotionCareValidationError):
        client.claim()

    assert calls == 1


def test_redirect_is_not_followed_or_retried_and_cannot_receive_authorization():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            302,
            headers={"Location": "https://evil.example/steal"},
            request=request,
        )

    client = MotionCareClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(MotionCareProtocolError):
        client.claim()

    assert len(requests) == 1
    assert requests[0].url.host == "motioncare.example"


def test_transient_failure_stops_after_configured_three_attempts():
    attempts = 0
    sleeps = []

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, request=request)

    client = MotionCareClient(
        settings(),
        transport=httpx.MockTransport(handler),
        sleeper=sleeps.append,
    )

    with pytest.raises(MotionCareUnavailableError) as error:
        client.claim()

    assert attempts == 3
    assert sleeps == [1.0, 2.0]
    assert "service-token-secret" not in str(error.value)


def test_retry_log_keeps_only_the_fixed_relative_api_path(caplog):
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(204, request=request)

    client = MotionCareClient(
        settings(),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )

    with caplog.at_level(logging.WARNING, logger="pp_mcare.api_client"):
        assert client.claim() is None

    retry = next(record for record in caplog.records if record.msg == "motioncare_request_retry")
    assert retry.method == "POST"
    assert retry.path == "/api/internal/motion-analysis/jobs/claim/"
    assert retry.status == 503
    assert retry.attempt == 1
    assert retry.reason_code == "server_error"


def test_heartbeat_serializes_lease_but_returns_only_strict_safe_response():
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "protocol_version": PROTOCOL_VERSION,
                "job_id": 41,
                "lease_expires_at": "2026-09-05T10:05:00+00:00",
                "heartbeat_interval_seconds": 60,
                "current_stage": "upload",
            },
            request=request,
        )

    client = MotionCareClient(settings(), transport=httpx.MockTransport(handler))

    result = client.heartbeat(41, "l" * 43, "upload")

    assert result.job_id == 41
    assert result.current_stage == "upload"
    assert "l" * 43 not in repr(result)
    assert captured == [
        {
            "protocol_version": PROTOCOL_VERSION,
            "lease_token": "l" * 43,
            "stage": "upload",
        }
    ]


@pytest.mark.parametrize(
    ("status", "error_type"),
    [(400, MotionCareValidationError), (409, MotionCareConflictError)],
)
def test_heartbeat_exposes_clear_validation_and_conflict_semantics(status, error_type):
    client = MotionCareClient(
        settings(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={"detail": "secret"}, request=request)
        ),
    )

    with pytest.raises(error_type):
        client.heartbeat(41, "l" * 43, "upload")


def test_complete_retries_identical_shared_payload_and_stable_caller_idempotency_key():
    bodies = []

    def handler(request):
        bodies.append(bytes(request.content))
        if len(bodies) < 3:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            json={
                "protocol_version": PROTOCOL_VERSION,
                "job_id": 41,
                "status": "succeeded",
                "finished_at": "2026-09-05T10:10:00+00:00",
                "total_count": 90,
                "standard_count": 80,
                "nonstandard_count": 10,
            },
            request=request,
        )

    payload = completion_payload()
    client = MotionCareClient(
        settings(),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )

    result = client.complete(41, payload)

    assert result.status == "succeeded"
    assert result.counts == MotionCounts(90, 80, 10)
    assert len(bodies) == 3
    assert bodies[0] == bodies[1] == bodies[2]
    decoded = json.loads(bodies[0])
    assert decoded["idempotency_key"] == "complete-stable-001"
    assert decoded["algorithm_version"] == "PP-TinyPose_128x96"
    assert decoded["subject_tracker_version"] == "primary-subject-v1"


def test_fail_retries_identical_payload_and_never_generates_an_idempotency_key():
    bodies = []

    def handler(request):
        bodies.append(bytes(request.content))
        if len(bodies) == 1:
            return httpx.Response(500, request=request)
        return httpx.Response(
            200,
            json={
                "protocol_version": PROTOCOL_VERSION,
                "job_id": 41,
                "status": "failed",
                "finished_at": "2026-09-05T10:10:00+00:00",
            },
            request=request,
        )

    client = MotionCareClient(
        settings(),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    )

    result = client.fail(
        41,
        lease_token="l" * 43,
        idempotency_key="fail-stable-001",
        failure_code="processor_error",
        summary="任务处理异常",
        stage_timings={"processor": 1.25},
    )

    assert result.status == "failed"
    assert bodies[0] == bodies[1]
    assert json.loads(bodies[0]) == {
        "protocol_version": PROTOCOL_VERSION,
        "lease_token": "l" * 43,
        "idempotency_key": "fail-stable-001",
        "failure_code": "processor_error",
        "summary": "任务处理异常",
        "stage_timings": {"processor": 1.25},
    }


def test_client_repr_exceptions_and_filtered_logs_redact_secrets(caplog):
    token = "service-token-secret"
    signed_url = "https://private.example/video.mp4?token=signed-secret"
    local_path = "/opt/motioncare-analysis/tmp/jobs/41/patient.mp4"
    patient_name = "Alice-Private-Patient"
    logger = logging.getLogger("pp_mcare.test.security")
    install_safe_logging(logger, secrets=(token,))
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError(
            f"Bearer {token} {signed_url} {local_path}",
            request=request,
        )

    client = MotionCareClient(
        settings(),
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
        logger=logger,
    )

    with caplog.at_level(logging.DEBUG, logger=logger.name):
        with pytest.raises(MotionCareUnavailableError) as error:
            client.claim()
        try:
            raise RuntimeError(f"Bearer {token} {signed_url} {local_path}")
        except RuntimeError:
            logger.exception(
                "unsafe exception %s %s",
                signed_url,
                patient_name,
                extra={
                    "unsafe_payload": local_path,
                    "patient_info": patient_name,
                    "reason_code": "test_failure",
                },
            )

    rendered = caplog.text + repr(client) + repr(error.value) + str(error.value)
    for forbidden in (
        token,
        signed_url,
        "signed-secret",
        local_path,
        "patient.mp4",
        patient_name,
    ):
        assert forbidden not in rendered
    assert attempts == 3
    assert "<redacted>" in rendered
