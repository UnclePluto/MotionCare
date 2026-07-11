import uuid

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_qiniu_cleanup_upgrade_repairs_attempt_and_canonical_keys(
    project_patient,
    active_prescription,
    prescription_action,
):
    migrate_from = [("training", "0007_videoassemblyjob_qiniu_upload_deadline_at")]
    migrate_to = [("training", "0009_repair_qiniu_canonical_keys")]
    executor = MigrationExecutor(connection)
    executor.migrate(migrate_from)
    old_apps = executor.loader.project_state(migrate_from).apps
    TrainingVideo = old_apps.get_model("training", "TrainingVideo")
    VideoAssemblyJob = old_apps.get_model("training", "VideoAssemblyJob")

    training_date = timezone.localdate()
    common = {
        "prescription_id": active_prescription.id,
        "prescription_action_id": prescription_action.id,
        "training_date": training_date,
        "bucket": settings.QINIU_BUCKET,
        "content_type": "video/mp4",
        "size_bytes": 12,
        "duration_seconds": 60,
        "actual_duration_seconds": 60,
        "expected_segment_count": 2,
        "finalized_at": timezone.now(),
    }

    pending_session = uuid.UUID("10000000-0000-4000-8000-000000000001")
    pending = TrainingVideo.objects.create(
        project_patient_id=project_patient.id,
        client_session_id=pending_session,
        status="uploading_qiniu",
        **common,
    )
    pending_attempt = f"training-videos/attempts/{pending.id}-{pending_session}/attempt-2.mp4"
    pending_job = VideoAssemblyJob.objects.create(
        training_video_id=pending.id,
        status="running",
        attempt_count=2,
        qiniu_object_key=pending_attempt,
    )

    attached_session = uuid.UUID("20000000-0000-4000-8000-000000000002")
    attached_key = "legacy/attached-object.mp4"
    attached = TrainingVideo.objects.create(
        project_patient_id=project_patient.id,
        client_session_id=attached_session,
        status="attached",
        object_key=attached_key,
        **common,
    )
    attached_job = VideoAssemblyJob.objects.create(
        training_video_id=attached.id,
        status="succeeded",
        attempt_count=1,
        qiniu_object_key=attached_key,
    )

    cleanup_session = uuid.UUID("30000000-0000-4000-8000-000000000003")
    cleanup = TrainingVideo.objects.create(
        project_patient_id=None,
        client_session_id=cleanup_session,
        status="failed",
        cleanup_requested_at=timezone.now(),
        **common,
    )
    cleanup_attempt = f"training-videos/attempts/{cleanup.id}-{cleanup_session}/attempt-3.mp4"
    cleanup_job = VideoAssemblyJob.objects.create(
        training_video_id=cleanup.id,
        status="failed",
        attempt_count=3,
        qiniu_object_key=cleanup_attempt,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_to)
    new_apps = executor.loader.project_state(migrate_to).apps
    VideoAssemblyJob = new_apps.get_model("training", "VideoAssemblyJob")
    QiniuCleanupTombstone = new_apps.get_model("training", "QiniuCleanupTombstone")

    repaired_pending = VideoAssemblyJob.objects.get(pk=pending_job.pk)
    pending_canonical = (
        f"training-videos/{project_patient.id}/{training_date:%Y/%m/%d}/"
        f"{pending_session}.mp4"
    )
    assert repaired_pending.qiniu_attempt_object_key == pending_attempt
    assert repaired_pending.qiniu_object_key == pending_canonical
    pending_tombstone = QiniuCleanupTombstone.objects.get(
        attempt_key_prefix=f"training-videos/attempts/{pending.id}-{pending_session}/attempt-"
    )
    assert pending_tombstone.canonical_key == pending_canonical
    assert pending_tombstone.retain_canonical is True

    repaired_attached = VideoAssemblyJob.objects.get(pk=attached_job.pk)
    assert repaired_attached.qiniu_object_key == attached_key
    attached_tombstone = QiniuCleanupTombstone.objects.get(
        attempt_key_prefix=f"training-videos/attempts/{attached.id}-{attached_session}/attempt-"
    )
    assert attached_tombstone.canonical_key == attached_key
    assert attached_tombstone.retain_canonical is True

    repaired_cleanup = VideoAssemblyJob.objects.get(pk=cleanup_job.pk)
    cleanup_canonical = (
        f"training-videos/{project_patient.id}/{training_date:%Y/%m/%d}/"
        f"{cleanup_session}.mp4"
    )
    assert repaired_cleanup.qiniu_attempt_object_key == cleanup_attempt
    assert repaired_cleanup.qiniu_object_key == cleanup_canonical
    cleanup_tombstone = QiniuCleanupTombstone.objects.get(
        attempt_key_prefix=f"training-videos/attempts/{cleanup.id}-{cleanup_session}/attempt-"
    )
    assert cleanup_tombstone.canonical_key == cleanup_canonical
    assert cleanup_tombstone.retain_canonical is False
