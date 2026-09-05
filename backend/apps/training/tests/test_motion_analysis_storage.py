from datetime import timedelta
import os
import subprocess
import sys
import threading
from unittest.mock import Mock

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.db.models.query import QuerySet
from django.test import override_settings
from django.utils import timezone

from apps.training.models import (
    MotionAnalysisJob,
    QiniuCleanupTombstone,
    TrainingRecord,
    TrainingVideo,
)


def _storage_module():
    from apps.training import motion_analysis_storage

    return motion_analysis_storage


@pytest.fixture
def analysis_job(settings, project_patient, active_prescription, prescription_action):
    settings.QINIU_BUCKET = "analysis-skeletons"
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
        skeleton_object_key=(
            f"motion-analysis/{project_patient.id}/2026/09/"
            "11111111-1111-4111-8111-111111111111/skeleton.mp4"
        ),
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
            analysis_job.skeleton_object_key,
            10800,
            {"insertOnly": 1},
        )
    ]
    assert grant.download.object_key == "training-videos/1/original.mp4"
    assert grant.download.expires_at == (now + timedelta(hours=1)).isoformat()
    assert grant.upload.object_key == analysis_job.skeleton_object_key
    assert grant.upload.expires_at == (now + timedelta(hours=3)).isoformat()
    assert "sensitive-upload-token" not in repr(grant)
    assert "token=" not in repr(grant)


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_DOWNLOAD_DOMAIN="https://private.example.com",
)
@pytest.mark.parametrize(
    ("bucket", "object_key_case"),
    [
        ("", "valid"),
        ("analysis-skeletons", "empty"),
        ("analysis-skeletons", "wrong_project"),
        ("analysis-skeletons", "wrong_filename"),
    ],
)
def test_issue_grant_rejects_empty_or_out_of_scope_skeleton_destination(
    analysis_job,
    monkeypatch,
    bucket,
    object_key_case,
):
    module = _storage_module()
    object_keys = {
        "valid": analysis_job.skeleton_object_key,
        "empty": "",
        "wrong_project": analysis_job.skeleton_object_key.replace(
            f"motion-analysis/{analysis_job.project_patient_id}/",
            f"motion-analysis/{analysis_job.project_patient_id + 1}/",
            1,
        ),
        "wrong_filename": analysis_job.skeleton_object_key.removesuffix("skeleton.mp4")
        + "result.mp4",
    }
    object_key = object_keys[object_key_case]
    analysis_job.skeleton_bucket = bucket
    analysis_job.skeleton_object_key = object_key or None
    analysis_job.save(update_fields=["skeleton_bucket", "skeleton_object_key", "updated_at"])
    monkeypatch.setattr(
        module.Auth,
        "upload_token",
        lambda *_args, **_kwargs: pytest.fail("不应为无效骨架目标签发 token"),
    )

    with pytest.raises(ValidationError, match="骨架对象"):
        module.issue_storage_grant(analysis_job, timezone.now())


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
                "object_key": analysis_job.skeleton_object_key,
                "object_hash": "skeleton-hash",
                "size_bytes": 256,
                "content_type": "video/mp4",
            },
        )


@pytest.mark.django_db
@override_settings(
    PP_MCARE_OBJECT_STAT_TIMEOUT_SECONDS=4,
    PP_MCARE_OBJECT_STAT_RETRIES=2,
)
def test_verify_skeleton_upload_applies_bounded_qiniu_stat_settings(
    analysis_job,
    monkeypatch,
):
    module = _storage_module()
    configure = Mock()
    monkeypatch.setattr(module.qiniu.config, "set_default", configure)
    monkeypatch.setattr(
        module,
        "stat_object_metadata",
        Mock(return_value={"hash": "skeleton-hash", "fsize": 256, "mimeType": "video/mp4"}),
    )

    module.verify_skeleton_upload(
        analysis_job,
        {
            "bucket": "analysis-skeletons",
            "object_key": analysis_job.skeleton_object_key,
            "object_hash": "skeleton-hash",
            "size_bytes": 256,
            "content_type": "video/mp4",
        },
    )

    configure.assert_called_once_with(connection_timeout=4, connection_retries=2)


@pytest.mark.parametrize(
    "setting_name",
    ["PP_MCARE_OBJECT_STAT_TIMEOUT_SECONDS", "PP_MCARE_OBJECT_STAT_RETRIES"],
)
def test_invalid_qiniu_stat_environment_setting_fails_at_startup(settings, setting_name):
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=settings.BASE_DIR,
        env={**os.environ, setting_name: "0"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert setting_name in result.stderr


@pytest.mark.django_db
def test_queue_skeleton_cleanup_keeps_only_the_job_skeleton_directory(analysis_job):
    module = _storage_module()

    first = module.queue_skeleton_cleanup(analysis_job)
    second = module.queue_skeleton_cleanup(analysis_job)

    assert first.pk == second.pk
    assert first.session_id == analysis_job.training_video.client_session_id
    assert first.bucket == "analysis-skeletons"
    expected_prefix = analysis_job.skeleton_object_key.rpartition("/")[0] + "/"
    assert first.attempt_key_prefix == expected_prefix
    assert first.max_attempt_number == 0
    assert first.canonical_key == analysis_job.skeleton_object_key
    assert first.retain_canonical is False


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_skeleton_tombstone_unique_race_rereads_winner(
    analysis_job,
    monkeypatch,
):
    module = _storage_module()
    assert connection.vendor == "postgresql"
    expected_prefix = analysis_job.skeleton_object_key.rpartition("/")[0] + "/"
    initial_reads = threading.Barrier(2)
    read_lock = threading.Lock()
    local_state = threading.local()
    initial_miss_count = 0
    tombstone_ids = []
    errors = []
    original_get = QuerySet.get

    def synchronized_get(queryset, *args, **kwargs):
        nonlocal initial_miss_count
        try:
            return original_get(queryset, *args, **kwargs)
        except QiniuCleanupTombstone.DoesNotExist:
            is_target_initial_read = (
                queryset.model is QiniuCleanupTombstone
                and kwargs.get("attempt_key_prefix") == expected_prefix
                and not getattr(local_state, "waited", False)
            )
            if is_target_initial_read:
                local_state.waited = True
                with read_lock:
                    initial_miss_count += 1
                initial_reads.wait(timeout=5)
            raise

    def register_cleanup():
        close_old_connections()
        try:
            thread_job = MotionAnalysisJob.objects.select_related("training_video").get(
                pk=analysis_job.pk
            )
            tombstone_ids.append(module.queue_skeleton_cleanup(thread_job).id)
        except Exception as exc:  # pragma: no branch - thread result capture
            errors.append(exc)
        finally:
            close_old_connections()

    monkeypatch.setattr(QuerySet, "get", synchronized_get)
    threads = [threading.Thread(target=register_cleanup) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert initial_miss_count == 2
    assert errors == []
    assert len(set(tombstone_ids)) == 1
    assert QiniuCleanupTombstone.objects.filter(attempt_key_prefix=expected_prefix).count() == 1
