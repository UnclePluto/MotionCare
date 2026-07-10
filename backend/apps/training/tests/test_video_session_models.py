import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.training.models import TrainingVideo, TrainingVideoSegment, VideoAssemblyJob


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

    assert video.status == TrainingVideo.Status.UPLOADING
    assert first.index == 0
    assert job.status == VideoAssemblyJob.Status.PENDING
    assert job.cleanup_status == VideoAssemblyJob.CleanupStatus.PENDING

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
