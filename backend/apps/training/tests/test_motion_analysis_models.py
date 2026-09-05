import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from motion_analysis_contract import MotionCounts

from apps.training.models import MotionAnalysisJob, TrainingRecord, TrainingVideo


@pytest.fixture
def training_record(project_patient, active_prescription, prescription_action):
    return TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
    )


def test_training_record_rejects_inconsistent_motion_counts(training_record):
    TrainingRecord._meta.get_field("motion_total_count")
    training_record.motion_total_count = 5
    training_record.motion_standard_count = 2
    training_record.motion_nonstandard_count = 2

    with pytest.raises(ValidationError):
        training_record.full_clean()


def test_set_motion_result_records_doctor_provenance(training_record, doctor):
    recorded_at = timezone.now()

    training_record.set_motion_result(
        MotionCounts(5, 4, 1),
        {"doctor_note": "已复核"},
        "doctor",
        doctor,
        recorded_at,
    )

    assert training_record.motion_total_count == 5
    assert training_record.motion_standard_count == 4
    assert training_record.motion_nonstandard_count == 1
    assert training_record.motion_quality_data == {"doctor_note": "已复核"}
    assert training_record.motion_result_source == "doctor"
    assert training_record.motion_result_updated_by == doctor
    assert training_record.motion_result_updated_at == recorded_at


def test_motion_analysis_job_persists_control_plane_and_skeleton_metadata(
    project_patient,
    active_prescription,
    prescription_action,
):
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
    )
    lease_expires_at = timezone.now() + timezone.timedelta(minutes=5)
    heartbeat_at = timezone.now()
    job = MotionAnalysisJob.objects.create(
        training_video=video,
        project_patient=project_patient,
        prescription_action=prescription_action,
        worker_id="worker-1",
        lease_token_hash="a" * 64,
        lease_expires_at=lease_expires_at,
        last_heartbeat_at=heartbeat_at,
        action_source_key="shoulder-press",
        parameter_version="params-v1",
        subject_tracker_version="tracker-v1",
        completion_idempotency_key="completion-1",
        failure_code="worker_unavailable",
        skeleton_bucket="motion-skeletons",
        skeleton_object_key="skeletons/job-1.json",
        skeleton_object_hash="b" * 64,
        skeleton_size_bytes=512,
        skeleton_duration_seconds=42.5,
        skeleton_width=1920,
        skeleton_height=1080,
        skeleton_fps=30.0,
    )

    persisted = MotionAnalysisJob.objects.get(pk=job.pk)
    assert persisted.worker_id == "worker-1"
    assert persisted.lease_token_hash == "a" * 64
    assert persisted.lease_expires_at == lease_expires_at
    assert persisted.last_heartbeat_at == heartbeat_at
    assert persisted.action_source_key == "shoulder-press"
    assert persisted.parameter_version == "params-v1"
    assert persisted.subject_tracker_version == "tracker-v1"
    assert persisted.completion_idempotency_key == "completion-1"
    assert persisted.failure_code == "worker_unavailable"
    assert persisted.skeleton_bucket == "motion-skeletons"
    assert persisted.skeleton_object_key == "skeletons/job-1.json"
    assert persisted.skeleton_object_hash == "b" * 64
    assert persisted.skeleton_size_bytes == 512
    assert persisted.skeleton_duration_seconds == 42.5
    assert persisted.skeleton_width == 1920
    assert persisted.skeleton_height == 1080
    assert persisted.skeleton_fps == 30.0


@pytest.mark.django_db(transaction=True)
def test_control_plane_migration_fails_existing_active_analysis_jobs(
    project_patient,
    active_prescription,
    prescription_action,
):
    migrate_from = [("training", "0013_trainingvideo_training_window")]
    migrate_to = [("training", "0014_pp_mcare_control_plane")]

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_from)
    old_apps = executor.loader.project_state(migrate_from).apps
    TrainingVideo = old_apps.get_model("training", "TrainingVideo")
    MotionAnalysisJob = old_apps.get_model("training", "MotionAnalysisJob")
    pending_video = TrainingVideo.objects.create(
        project_patient_id=project_patient.id,
        prescription_id=active_prescription.id,
        prescription_action_id=prescription_action.id,
    )
    running_video = TrainingVideo.objects.create(
        project_patient_id=project_patient.id,
        prescription_id=active_prescription.id,
        prescription_action_id=prescription_action.id,
    )
    pending_job = MotionAnalysisJob.objects.create(
        training_video_id=pending_video.id,
        project_patient_id=project_patient.id,
        prescription_action_id=prescription_action.id,
        status="pending",
    )
    running_job = MotionAnalysisJob.objects.create(
        training_video_id=running_video.id,
        project_patient_id=project_patient.id,
        prescription_action_id=prescription_action.id,
        status="running",
    )

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_to)
    new_apps = executor.loader.project_state(migrate_to).apps
    MotionAnalysisJob = new_apps.get_model("training", "MotionAnalysisJob")

    assert MotionAnalysisJob.objects.get(pk=pending_job.id).status == "failed"
    assert MotionAnalysisJob.objects.get(pk=running_job.id).status == "failed"
    assert MotionAnalysisJob.objects.get(pk=pending_job.id).failure_code == "service_migration"
    assert MotionAnalysisJob.objects.get(pk=running_job.id).failure_code == "service_migration"
