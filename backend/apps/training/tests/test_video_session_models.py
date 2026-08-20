import uuid
from datetime import UTC, datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.training.models import TrainingVideo, TrainingVideoSegment, VideoAssemblyJob
from apps.prescriptions.models import ActionLibraryItem
from apps.training.video_services import create_training_video_session


@pytest.mark.django_db
def test_segmented_training_video_models(
    project_patient, active_prescription, prescription_action
):
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        expected_duration_seconds=180,
    )
    first = TrainingVideoSegment.objects.create(
        training_video=video,
        index=0,
        duration_ms=30000,
        size_bytes=1024,
        sha256="a" * 64,
        relative_path=f"{video.client_session_id.hex}/segments/000000.mp4",
        status=TrainingVideoSegment.Status.UPLOADED,
    )
    job = VideoAssemblyJob.objects.create(training_video=video)

    assert video.status == TrainingVideo.Status.RECORDING
    assert first.index == 0
    assert job.status == VideoAssemblyJob.Status.PENDING
    assert job.cleanup_status == VideoAssemblyJob.CleanupStatus.PENDING
    assert video.cleanup_status == TrainingVideo.CleanupStatus.NONE
    assert video.cleanup_requested_at is None

    with pytest.raises(IntegrityError), transaction.atomic():
        TrainingVideoSegment.objects.create(
            training_video=video,
            index=0,
            duration_ms=1000,
            size_bytes=1,
            sha256="b" * 64,
            relative_path=f"{video.client_session_id.hex}/segments/duplicate.mp4",
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        TrainingVideo.objects.create(
            client_session_id=video.client_session_id,
            project_patient=project_patient,
            prescription=active_prescription,
            prescription_action=prescription_action,
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        VideoAssemblyJob.objects.create(training_video=video)

    project_patient.delete()
    video.refresh_from_db()
    assert video.project_patient_id is None


@pytest.mark.django_db
def test_training_video_session_accepts_1800_seconds_and_rejects_1801(
    project_patient,
    active_prescription,
    monkeypatch,
    settings,
):
    action = active_prescription.add_action_snapshot(
        ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press"),
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=30,
    )
    monkeypatch.setattr(
        "apps.training.video_services._ensure_staging_available",
        lambda: None,
    )
    settings.TRAINING_VIDEO_MAX_DURATION_SECONDS = 2_400

    accepted, created = create_training_video_session(
        project_patient=project_patient,
        client_session_id=uuid.uuid4(),
        prescription_action_id=action.id,
        training_date=timezone.localdate(),
        expected_duration_seconds=1800,
        training_started_at=datetime(2026, 7, 11, 1, 32, 14, tzinfo=UTC),
    )

    assert created is True
    assert accepted.expected_duration_seconds == 1800
    with pytest.raises(ValidationError, match="时长超过限制"):
        create_training_video_session(
            project_patient=project_patient,
            client_session_id=uuid.uuid4(),
            prescription_action_id=action.id,
            training_date=timezone.localdate(),
            expected_duration_seconds=1801,
            training_started_at=datetime(2026, 7, 11, 1, 32, 14, tzinfo=UTC),
        )


@pytest.mark.django_db
def test_existing_legacy_2400_second_session_remains_idempotently_addressable(
    project_patient,
    active_prescription,
):
    action = active_prescription.add_action_snapshot(
        ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press"),
        duration_minutes=30,
    )
    client_session_id = uuid.uuid4()
    started_at = datetime(2026, 7, 11, 1, 32, 14, tzinfo=UTC)
    existing = TrainingVideo.objects.create(
        client_session_id=client_session_id,
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=started_at.date(),
        expected_duration_seconds=2_400,
        training_started_at=started_at,
    )

    returned, created = create_training_video_session(
        project_patient=project_patient,
        client_session_id=client_session_id,
        prescription_action_id=action.id,
        training_date=started_at.date(),
        expected_duration_seconds=2_400,
        training_started_at=started_at,
    )

    assert created is False
    assert returned.id == existing.id
