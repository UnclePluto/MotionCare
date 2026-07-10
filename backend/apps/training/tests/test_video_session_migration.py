import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_segmented_video_migration_assigns_distinct_session_ids_to_history(
    project_patient, active_prescription, prescription_action
):
    executor = MigrationExecutor(connection)
    migrate_from = [("training", "0003_unique_active_motion_analysis_job")]
    migrate_to = [("training", "0004_segmented_training_video")]

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
        "upload_token_expires_at": "2026-07-11T00:00:00+00:00",
    }
    TrainingVideo.objects.create(object_key="legacy/first.mp4", **legacy_video_fields)
    TrainingVideo.objects.create(object_key="legacy/second.mp4", **legacy_video_fields)

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_to)
    new_apps = executor.loader.project_state(migrate_to).apps
    TrainingVideo = new_apps.get_model("training", "TrainingVideo")
    client_session_ids = list(
        TrainingVideo.objects.order_by("object_key").values_list("client_session_id", flat=True)
    )

    assert all(client_session_ids)
    assert len(set(client_session_ids)) == 2
