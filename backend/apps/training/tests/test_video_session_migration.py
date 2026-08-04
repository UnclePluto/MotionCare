import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_legacy_pipeline_retirement_assigns_distinct_session_ids_to_history(
    project_patient, active_prescription, prescription_action
):
    executor = MigrationExecutor(connection)
    migrate_from = [("training", "0004_trainingvideo_training_date")]
    migrate_to = [("training", "0009_current_training_pipeline")]

    executor.migrate(migrate_from)
    old_apps = executor.loader.project_state(migrate_from).apps
    TrainingVideo = old_apps.get_model("training", "TrainingVideo")
    legacy_video_fields = {
        "project_patient_id": project_patient.id,
        "prescription_id": active_prescription.id,
        "prescription_action_id": prescription_action.id,
        "bucket": "motioncare-videos",
        "content_type": "video/mp4",
        "size_bytes": 1,
        "duration_seconds": 1,
        "training_date": timezone.localdate(),
    }
    TrainingVideo.objects.create(
        object_key="legacy/first.mp4",
        status="attached",
        **legacy_video_fields,
    )
    TrainingVideo.objects.create(
        object_key="legacy/second.mp4",
        status="attached",
        **legacy_video_fields,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_to)
    new_apps = executor.loader.project_state(migrate_to).apps
    TrainingVideo = new_apps.get_model("training", "TrainingVideo")
    client_session_ids = list(
        TrainingVideo.objects.order_by("object_key").values_list("client_session_id", flat=True)
    )

    assert all(client_session_ids)
    assert len(set(client_session_ids)) == 2


@pytest.mark.django_db(transaction=True)
def test_legacy_pipeline_retirement_fails_incomplete_sessions_and_keeps_attached(
    project_patient, active_prescription, prescription_action
):
    executor = MigrationExecutor(connection)
    migrate_from = [("training", "0004_trainingvideo_training_date")]
    migrate_to = [("training", "0009_current_training_pipeline")]

    executor.migrate(migrate_from)
    old_apps = executor.loader.project_state(migrate_from).apps
    TrainingVideo = old_apps.get_model("training", "TrainingVideo")
    common = {
        "project_patient_id": project_patient.id,
        "prescription_id": active_prescription.id,
        "prescription_action_id": prescription_action.id,
        "bucket": "motioncare-videos",
        "content_type": "video/mp4",
        "size_bytes": 1,
        "duration_seconds": 1,
        "training_date": timezone.localdate(),
    }
    uploading = TrainingVideo.objects.create(
        object_key="legacy/uploading.mp4", status="uploading", **common
    )
    processing = TrainingVideo.objects.create(
        object_key="legacy/processing.mp4", status="merging", **common
    )
    attached = TrainingVideo.objects.create(
        object_key="legacy/attached.mp4", status="attached", **common
    )

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_to)
    new_apps = executor.loader.project_state(migrate_to).apps
    TrainingVideo = new_apps.get_model("training", "TrainingVideo")

    expected_reason = "旧版视频处理会话已停止，请重新训练"
    assert TrainingVideo.objects.get(pk=uploading.pk).status == "failed"
    assert TrainingVideo.objects.get(pk=uploading.pk).failure_reason == expected_reason
    assert TrainingVideo.objects.get(pk=processing.pk).status == "failed"
    assert TrainingVideo.objects.get(pk=processing.pk).failure_reason == expected_reason
    assert TrainingVideo.objects.get(pk=attached.pk).status == "attached"
