import importlib
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
    migrate_from = [("training", "0009_current_training_pipeline")]
    migrate_to = [("training", "0012_repair_unbound_qiniu_canonical_keys")]
    executor = MigrationExecutor(connection)
    executor.migrate(migrate_from)
    old_apps = executor.loader.project_state(migrate_from).apps
    TrainingVideo = old_apps.get_model("training", "TrainingVideo")
    VideoAssemblyJob = old_apps.get_model("training", "VideoAssemblyJob")
    Prescription = old_apps.get_model("prescriptions", "Prescription")

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
    unbound_prescription = Prescription.objects.create(
        project_patient_id=None,
        version=active_prescription.version,
        opened_by_id=active_prescription.opened_by_id,
        status="terminated",
    )
    unbound_common = {**common, "prescription_id": unbound_prescription.id}

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
        **unbound_common,
    )
    cleanup_attempt = f"training-videos/attempts/{cleanup.id}-{cleanup_session}/attempt-3.mp4"
    cleanup_job = VideoAssemblyJob.objects.create(
        training_video_id=cleanup.id,
        status="failed",
        attempt_count=3,
        qiniu_object_key=cleanup_attempt,
    )

    attached_cleanup_session = uuid.UUID("40000000-0000-4000-8000-000000000004")
    attached_cleanup_key = "legacy/attached-cleanup-object.mp4"
    attached_cleanup = TrainingVideo.objects.create(
        project_patient_id=None,
        client_session_id=attached_cleanup_session,
        status="attached",
        object_key=attached_cleanup_key,
        cleanup_requested_at=timezone.now(),
        **unbound_common,
    )
    attached_cleanup_job = VideoAssemblyJob.objects.create(
        training_video_id=attached_cleanup.id,
        status="succeeded",
        attempt_count=2,
        qiniu_object_key=attached_cleanup_key,
    )

    detached_canonical_session = uuid.UUID("50000000-0000-4000-8000-000000000005")
    detached_canonical_key = "legacy/unbound-job-object.mp4"
    detached_canonical = TrainingVideo.objects.create(
        project_patient_id=None,
        client_session_id=detached_canonical_session,
        status="failed",
        cleanup_requested_at=timezone.now(),
        **unbound_common,
    )
    detached_canonical_job = VideoAssemblyJob.objects.create(
        training_video_id=detached_canonical.id,
        status="failed",
        attempt_count=4,
        qiniu_object_key=detached_canonical_key,
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
    assert repaired_cleanup.qiniu_attempt_object_key == cleanup_attempt
    assert repaired_cleanup.qiniu_object_key == ""
    cleanup_tombstone = QiniuCleanupTombstone.objects.get(
        attempt_key_prefix=f"training-videos/attempts/{cleanup.id}-{cleanup_session}/attempt-"
    )
    assert cleanup_tombstone.canonical_key == ""
    assert cleanup_tombstone.retain_canonical is False
    assert cleanup_tombstone.max_attempt_number == 3

    repaired_attached_cleanup = VideoAssemblyJob.objects.get(pk=attached_cleanup_job.pk)
    assert repaired_attached_cleanup.qiniu_object_key == attached_cleanup_key
    attached_cleanup_tombstone = QiniuCleanupTombstone.objects.get(
        attempt_key_prefix=(
            f"training-videos/attempts/{attached_cleanup.id}-{attached_cleanup_session}/attempt-"
        )
    )
    assert attached_cleanup_tombstone.canonical_key == attached_cleanup_key
    assert attached_cleanup_tombstone.retain_canonical is False

    repaired_detached_canonical = VideoAssemblyJob.objects.get(
        pk=detached_canonical_job.pk
    )
    assert repaired_detached_canonical.qiniu_object_key == detached_canonical_key
    detached_canonical_tombstone = QiniuCleanupTombstone.objects.get(
        attempt_key_prefix=(
            "training-videos/attempts/"
            f"{detached_canonical.id}-{detached_canonical_session}/attempt-"
        )
    )
    assert detached_canonical_tombstone.canonical_key == detached_canonical_key
    assert detached_canonical_tombstone.retain_canonical is False

    assert not VideoAssemblyJob.objects.filter(
        qiniu_object_key__startswith="training-videos/None/"
    ).exists()
    assert not QiniuCleanupTombstone.objects.filter(
        canonical_key__startswith="training-videos/None/"
    ).exists()

    job_state = list(
        VideoAssemblyJob.objects.order_by("id").values_list(
            "id",
            "qiniu_object_key",
            "qiniu_attempt_object_key",
        )
    )
    tombstone_state = list(
        QiniuCleanupTombstone.objects.order_by("id").values_list(
            "id",
            "canonical_key",
            "retain_canonical",
            "max_attempt_number",
            "updated_at",
        )
    )
    migration = importlib.import_module(
        "apps.training.migrations.0012_repair_unbound_qiniu_canonical_keys"
    )
    migration.repair_unbound_qiniu_canonical_keys(new_apps, None)
    assert list(
        VideoAssemblyJob.objects.order_by("id").values_list(
            "id",
            "qiniu_object_key",
            "qiniu_attempt_object_key",
        )
    ) == job_state
    assert list(
        QiniuCleanupTombstone.objects.order_by("id").values_list(
            "id",
            "canonical_key",
            "retain_canonical",
            "max_attempt_number",
            "updated_at",
        )
    ) == tombstone_state
