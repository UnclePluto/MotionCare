import uuid
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.prescriptions.models import ActionLibraryItem
from apps.training import tasks as training_tasks
from apps.training.models import (
    MotionAnalysisJob,
    TrainingRecord,
    TrainingVideo,
    VideoAssemblyJob,
)
from apps.training.motion_analysis_support import SHOULDER_PRESS_SOURCE_KEY
from apps.training.video_tasks import attach_training_video


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _shoulder_press_action(active_prescription):
    item = ActionLibraryItem.objects.get(source_key=SHOULDER_PRESS_SOURCE_KEY)
    return active_prescription.add_action_snapshot(
        item,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=2,
    )


def _video(
    project_patient,
    active_prescription,
    action,
    *,
    status=TrainingVideo.Status.ATTACHED,
):
    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=2,
    )
    return TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_record=record,
        bucket="motioncare-training",
        object_key=f"training-videos/{project_patient.id}/{uuid.uuid4().hex}.mp4",
        object_hash="hash-a",
        content_type="video/mp4",
        size_bytes=1024,
        duration_seconds=120,
        status=status,
        uploaded_at=timezone.now(),
    )


def _queued_video_job(project_patient, active_prescription, action):
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate(),
        actual_duration_seconds=120,
        status=TrainingVideo.Status.QUEUED,
    )
    object_key = f"training-videos/{project_patient.id}/{uuid.uuid4().hex}.mp4"
    job = VideoAssemblyJob.objects.create(
        training_video=video,
        status=VideoAssemblyJob.Status.RUNNING,
        qiniu_object_key=object_key,
    )
    return video, job


def _attach(video_job):
    result = SimpleNamespace(size_bytes=1024)
    return attach_training_video(
        video_job.id,
        result,
        {"hash": "hash-a", "fsize": result.size_bytes},
        lease_attempt=video_job.attempt_count,
        object_key=video_job.qiniu_object_key,
    )


def _other_doctor():
    return User.objects.create_user(
        phone="13800009999",
        password="pass123456",
        name="无权限医生",
        role=User.Role.DOCTOR,
    )


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_DOWNLOAD_DOMAIN="https://cdn.example.com",
)
def test_doctor_gets_short_private_url_only_for_attached_video(
    doctor,
    project_patient,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    attached = _video(project_patient, active_prescription, action)
    recording = _video(
        project_patient,
        active_prescription,
        action,
        status=TrainingVideo.Status.RECORDING,
    )

    response = _client(doctor).get(f"/api/training/videos/{attached.id}/download-url/")
    recording_response = _client(doctor).get(
        f"/api/training/videos/{recording.id}/download-url/"
    )

    assert response.status_code == 200, response.data
    assert response.data["url"].startswith(
        f"https://cdn.example.com/{attached.object_key}?e="
    )
    assert "token=ak-test:" in response.data["url"]
    assert recording_response.status_code == 400
    assert "绑定" in str(recording_response.data)


@pytest.mark.django_db
@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=True)
@pytest.mark.parametrize("suffix", ["download-url/", "analysis-jobs/latest/"])
def test_inaccessible_doctor_receives_404_for_remaining_video_endpoints(
    suffix,
    project_patient,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    video = _video(project_patient, active_prescription, action)

    response = _client(_other_doctor()).get(
        f"/api/training/videos/{video.id}/{suffix}"
    )

    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(
    TRAINING_HEALTH_ENFORCE_ROW_SCOPE=False,
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_DOWNLOAD_DOMAIN="https://cdn.example.com",
)
def test_doctor_can_access_other_doctors_remaining_video_endpoints_by_default(
    project_patient,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    video = _video(project_patient, active_prescription, action)
    other_doctor = _other_doctor()

    download = _client(other_doctor).get(
        f"/api/training/videos/{video.id}/download-url/"
    )
    latest = _client(other_doctor).get(
        f"/api/training/videos/{video.id}/analysis-jobs/latest/"
    )

    assert download.status_code == 200
    assert download.data["url"].startswith(
        f"https://cdn.example.com/{video.object_key}?e="
    )
    assert latest.status_code == 200
    assert latest.data is None


@pytest.mark.django_db
def test_doctor_cannot_create_or_recreate_analysis_job(
    doctor,
    project_patient,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    video = _video(project_patient, active_prescription, action)

    response = _client(doctor).post(
        f"/api/training/videos/{video.id}/analysis-jobs/"
    )

    assert response.status_code == 404
    assert MotionAnalysisJob.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    PP_MCARE_AUTO_ENQUEUE_ENABLED=True,
    QINIU_BUCKET="motioncare-training",
)
def test_attach_creates_analysis_job_synchronously_without_celery_inference(
    project_patient,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    video, video_job = _queued_video_job(
        project_patient,
        active_prescription,
        action,
    )

    with transaction.atomic():
        _attach(video_job)
        job_id = MotionAnalysisJob.objects.get(training_video=video).id

    job = MotionAnalysisJob.objects.get(pk=job_id)
    assert job.status == MotionAnalysisJob.Status.PENDING
    assert job.requested_by is None
    assert not hasattr(training_tasks, "run_motion_analysis_job")


@pytest.mark.django_db
@override_settings(
    PP_MCARE_AUTO_ENQUEUE_ENABLED=False,
    QINIU_BUCKET="motioncare-training",
)
def test_attach_does_not_create_analysis_job_when_auto_enqueue_is_disabled(
    project_patient,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    video, video_job = _queued_video_job(
        project_patient,
        active_prescription,
        action,
    )

    _attach(video_job)

    assert not MotionAnalysisJob.objects.filter(training_video=video).exists()


@pytest.mark.django_db
def test_database_constraint_prevents_concurrent_active_jobs(
    project_patient,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    video = _video(project_patient, active_prescription, action)
    MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=video.training_record,
        project_patient=project_patient,
        prescription_action=action,
        status=MotionAnalysisJob.Status.PENDING,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        MotionAnalysisJob.objects.create(
            training_video=video,
            training_record=video.training_record,
            project_patient=project_patient,
            prescription_action=action,
            status=MotionAnalysisJob.Status.RUNNING,
        )


@pytest.mark.django_db
def test_failed_job_cannot_be_retried_and_latest_endpoint_keeps_failed_job(
    doctor,
    project_patient,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    video = _video(project_patient, active_prescription, action)
    failed = MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=video.training_record,
        project_patient=project_patient,
        prescription_action=action,
        status=MotionAnalysisJob.Status.FAILED,
        failure_reason="旧任务失败",
        finished_at=timezone.now(),
    )

    create_response = _client(doctor).post(
        f"/api/training/videos/{video.id}/analysis-jobs/"
    )
    latest_response = _client(doctor).get(
        f"/api/training/videos/{video.id}/analysis-jobs/latest/"
    )

    assert create_response.status_code == 404
    assert MotionAnalysisJob.objects.filter(training_video=video).count() == 1
    assert latest_response.status_code == 200
    assert latest_response.data["id"] == failed.id
