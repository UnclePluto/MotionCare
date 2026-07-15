import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.training.models import MotionAnalysisJob, TrainingRecord, TrainingVideo


def _attached_video(project_patient, active_prescription, prescription_action):
    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
    )
    return TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_record=record,
        bucket="motioncare",
        object_key="training/a.mp4",
        object_hash="final-hash",
        content_type="video/mp4",
        size_bytes=10,
        duration_seconds=3,
        status=TrainingVideo.Status.ATTACHED,
    )


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_DOWNLOAD_DOMAIN="https://cdn.example.com",
)
def test_doctor_can_get_video_url_and_create_analysis(
    doctor, project_patient, active_prescription, prescription_action
):
    video = _attached_video(project_patient, active_prescription, prescription_action)
    client = APIClient()
    client.force_authenticate(doctor)
    download = client.get(f"/api/training/videos/{video.id}/download-url/")
    analysis = client.post(f"/api/training/videos/{video.id}/analysis-jobs/")

    assert download.status_code == 200
    assert download.data["url"].startswith("https://cdn.example.com/training/a.mp4?e=")
    assert analysis.status_code == 201
    assert MotionAnalysisJob.objects.filter(training_video=video).count() == 1


@pytest.mark.django_db
def test_doctor_cannot_download_or_analyze_processing_video(
    doctor, project_patient, active_prescription, prescription_action
):
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key="training/processing.mp4",
        status=TrainingVideo.Status.MERGING,
    )
    client = APIClient()
    client.force_authenticate(doctor)

    download = client.get(f"/api/training/videos/{video.id}/download-url/")
    analysis = client.post(f"/api/training/videos/{video.id}/analysis-jobs/")

    assert download.status_code == 400
    assert analysis.status_code == 400
