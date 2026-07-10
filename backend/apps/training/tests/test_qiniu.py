from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from qiniu import Auth, BucketManager, etag

from apps.training.models import MotionAnalysisJob, TrainingVideo
from apps.training import qiniu as training_qiniu
from apps.training.qiniu import private_download_url


def _stat_response(*, status_code=200, error=None):
    return SimpleNamespace(status_code=status_code, error=error)


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


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_stat_object_metadata_or_none_returns_none_only_for_612(monkeypatch):
    stat = Mock(return_value=(None, _stat_response(status_code=612, error="no such file")))
    monkeypatch.setattr(BucketManager, "stat", stat)

    assert training_qiniu.stat_object_metadata_or_none(
        bucket="motioncare-training",
        key="training-videos/1/missing.mp4",
    ) is None


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_stat_object_metadata_or_none_rejects_non_612_error(monkeypatch):
    monkeypatch.setattr(
        BucketManager,
        "stat",
        Mock(return_value=(None, _stat_response(status_code=401, error="bad credentials"))),
    )

    with pytest.raises(ValidationError, match="无法读取"):
        training_qiniu.stat_object_metadata_or_none(
            bucket="motioncare-training",
            key="training-videos/1/video.mp4",
        )


def _local_video(tmp_path):
    path = tmp_path / "final.mp4"
    path.write_bytes(b"final-video-bytes")
    return path


def _matching_metadata(path):
    return {"hash": etag(str(path)), "fsize": path.stat().st_size, "mimeType": "video/mp4"}


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_upload_local_video_stats_after_successful_upload(tmp_path, monkeypatch):
    path = _local_video(tmp_path)
    stat = Mock(side_effect=[
        (None, _stat_response(status_code=612, error="no such file")),
        (_matching_metadata(path), _stat_response()),
    ])
    put_file = Mock(return_value=({"key": "training-videos/1/final.mp4", "hash": etag(str(path))}, _stat_response()))
    upload_token = Mock(return_value="upload-token")
    auth = Auth("ak-test", "sk-test")
    monkeypatch.setattr(auth, "upload_token", upload_token)
    monkeypatch.setattr(BucketManager, "stat", stat)
    monkeypatch.setattr(training_qiniu, "put_file", put_file)
    monkeypatch.setattr(training_qiniu, "Auth", Mock(return_value=auth))

    metadata = training_qiniu.upload_local_video(
        path=path,
        bucket="motioncare-training",
        key="training-videos/1/final.mp4",
    )

    assert metadata == _matching_metadata(path)
    assert stat.call_count == 2
    put_file.assert_called_once_with(
        "upload-token",
        "training-videos/1/final.mp4",
        str(path),
        check_crc=True,
        mime_type="video/mp4",
    )
    upload_token.assert_called_once_with("motioncare-training", "training-videos/1/final.mp4", 3600)


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_upload_local_video_reuses_matching_existing_object(tmp_path, monkeypatch):
    path = _local_video(tmp_path)
    stat = Mock(return_value=(_matching_metadata(path), _stat_response()))
    put_file = Mock()
    monkeypatch.setattr(BucketManager, "stat", stat)
    monkeypatch.setattr(training_qiniu, "put_file", put_file)

    metadata = training_qiniu.upload_local_video(
        path=path,
        bucket="motioncare-training",
        key="training-videos/1/final.mp4",
    )

    assert metadata == _matching_metadata(path)
    stat.assert_called_once_with("motioncare-training", "training-videos/1/final.mp4")
    put_file.assert_not_called()


@pytest.mark.parametrize(
    "metadata",
    [
        {"hash": "other-hash", "fsize": len(b"final-video-bytes"), "mimeType": "video/mp4"},
        {"hash": None, "fsize": 1, "mimeType": "video/mp4"},
    ],
)
@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_upload_local_video_rejects_conflicting_existing_object(tmp_path, monkeypatch, metadata):
    path = _local_video(tmp_path)
    put_file = Mock()
    monkeypatch.setattr(BucketManager, "stat", Mock(return_value=(metadata, _stat_response())))
    monkeypatch.setattr(training_qiniu, "put_file", put_file)

    with pytest.raises(ValidationError, match="冲突"):
        training_qiniu.upload_local_video(
            path=path,
            bucket="motioncare-training",
            key="training-videos/1/final.mp4",
        )

    put_file.assert_not_called()


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_upload_local_video_rejects_upload_result_mismatch(tmp_path, monkeypatch):
    path = _local_video(tmp_path)
    stat = Mock(return_value=(None, _stat_response(status_code=612, error="no such file")))
    put_file = Mock(return_value=({"key": "wrong-key", "hash": etag(str(path))}, _stat_response()))
    auth = Auth("ak-test", "sk-test")
    monkeypatch.setattr(auth, "upload_token", Mock(return_value="upload-token"))
    monkeypatch.setattr(BucketManager, "stat", stat)
    monkeypatch.setattr(training_qiniu, "put_file", put_file)
    monkeypatch.setattr(training_qiniu, "Auth", Mock(return_value=auth))

    with pytest.raises(ValidationError, match="结果不匹配"):
        training_qiniu.upload_local_video(
            path=path,
            bucket="motioncare-training",
            key="training-videos/1/final.mp4",
        )

    assert stat.call_count == 1


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
    )
    job = MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=None,
        project_patient=project_patient,
        prescription_action=prescription_action,
        algorithm_name="pp-tiny-pose",
        rule_version="shoulder-press-v1",
    )

    assert video.status == TrainingVideo.Status.RECORDING
    assert job.status == MotionAnalysisJob.Status.PENDING
