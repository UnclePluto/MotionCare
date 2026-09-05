from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone

from apps.training.models import MotionAnalysisJob, TrainingRecord, TrainingVideo


def _storage_module():
    from apps.training import motion_analysis_storage

    return motion_analysis_storage


@pytest.fixture
def analysis_job(project_patient, active_prescription, prescription_action):
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
        object_key="training-videos/1/original.mp4",
        object_hash="original-hash",
        content_type="video/mp4",
        size_bytes=1024,
        duration_seconds=60,
        status=TrainingVideo.Status.ATTACHED,
    )
    return MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=record,
        project_patient=project_patient,
        prescription_action=prescription_action,
        skeleton_bucket="analysis-skeletons",
        skeleton_object_key="motion-analysis/1/2026/09/job-uuid/skeleton.mp4",
    )


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_DOWNLOAD_DOMAIN="https://private.example.com",
    PP_MCARE_DOWNLOAD_TOKEN_TTL_SECONDS=3600,
    PP_MCARE_UPLOAD_TOKEN_TTL_SECONDS=10800,
)
def test_issue_grant_limits_upload_to_preallocated_key(analysis_job, monkeypatch):
    module = _storage_module()
    issued = []

    def upload_token(_, bucket, key, expires, policy):
        issued.append((bucket, key, expires, policy))
        return "sensitive-upload-token"

    monkeypatch.setattr(module.Auth, "upload_token", upload_token)
    now = timezone.now()

    grant = module.issue_storage_grant(analysis_job, now)

    assert issued == [
        (
            "analysis-skeletons",
            "motion-analysis/1/2026/09/job-uuid/skeleton.mp4",
            10800,
            {"insertOnly": 1},
        )
    ]
    assert grant.download.object_key == "training-videos/1/original.mp4"
    assert grant.download.expires_at == (now + timedelta(hours=1)).isoformat()
    assert grant.upload.object_key == "motion-analysis/1/2026/09/job-uuid/skeleton.mp4"
    assert grant.upload.expires_at == (now + timedelta(hours=3)).isoformat()
    assert "sensitive-upload-token" not in repr(grant)
    assert "token=" not in repr(grant)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("remote_metadata", "expected_detail"),
    [
        (
            {"hash": "unexpected-hash", "fsize": 256, "mimeType": "video/mp4"},
            "Hash 不匹配",
        ),
        (
            {"hash": "skeleton-hash", "fsize": 512, "mimeType": "video/mp4"},
            "大小不匹配",
        ),
        (
            {"hash": "skeleton-hash", "fsize": 256, "mimeType": "video/quicktime"},
            "类型不匹配",
        ),
    ],
)
def test_verify_skeleton_upload_rejects_remote_metadata_mismatch(
    analysis_job,
    monkeypatch,
    remote_metadata,
    expected_detail,
):
    module = _storage_module()
    monkeypatch.setattr(module, "stat_object_metadata", lambda **_: remote_metadata)

    with pytest.raises(ValidationError, match=expected_detail):
        module.verify_skeleton_upload(
            analysis_job,
            {
                "bucket": "analysis-skeletons",
                "object_key": "motion-analysis/1/2026/09/job-uuid/skeleton.mp4",
                "object_hash": "skeleton-hash",
                "size_bytes": 256,
                "content_type": "video/mp4",
            },
        )


@pytest.mark.django_db
def test_queue_skeleton_cleanup_keeps_only_the_job_skeleton_directory(analysis_job):
    module = _storage_module()

    first = module.queue_skeleton_cleanup(analysis_job)
    second = module.queue_skeleton_cleanup(analysis_job)

    assert first.pk == second.pk
    assert first.session_id == analysis_job.training_video.client_session_id
    assert first.bucket == "analysis-skeletons"
    assert first.attempt_key_prefix == "motion-analysis/1/2026/09/job-uuid/"
    assert first.max_attempt_number == 0
    assert first.canonical_key == "motion-analysis/1/2026/09/job-uuid/skeleton.mp4"
    assert first.retain_canonical is False
