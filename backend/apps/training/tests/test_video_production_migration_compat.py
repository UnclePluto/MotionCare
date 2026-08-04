import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_deployed_training_migrations_upgrade_without_recreating_video_tables(
    project_patient,
    active_prescription,
    prescription_action,
):
    migrate_from = [("training", "0004_trainingvideo_training_date")]
    migrate_to = [("training", "0012_repair_unbound_qiniu_canonical_keys")]

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_from)
    old_apps = executor.loader.project_state(migrate_from).apps
    MotionAnalysisJob = old_apps.get_model("training", "MotionAnalysisJob")
    TrainingVideo = old_apps.get_model("training", "TrainingVideo")
    TrainingVideoSegment = old_apps.get_model("training", "TrainingVideoSegment")
    VideoProcessingJob = old_apps.get_model("training", "VideoProcessingJob")

    common = {
        "project_patient_id": project_patient.id,
        "prescription_id": active_prescription.id,
        "prescription_action_id": prescription_action.id,
        "bucket": "motioncare-videos",
        "content_type": "video/mp4",
        "size_bytes": 1,
        "duration_seconds": 1,
    }
    attached = TrainingVideo.objects.create(
        object_key="legacy/attached.mp4",
        status="attached",
        training_date=timezone.localdate(),
        **common,
    )
    unfinished = TrainingVideo.objects.create(
        object_key="legacy/unfinished.mp4",
        status="uploading",
        training_date=None,
        **common,
    )
    first_analysis = MotionAnalysisJob.objects.create(
        training_video_id=attached.id,
        project_patient_id=project_patient.id,
        prescription_action_id=prescription_action.id,
        status="pending",
    )
    second_analysis = MotionAnalysisJob.objects.create(
        training_video_id=attached.id,
        project_patient_id=project_patient.id,
        prescription_action_id=prescription_action.id,
        status="running",
    )
    TrainingVideoSegment.objects.create(
        training_video_id=unfinished.id,
        sequence_index=0,
        server_file_path="/app/media/training-video-staging/legacy/000000.mp4",
        size_bytes=1,
        duration_seconds=1,
        object_hash="0" * 64,
    )
    VideoProcessingJob.objects.create(training_video_id=unfinished.id)

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_to)
    new_apps = executor.loader.project_state(migrate_to).apps
    LegacyTrainingVideoSegmentArchive = new_apps.get_model(
        "training",
        "LegacyTrainingVideoSegmentArchive",
    )
    MotionAnalysisJob = new_apps.get_model("training", "MotionAnalysisJob")
    QiniuCleanupTombstone = new_apps.get_model(
        "training",
        "QiniuCleanupTombstone",
    )
    TrainingVideo = new_apps.get_model("training", "TrainingVideo")
    TrainingVideoSegment = new_apps.get_model("training", "TrainingVideoSegment")
    VideoAssemblyJob = new_apps.get_model("training", "VideoAssemblyJob")

    upgraded_attached = TrainingVideo.objects.get(pk=attached.pk)
    upgraded_unfinished = TrainingVideo.objects.get(pk=unfinished.pk)
    assert upgraded_attached.status == "attached"
    assert upgraded_attached.object_key == "legacy/attached.mp4"
    assert upgraded_attached.client_session_id is not None
    assert upgraded_unfinished.status == "failed"
    assert upgraded_unfinished.training_date is not None
    assert upgraded_unfinished.client_session_id is not None
    assert upgraded_unfinished.client_session_id != upgraded_attached.client_session_id
    active_analysis_ids = list(
        MotionAnalysisJob.objects.filter(
            training_video_id=attached.id,
            status__in=["pending", "running"],
        ).values_list("id", flat=True)
    )
    assert active_analysis_ids == [second_analysis.id]
    assert MotionAnalysisJob.objects.get(pk=first_analysis.id).status == "failed"
    assert not TrainingVideoSegment.objects.exists()
    assert not VideoAssemblyJob.objects.exists()
    archived_segment = LegacyTrainingVideoSegmentArchive.objects.get(
        source_training_video_id=unfinished.id,
    )
    assert (
        archived_segment.server_file_path
        == "/app/media/training-video-staging/legacy/000000.mp4"
    )

    attached_tombstone = QiniuCleanupTombstone.objects.get(
        session_id=upgraded_attached.client_session_id,
    )
    assert attached_tombstone.canonical_key == "legacy/attached.mp4"
    assert attached_tombstone.retain_canonical is True


@pytest.mark.django_db(transaction=True)
def test_schema_retirement_backfills_sessions_created_after_initial_uuid_pass(
    project_patient,
    active_prescription,
    prescription_action,
):
    migrate_from = [("training", "0007_populate_training_client_session_ids")]
    migrate_to = [("training", "0009_current_training_pipeline")]

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_from)
    old_apps = executor.loader.project_state(migrate_from).apps
    TrainingVideo = old_apps.get_model("training", "TrainingVideo")
    late_video = TrainingVideo.objects.create(
        project_patient_id=project_patient.id,
        prescription_id=active_prescription.id,
        prescription_action_id=prescription_action.id,
        bucket="motioncare-videos",
        object_key="legacy/late-session.mp4",
        content_type="video/mp4",
        size_bytes=1,
        duration_seconds=1,
        status="uploading",
        training_date=timezone.localdate(),
        client_session_id=None,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_to)
    new_apps = executor.loader.project_state(migrate_to).apps
    TrainingVideo = new_apps.get_model("training", "TrainingVideo")

    upgraded = TrainingVideo.objects.get(pk=late_video.pk)
    assert upgraded.client_session_id is not None
