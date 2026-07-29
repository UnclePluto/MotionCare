import pytest
from rest_framework.test import APIClient
from unittest.mock import Mock

from apps.prescriptions.models import Prescription
from apps.studies.models import ProjectPatient
from apps.training.models import TrainingVideo, VideoAssemblyJob


@pytest.mark.django_db
def test_unbind_terminates_prescriptions_and_removes_link(doctor, project_patient, active_prescription):
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/project-patients/{project_patient.id}/unbind/")
    assert r.status_code == 200
    active_prescription.refresh_from_db()
    assert active_prescription.status == Prescription.Status.TERMINATED
    assert active_prescription.archived_at is not None
    assert active_prescription.project_patient_id is None
    assert not ProjectPatient.objects.filter(pk=project_patient.pk).exists()


@pytest.mark.django_db
def test_unbind_keeps_training_video_as_durable_cleanup_record_and_enqueues_after_commit(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        status=TrainingVideo.Status.UPLOADING_QINIU,
    )
    VideoAssemblyJob.objects.create(
        training_video=video,
        qiniu_object_key="training-videos/pending-final.mp4",
    )
    from apps.training import video_tasks

    delay = Mock()
    monkeypatch.setattr(video_tasks.cleanup_unbound_training_video, "delay", delay)
    client = APIClient()
    client.force_authenticate(user=doctor)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            f"/api/studies/project-patients/{project_patient.id}/unbind/"
        )

    assert response.status_code == 200
    video.refresh_from_db()
    assert video.project_patient_id is None
    assert video.cleanup_status == TrainingVideo.CleanupStatus.PENDING
    assert video.cleanup_requested_at is not None
    delay.assert_called_once_with(video.id)
