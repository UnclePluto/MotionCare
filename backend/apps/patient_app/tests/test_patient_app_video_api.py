import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient
from types import SimpleNamespace
from unittest.mock import patch

from apps.patient_app.services import bind_project_patient_with_code, create_binding_code
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem
from apps.studies.models import ProjectPatient
from apps.training.models import (
    TrainingRecord,
    TrainingVideo,
    TrainingVideoSegment,
    VideoProcessingJob,
)


def _client(project_patient, doctor, *, openid="video-openid"):
    code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    token, _ = bind_project_patient_with_code(code, wx_openid=openid)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _shoulder_action(active_prescription):
    item, _ = ActionLibraryItem.objects.get_or_create(
        source_key="motion-resistance-shoulder-press",
        defaults={
            "name": "肩部推举",
            "training_type": "运动训练",
            "internal_type": ActionLibraryItem.InternalType.MOTION,
            "action_type": "抗阻训练",
        },
    )
    return active_prescription.add_action_snapshot(item, weekly_target_count=2)


def _create_session(client, action_id):
    return client.post(
        "/api/patient-app/training-video-sessions/",
        {"prescription_action": action_id},
        format="json",
    )


def _upload_segment(client, video_id, content=b"segment-a", sequence_index=0):
    return client.post(
        f"/api/patient-app/training-video-sessions/{video_id}/segments/",
        {
            "sequence_index": sequence_index,
            "duration_seconds": 30,
            "file": SimpleUploadedFile(
                f"segment-{sequence_index}.mp4", content, "video/mp4"
            ),
        },
        format="multipart",
    )


def _finish_session(client, video_id, *, segment_count, duration_seconds=70):
    return client.post(
        f"/api/patient-app/training-video-sessions/{video_id}/finish/",
        {
            "segment_count": segment_count,
            "duration_seconds": duration_seconds,
            "training_date": str(timezone.localdate()),
        },
        format="json",
    )


@pytest.mark.django_db
def test_patient_creates_segmented_training_video_session(
    project_patient, doctor, active_prescription
):
    action = _shoulder_action(active_prescription)
    client = _client(project_patient, doctor)

    response = _create_session(client, action.id)

    assert response.status_code == 201, response.data
    assert response.data == {
        "video_id": response.data["video_id"],
        "status": "recording",
        "uploaded_segment_count": 0,
    }
    video = TrainingVideo.objects.get(pk=response.data["video_id"])
    assert video.project_patient == project_patient
    assert video.prescription_action == action


@pytest.mark.django_db
def test_segment_upload_is_idempotent_for_same_sequence_and_content(
    project_patient, doctor, active_prescription, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    action = _shoulder_action(active_prescription)
    client = _client(project_patient, doctor)
    video_id = _create_session(client, action.id).data["video_id"]

    first = _upload_segment(client, video_id)
    second = _upload_segment(client, video_id)

    assert first.status_code == 201, first.data
    assert second.status_code == 200, second.data
    assert first.data["object_hash"] == second.data["object_hash"]
    assert TrainingVideoSegment.objects.filter(training_video_id=video_id).count() == 1
    video = TrainingVideo.objects.get(pk=video_id)
    assert video.uploaded_segment_count == 1


@pytest.mark.django_db
def test_segment_upload_rejects_same_sequence_with_different_content(
    project_patient, doctor, active_prescription, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    action = _shoulder_action(active_prescription)
    client = _client(project_patient, doctor)
    video_id = _create_session(client, action.id).data["video_id"]
    assert _upload_segment(client, video_id, b"segment-a").status_code == 201

    conflict = _upload_segment(client, video_id, b"segment-b")

    assert conflict.status_code == 409, conflict.data
    assert TrainingVideoSegment.objects.filter(training_video_id=video_id).count() == 1


@pytest.mark.django_db
def test_segment_upload_rejects_when_server_disk_reserve_would_be_exhausted(
    project_patient, doctor, active_prescription, settings, tmp_path
):
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    settings.TRAINING_VIDEO_SERVER_MIN_FREE_BYTES = 1_024
    action = _shoulder_action(active_prescription)
    client = _client(project_patient, doctor)
    video_id = _create_session(client, action.id).data["video_id"]

    with patch(
        "apps.training.video_services.shutil.disk_usage",
        return_value=SimpleNamespace(free=1_030),
    ):
        response = _upload_segment(client, video_id, content=b"segment-over-reserve")

    assert response.status_code == 400, response.data
    assert "存储空间不足" in response.data["detail"]
    assert not TrainingVideoSegment.objects.filter(training_video_id=video_id).exists()


@pytest.mark.django_db
def test_patient_cannot_read_another_patients_video_session(
    project_patient, doctor, active_prescription, group
):
    action = _shoulder_action(active_prescription)
    owner_client = _client(project_patient, doctor)
    video_id = _create_session(owner_client, action.id).data["video_id"]
    other_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )
    other_project_patient = ProjectPatient.objects.create(
        project=project_patient.project,
        patient=other_patient,
        group=group,
    )
    other_client = _client(other_project_patient, doctor, openid="video-openid-other")

    response = other_client.get(
        f"/api/patient-app/training-video-sessions/{video_id}/"
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_patient_cannot_write_another_patients_segment_to_disk(
    project_patient, doctor, active_prescription, group, settings, tmp_path
):
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    action = _shoulder_action(active_prescription)
    owner_client = _client(project_patient, doctor)
    video_id = _create_session(owner_client, action.id).data["video_id"]
    other_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900002223",
        primary_doctor=doctor,
    )
    other_project_patient = ProjectPatient.objects.create(
        project=project_patient.project,
        patient=other_patient,
        group=group,
    )
    other_client = _client(other_project_patient, doctor, openid="video-upload-other")

    response = _upload_segment(other_client, video_id)

    assert response.status_code == 404
    assert not (settings.TRAINING_VIDEO_TEMP_ROOT / str(video_id)).exists()


@pytest.mark.django_db
def test_session_status_does_not_expose_server_path_or_qiniu_credentials(
    project_patient, doctor, active_prescription, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    action = _shoulder_action(active_prescription)
    client = _client(project_patient, doctor)
    video_id = _create_session(client, action.id).data["video_id"]
    assert _upload_segment(client, video_id).status_code == 201

    response = client.get(f"/api/patient-app/training-video-sessions/{video_id}/")

    assert response.status_code == 200, response.data
    assert response.data["uploaded_segment_count"] == 1
    serialized = str(response.data).lower()
    assert "server_file_path" not in serialized
    assert "upload_token" not in serialized
    assert "qiniu_access_key" not in serialized


@pytest.mark.django_db
def test_finish_rejects_missing_segments_and_returns_indexes(
    project_patient, doctor, active_prescription, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    action = _shoulder_action(active_prescription)
    client = _client(project_patient, doctor)
    video_id = _create_session(client, action.id).data["video_id"]
    assert _upload_segment(client, video_id, sequence_index=0).status_code == 201
    assert _upload_segment(client, video_id, b"segment-c", sequence_index=2).status_code == 201

    response = _finish_session(client, video_id, segment_count=3)

    assert response.status_code == 409, response.data
    assert response.data["missing_segments"] == [1]
    assert not VideoProcessingJob.objects.filter(training_video_id=video_id).exists()


@pytest.mark.django_db
def test_finish_bounds_missing_indexes_for_extreme_segment_count(
    project_patient, doctor, active_prescription, settings, tmp_path
):
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    action = _shoulder_action(active_prescription)
    client = _client(project_patient, doctor)
    video_id = _create_session(client, action.id).data["video_id"]
    assert _upload_segment(client, video_id, sequence_index=0).status_code == 201

    response = _finish_session(client, video_id, segment_count=10_000)

    assert response.status_code == 409, response.data
    assert len(response.data["missing_segments"]) <= 100
    assert response.data["missing_segments_truncated"] is True


@pytest.mark.django_db
def test_finish_creates_one_job_and_enqueues_after_commit(
    project_patient,
    doctor,
    active_prescription,
    settings,
    tmp_path,
    django_capture_on_commit_callbacks,
):
    settings.MEDIA_ROOT = tmp_path
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    action = _shoulder_action(active_prescription)
    client = _client(project_patient, doctor)
    video_id = _create_session(client, action.id).data["video_id"]
    assert _upload_segment(client, video_id, sequence_index=0).status_code == 201
    assert _upload_segment(client, video_id, b"segment-b", sequence_index=1).status_code == 201

    with patch("apps.training.tasks.process_training_video_job.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            first = _finish_session(client, video_id, segment_count=2, duration_seconds=60)
        with django_capture_on_commit_callbacks(execute=True):
            second = _finish_session(client, video_id, segment_count=2, duration_seconds=60)

    assert first.status_code == 202, first.data
    assert second.status_code == 200, second.data
    assert first.data["processing_job_id"] == second.data["processing_job_id"]
    assert VideoProcessingJob.objects.filter(training_video_id=video_id).count() == 1
    delay.assert_called_once_with(first.data["processing_job_id"])
    assert not TrainingRecord.objects.filter(project_patient=project_patient).exists()


@pytest.mark.django_db
def test_finish_prevents_later_segment_uploads(
    project_patient,
    doctor,
    active_prescription,
    settings,
    tmp_path,
    django_capture_on_commit_callbacks,
):
    settings.MEDIA_ROOT = tmp_path
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    action = _shoulder_action(active_prescription)
    client = _client(project_patient, doctor)
    video_id = _create_session(client, action.id).data["video_id"]
    assert _upload_segment(client, video_id, sequence_index=0).status_code == 201
    with patch("apps.training.tasks.process_training_video_job.delay"):
        with django_capture_on_commit_callbacks(execute=True):
            assert _finish_session(client, video_id, segment_count=1).status_code == 202

    late = _upload_segment(client, video_id, b"late-segment", sequence_index=1)

    assert late.status_code == 400, late.data


@pytest.mark.django_db
def test_finish_survives_celery_enqueue_failure_and_schedules_retry(
    project_patient,
    doctor,
    active_prescription,
    settings,
    tmp_path,
    django_capture_on_commit_callbacks,
):
    settings.MEDIA_ROOT = tmp_path
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    action = _shoulder_action(active_prescription)
    client = _client(project_patient, doctor)
    video_id = _create_session(client, action.id).data["video_id"]
    assert _upload_segment(client, video_id, sequence_index=0).status_code == 201

    with patch(
        "apps.training.tasks.process_training_video_job.delay",
        side_effect=RuntimeError("redis unavailable"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = _finish_session(client, video_id, segment_count=1)

    assert response.status_code == 202, response.data
    job = VideoProcessingJob.objects.get(training_video_id=video_id)
    assert job.status == VideoProcessingJob.Status.FAILED
    assert job.next_retry_at is not None
