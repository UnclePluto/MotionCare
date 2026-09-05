import pytest

from motion_analysis_contract import (
    PROTOCOL_VERSION,
    ClaimedJob,
    CompletionPayload,
    ContractValidationError,
    SkeletonArtifact,
    WorkerCapability,
    MotionCounts,
    capability_key,
    validate_counts,
)


CLAIM_RESPONSE = {
    "protocol_version": PROTOCOL_VERSION,
    "job_id": 1,
    "action_source_key": "motion-resistance-shoulder-press",
    "algorithm_version": "PP-TinyPose_128x96",
    "rule_version": "shoulder-press-v2",
    "parameter_version": "shoulder-press-v2-defaults",
    "subject_tracker_version": "primary-subject-v1",
    "lease_token": "lease-token",
    "lease_expires_at": "2026-09-05T10:00:00Z",
    "heartbeat_interval_seconds": 60,
    "download": {
        "url": "https://example.invalid/original.mp4",
        "bucket": "motion-analysis",
        "object_key": "motion-analysis/1/2026/09/job/original.mp4",
        "expires_at": "2026-09-05T10:00:00Z",
        "size_bytes": 1024,
        "content_type": "video/mp4",
    },
    "upload": {
        "bucket": "motion-analysis",
        "object_key": "motion-analysis/1/2026/09/job/skeleton.mp4",
        "token": "upload-token",
        "expires_at": "2026-09-05T12:00:00Z",
    },
}


def test_validate_counts_rejects_bool_and_broken_total():
    with pytest.raises(ContractValidationError):
        validate_counts(
            {"total_count": True, "standard_count": 1, "nonstandard_count": 0}
        )

    with pytest.raises(ContractValidationError):
        validate_counts(
            {"total_count": 3, "standard_count": 1, "nonstandard_count": 1}
        )


def test_direct_dto_construction_rejects_invalid_counts_and_non_json_values():
    with pytest.raises(ContractValidationError):
        MotionCounts(3, 1, 1)

    skeleton = SkeletonArtifact(
        bucket="motion-analysis",
        object_key="motion-analysis/1/2026/09/job/skeleton.mp4",
        object_hash="sha256:deadbeef",
        size_bytes=2048,
        duration_seconds=12.5,
        width=1920,
        height=1080,
        fps=30,
        content_type="video/mp4",
    )
    with pytest.raises(ContractValidationError):
        CompletionPayload(
            protocol_version=PROTOCOL_VERSION,
            lease_token="lease-token",
            idempotency_key="idem-001",
            algorithm_version="PP-TinyPose_128x96",
            rule_version="shoulder-press-v2",
            parameter_version="shoulder-press-v2-defaults",
            subject_tracker_version="primary-subject-v1",
            counts=MotionCounts(0, 0, 0),
            quality_summary={"invalid": object()},
            result_payload={},
            skeleton=skeleton,
        )


def test_direct_skeleton_construction_rejects_nan_and_missing_content_type():
    fields = {
        "bucket": "motion-analysis",
        "object_key": "motion-analysis/1/2026/09/job/skeleton.mp4",
        "object_hash": "sha256:deadbeef",
        "size_bytes": 2048,
        "duration_seconds": 12.5,
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "content_type": "video/mp4",
    }
    with pytest.raises(ContractValidationError):
        SkeletonArtifact(**{**fields, "fps": float("nan")})

    payload = dict(fields)
    del payload["content_type"]
    with pytest.raises(ContractValidationError):
        SkeletonArtifact.from_dict(payload)


def test_claimed_job_round_trip_keeps_exact_storage_scope():
    job = ClaimedJob.from_dict(CLAIM_RESPONSE)

    assert job.upload.object_key == "motion-analysis/1/2026/09/job/skeleton.mp4"
    assert job.action_source_key == "motion-resistance-shoulder-press"
    assert job.protocol_version == PROTOCOL_VERSION


def test_storage_grant_and_claim_repr_redact_urls_and_credentials():
    job = ClaimedJob.from_dict(CLAIM_RESPONSE)

    for value in (job.download, job.upload, job):
        rendered = repr(value)
        assert "https://example.invalid/original.mp4" not in rendered
        assert "upload-token" not in rendered
        assert "lease-token" not in rendered
        assert "<redacted>" in rendered


def test_claimed_job_rejects_unknown_protocol_version():
    payload = dict(CLAIM_RESPONSE)
    payload["protocol_version"] = "2"

    with pytest.raises(ContractValidationError):
        ClaimedJob.from_dict(payload)


def test_claimed_job_rejects_missing_upload_token():
    payload = dict(CLAIM_RESPONSE)
    payload["upload"] = dict(payload["upload"])
    del payload["upload"]["token"]

    with pytest.raises(ContractValidationError):
        ClaimedJob.from_dict(payload)


def test_from_dict_rejects_missing_capability_field_and_non_string_credential():
    with pytest.raises(ContractValidationError):
        WorkerCapability.from_dict(
            {
                "action_source_key": "motion-resistance-shoulder-press",
                "algorithm_version": "PP-TinyPose_128x96",
                "rule_version": "shoulder-press-v2",
            }
        )

    payload = dict(CLAIM_RESPONSE)
    payload["upload"] = dict(payload["upload"])
    payload["upload"]["token"] = 1
    with pytest.raises(ContractValidationError):
        ClaimedJob.from_dict(payload)


def test_completion_payload_round_trip_flattens_counts_and_keeps_json_base_types():
    payload = CompletionPayload.from_dict(
        {
            "protocol_version": PROTOCOL_VERSION,
            "lease_token": "lease-token",
            "idempotency_key": "idem-001",
            "algorithm_version": "PP-TinyPose_128x96",
            "rule_version": "shoulder-press-v2",
            "parameter_version": "shoulder-press-v2-defaults",
            "subject_tracker_version": "primary-subject-v1",
            "total_count": 90,
            "standard_count": 80,
            "nonstandard_count": 10,
            "quality_summary": {
                "confidence_level": 0.98,
                "quality_flags": ["stable", "complete"],
                "action_specific_details": {"side": "left"},
            },
            "result_payload": {
                "frames": [1, 2, 3],
                "notes": None,
            },
            "skeleton": {
                "bucket": "motion-analysis",
                "object_key": "motion-analysis/1/2026/09/job/skeleton.mp4",
                "object_hash": "sha256:deadbeef",
                "size_bytes": 2048,
                "duration_seconds": 12.5,
                "width": 1920,
                "height": 1080,
                "fps": 30,
                "content_type": "video/mp4",
            },
        }
    )

    assert payload.counts == MotionCounts(90, 80, 10)
    assert payload.to_dict()["total_count"] == 90
    assert payload.to_dict()["algorithm_version"] == "PP-TinyPose_128x96"
    assert payload.to_dict()["rule_version"] == "shoulder-press-v2"
    assert payload.to_dict()["parameter_version"] == "shoulder-press-v2-defaults"
    assert payload.to_dict()["subject_tracker_version"] == "primary-subject-v1"
    assert payload.to_dict()["skeleton"]["object_key"] == "motion-analysis/1/2026/09/job/skeleton.mp4"


@pytest.mark.parametrize(
    "field_name",
    [
        "algorithm_version",
        "rule_version",
        "parameter_version",
        "subject_tracker_version",
    ],
)
def test_completion_payload_requires_every_execution_version(field_name):
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "lease_token": "lease-token",
        "idempotency_key": "idem-001",
        "algorithm_version": "PP-TinyPose_128x96",
        "rule_version": "shoulder-press-v2",
        "parameter_version": "shoulder-press-v2-defaults",
        "subject_tracker_version": "primary-subject-v1",
        "total_count": 1,
        "standard_count": 1,
        "nonstandard_count": 0,
        "quality_summary": {},
        "result_payload": {},
        "skeleton": {
            "bucket": "motion-analysis",
            "object_key": "motion-analysis/1/2026/09/job/skeleton.mp4",
            "object_hash": "sha256:deadbeef",
            "size_bytes": 2048,
            "duration_seconds": 12.5,
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "content_type": "video/mp4",
        },
    }
    del payload[field_name]

    with pytest.raises(ContractValidationError, match=field_name):
        CompletionPayload.from_dict(payload)


def test_capability_key_uses_all_dimensions_in_order():
    capability = WorkerCapability(
        action_source_key="motion-resistance-shoulder-press",
        algorithm_version="PP-TinyPose_128x96",
        rule_version="shoulder-press-v2",
        parameter_version="shoulder-press-v2-defaults",
    )

    assert capability_key(capability) == (
        "motion-resistance-shoulder-press",
        "PP-TinyPose_128x96",
        "shoulder-press-v2",
        "shoulder-press-v2-defaults",
    )
