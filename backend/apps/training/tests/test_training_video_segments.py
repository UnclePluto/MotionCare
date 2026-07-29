import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.training.models import (
    TrainingVideo,
    TrainingVideoSegment,
    VideoProcessingJob,
)


def _video(project_patient, active_prescription, prescription_action):
    return TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key=f"training-videos/{project_patient.id}/session.mp4",
        content_type="video/mp4",
        size_bytes=0,
        duration_seconds=0,
    )


@pytest.mark.django_db
def test_segment_sequence_is_unique_per_training_video(
    project_patient, active_prescription, prescription_action
):
    video = _video(project_patient, active_prescription, prescription_action)
    TrainingVideoSegment.objects.create(
        training_video=video,
        sequence_index=0,
        server_file_path=f"training-video-segments/{video.id}/0.mp4",
        content_type="video/mp4",
        size_bytes=12,
        duration_seconds=30,
        object_hash="hash-a",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        TrainingVideoSegment.objects.create(
            training_video=video,
            sequence_index=0,
            server_file_path=f"training-video-segments/{video.id}/duplicate.mp4",
            content_type="video/mp4",
            size_bytes=12,
            duration_seconds=30,
            object_hash="hash-b",
        )


@pytest.mark.django_db
def test_training_video_has_only_one_processing_job(
    project_patient, active_prescription, prescription_action
):
    video = _video(project_patient, active_prescription, prescription_action)
    VideoProcessingJob.objects.create(training_video=video)

    with pytest.raises(IntegrityError), transaction.atomic():
        VideoProcessingJob.objects.create(training_video=video)


@pytest.mark.django_db
def test_processing_job_defaults_to_48_hour_expiry(
    project_patient, active_prescription, prescription_action
):
    before = timezone.now()
    video = _video(project_patient, active_prescription, prescription_action)
    job = VideoProcessingJob.objects.create(training_video=video)

    assert job.status == VideoProcessingJob.Status.QUEUED
    assert timezone.timedelta(hours=47, minutes=59) <= job.expires_at - before
    assert job.expires_at - before <= timezone.timedelta(hours=48, minutes=1)
