from types import SimpleNamespace
from unittest.mock import ANY, Mock

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
        progress_handler=ANY,
    )
    upload_token.assert_called_once_with("motioncare-training", "training-videos/1/final.mp4", 3600)


@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_UPLOAD_REQUEST_TIMEOUT_SECONDS=7,
    QINIU_UPLOAD_REQUEST_RETRIES=1,
)
def test_upload_local_video_heartbeats_and_enforces_deadline(tmp_path, monkeypatch):
    path = _local_video(tmp_path)
    clock = Mock(return_value=5.0)
    heartbeat = Mock()

    def late_upload(*args, progress_handler, **kwargs):
        progress_handler(1, 2)
        clock.return_value = 11.0
        progress_handler(2, 2)
        return ({"key": "training-videos/1/attempt-1.mp4", "hash": etag(str(path))}, _stat_response())

    auth = Auth("ak-test", "sk-test")
    monkeypatch.setattr(auth, "upload_token", Mock(return_value="upload-token"))
    monkeypatch.setattr(
        BucketManager,
        "stat",
        Mock(return_value=(None, _stat_response(status_code=612, error="no such file"))),
    )
    monkeypatch.setattr(training_qiniu, "put_file", late_upload)
    monkeypatch.setattr(training_qiniu, "Auth", Mock(return_value=auth))
    configure_sdk = Mock()
    monkeypatch.setattr(training_qiniu.qiniu.config, "set_default", configure_sdk)

    with pytest.raises(ValidationError, match="上传超时"):
        training_qiniu.upload_local_video(
            path=path,
            bucket="motioncare-training",
            key="training-videos/1/attempt-1.mp4",
            deadline_monotonic=10.0,
            on_progress=heartbeat,
            monotonic=clock,
        )

    heartbeat.assert_called_once_with(1, 2)
    configure_sdk.assert_called_once_with(connection_timeout=7, connection_retries=1)


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


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_upload_local_video_rejects_matching_existing_object_with_wrong_mime(
    tmp_path, monkeypatch
):
    path = _local_video(tmp_path)
    metadata = {
        **_matching_metadata(path),
        "mimeType": "application/octet-stream",
    }
    put_file = Mock()
    monkeypatch.setattr(
        BucketManager,
        "stat",
        Mock(return_value=(metadata, _stat_response())),
    )
    monkeypatch.setattr(training_qiniu, "put_file", put_file)

    with pytest.raises(ValidationError, match="类型不匹配"):
        training_qiniu.upload_local_video(
            path=path,
            bucket="motioncare-training",
            key="training-videos/1/final.mp4",
        )

    put_file.assert_not_called()


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_delete_object_if_exists_treats_qiniu_612_as_success(monkeypatch):
    delete = Mock(return_value=(None, _stat_response(status_code=612, error="no such file")))
    monkeypatch.setattr(BucketManager, "delete", delete)

    training_qiniu.delete_object_if_exists(
        bucket="motioncare-training",
        key="training-videos/1/final.mp4",
    )

    delete.assert_called_once_with("motioncare-training", "training-videos/1/final.mp4")


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_publish_attempt_moves_without_force_and_stats_canonical(tmp_path, monkeypatch):
    path = _local_video(tmp_path)
    metadata = _matching_metadata(path)
    canonical_key = "training-videos/1/final.mp4"
    attempt_key = "training-videos/attempts/session/attempt-1.mp4"
    stat = Mock(
        side_effect=[
            (None, _stat_response(status_code=612, error="no such file")),
            (metadata, _stat_response()),
        ]
    )
    move = Mock(return_value=(None, _stat_response()))
    monkeypatch.setattr(BucketManager, "stat", stat)
    monkeypatch.setattr(BucketManager, "move", move)

    published = training_qiniu.publish_attempt_to_canonical(
        bucket="motioncare-training",
        attempt_key=attempt_key,
        canonical_key=canonical_key,
        expected_hash=metadata["hash"],
        expected_size_bytes=metadata["fsize"],
        assert_lease=Mock(),
    )

    assert published == metadata
    move.assert_called_once_with(
        "motioncare-training",
        attempt_key,
        "motioncare-training",
        canonical_key,
        force="false",
    )
    assert stat.call_args_list[-1].args == ("motioncare-training", canonical_key)


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_publish_attempt_recovers_duplicate_move_612_from_matching_canonical(
    tmp_path, monkeypatch
):
    path = _local_video(tmp_path)
    metadata = _matching_metadata(path)
    stat = Mock(
        side_effect=[
            (None, _stat_response(status_code=612, error="no such file")),
            (metadata, _stat_response()),
        ]
    )
    monkeypatch.setattr(BucketManager, "stat", stat)
    monkeypatch.setattr(
        BucketManager,
        "move",
        Mock(return_value=(None, _stat_response(status_code=612, error="no such file"))),
    )

    published = training_qiniu.publish_attempt_to_canonical(
        bucket="motioncare-training",
        attempt_key="training-videos/attempts/session/attempt-1.mp4",
        canonical_key="training-videos/1/final.mp4",
        expected_hash=metadata["hash"],
        expected_size_bytes=metadata["fsize"],
        assert_lease=Mock(),
    )

    assert published == metadata


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_publish_attempt_rechecks_lease_after_stat_before_move(tmp_path, monkeypatch):
    path = _local_video(tmp_path)
    metadata = _matching_metadata(path)
    move = Mock()
    monkeypatch.setattr(
        BucketManager,
        "stat",
        Mock(return_value=(None, _stat_response(status_code=612, error="no such file"))),
    )
    monkeypatch.setattr(BucketManager, "move", move)

    with pytest.raises(RuntimeError, match="lease lost"):
        training_qiniu.publish_attempt_to_canonical(
            bucket="motioncare-training",
            attempt_key="training-videos/attempts/session/attempt-1.mp4",
            canonical_key="training-videos/1/final.mp4",
            expected_hash=metadata["hash"],
            expected_size_bytes=metadata["fsize"],
            assert_lease=Mock(side_effect=RuntimeError("lease lost")),
        )

    move.assert_not_called()


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_retry_after_move_before_db_attach_reuses_canonical_without_second_upload(
    tmp_path, monkeypatch
):
    path = _local_video(tmp_path)
    metadata = _matching_metadata(path)
    upload = Mock()
    move = Mock()
    lease = Mock()
    monkeypatch.setattr(
        training_qiniu,
        "stat_object_metadata_or_none",
        Mock(return_value=metadata),
    )
    monkeypatch.setattr(training_qiniu, "upload_local_video", upload)
    monkeypatch.setattr(training_qiniu, "publish_attempt_to_canonical", move)

    published = training_qiniu.upload_and_publish_local_video(
        path=path,
        bucket="motioncare-training",
        attempt_key="training-videos/attempts/session/attempt-2.mp4",
        canonical_key="training-videos/1/final.mp4",
        assert_lease=lease,
    )

    assert published == metadata
    upload.assert_not_called()
    move.assert_not_called()
    lease.assert_called_once_with()


@override_settings(QINIU_ACCESS_KEY="ak-test", QINIU_SECRET_KEY="sk-test")
def test_upload_and_publish_stale_lease_never_moves(tmp_path, monkeypatch):
    path = _local_video(tmp_path)
    metadata = _matching_metadata(path)
    move = Mock()
    monkeypatch.setattr(
        training_qiniu,
        "stat_object_metadata_or_none",
        Mock(return_value=None),
    )
    monkeypatch.setattr(training_qiniu, "upload_local_video", Mock(return_value=metadata))
    monkeypatch.setattr(training_qiniu, "publish_attempt_to_canonical", move)

    with pytest.raises(RuntimeError, match="lease lost"):
        training_qiniu.upload_and_publish_local_video(
            path=path,
            bucket="motioncare-training",
            attempt_key="training-videos/attempts/session/attempt-1.mp4",
            canonical_key="training-videos/1/final.mp4",
            assert_lease=Mock(side_effect=RuntimeError("lease lost")),
        )

    move.assert_not_called()


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
