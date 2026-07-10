import base64
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from qiniu import BucketManager

from apps.training.models import MotionAnalysisJob, TrainingVideo
from apps.training import qiniu as training_qiniu
from apps.training.qiniu import generate_upload_token, private_download_url


def _stat_response(*, status_code=200, error=None):
    return SimpleNamespace(status_code=status_code, error=error)


@pytest.mark.django_db
@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_generate_upload_token_contains_fixed_bucket_key_scope():
    token = generate_upload_token(
        bucket="motioncare",
        key="training-videos/1/2026/07/10/video.mp4",
        expires_at=1783692000,
    )

    assert token == (
        "ak-test:H1S1eXs9gKrJf9xztDGLb3R4fPE=:"
        "eyJzY29wZSI6Im1vdGlvbmNhcmU6dHJhaW5pbmctdmlkZW9zLzEvMjAyNi8wNy8xMC92aWRlby5tcDQiLCJkZWFkbGluZSI6MTc4MzY5MjAwMCwicmV0dXJuQm9keSI6IntcImtleVwiOlwiJChrZXkpXCIsXCJoYXNoXCI6XCIkKGV0YWcpXCIsXCJzaXplXCI6JChmc2l6ZSl9In0="
    )
    access_key, encoded_sign, encoded_policy = token.split(":")
    assert access_key == "ak-test"
    assert encoded_sign
    policy = json.loads(base64.urlsafe_b64decode(encoded_policy).decode("utf-8"))
    assert policy["scope"] == "motioncare:training-videos/1/2026/07/10/video.mp4"
    assert policy["deadline"] == 1783692000


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_private_download_url_adds_deadline_and_token():
    url = private_download_url(
        "https://cdn.example.com/training-videos/a.mp4",
        expires_at=1783692000,
    )

    assert url == (
        "https://cdn.example.com/training-videos/a.mp4?e=1783692000&"
        "token=ak-test:A5Sdr1PWsR-H9KVvZFsLggKOKSc%3D"
    )


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_stat_object_metadata_uses_bucket_manager(monkeypatch):
    stat = Mock(
        return_value=(
            {"hash": "trusted-hash", "fsize": 1024, "mimeType": "video/mp4"},
            _stat_response(),
        )
    )
    monkeypatch.setattr(BucketManager, "stat", stat)

    metadata = training_qiniu.stat_object_metadata(
        bucket="motioncare-training",
        key="training-videos/1/video.mp4",
    )

    assert metadata == {
        "hash": "trusted-hash",
        "fsize": 1024,
        "mimeType": "video/mp4",
    }
    stat.assert_called_once_with("motioncare-training", "training-videos/1/video.mp4")


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_stat_object_metadata_rejects_missing_object(monkeypatch):
    stat = Mock(return_value=(None, _stat_response(status_code=612, error="no such file")))
    monkeypatch.setattr(BucketManager, "stat", stat)

    with pytest.raises(ValidationError, match="对象不存在"):
        training_qiniu.stat_object_metadata(
            bucket="motioncare-training",
            key="training-videos/1/missing.mp4",
        )


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_stat_object_metadata_converts_sdk_failure_to_validation_error(monkeypatch):
    monkeypatch.setattr(BucketManager, "stat", Mock(side_effect=RuntimeError("network down")))

    with pytest.raises(ValidationError, match="无法读取"):
        training_qiniu.stat_object_metadata(
            bucket="motioncare-training",
            key="training-videos/1/video.mp4",
        )


@pytest.mark.parametrize(
    ("metadata", "expected_detail"),
    [
        (
            {"hash": "another-hash", "fsize": 1024, "mimeType": "video/mp4"},
            "Hash 不匹配",
        ),
        (
            {"hash": "trusted-hash", "fsize": 2048, "mimeType": "video/mp4"},
            "大小不匹配",
        ),
        (
            {"hash": "trusted-hash", "fsize": 1024, "mimeType": "image/png"},
            "类型不匹配",
        ),
        (
            {"hash": "trusted-hash", "fsize": 1024, "mimeType": "video/quicktime"},
            "类型不匹配",
        ),
    ],
)
def test_validate_object_metadata_rejects_untrusted_values(metadata, expected_detail):
    with pytest.raises(ValidationError, match=expected_detail):
        training_qiniu.validate_object_metadata(
            metadata,
            expected_hash="trusted-hash",
            expected_size_bytes=1024,
            expected_content_type="video/mp4",
        )


def test_validate_object_metadata_accepts_normalized_video_mime_type():
    training_qiniu.validate_object_metadata(
        {"hash": "trusted-hash", "fsize": 1024, "mimeType": "video/mp4; charset=binary"},
        expected_hash="trusted-hash",
        expected_size_bytes=1024,
        expected_content_type="video/mp4",
    )


@pytest.mark.django_db
def test_training_video_and_analysis_job_models_are_available(
    project_patient,
    active_prescription,
    prescription_action,
):
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key="training-videos/1/a.mp4",
        content_type="video/mp4",
        size_bytes=100,
        duration_seconds=30,
        upload_token_expires_at="2026-07-10T10:00:00+08:00",
    )
    job = MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=None,
        project_patient=project_patient,
        prescription_action=prescription_action,
        algorithm_name="pp-tiny-pose",
        rule_version="shoulder-press-v1",
    )

    assert video.status == TrainingVideo.Status.UPLOADING
    assert job.status == MotionAnalysisJob.Status.PENDING
