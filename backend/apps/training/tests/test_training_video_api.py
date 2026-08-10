import uuid
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.prescriptions.models import ActionLibraryItem
from apps.training.models import MotionAnalysisJob, TrainingRecord, TrainingVideo
from apps.training.video_services import SHOULDER_PRESS_SOURCE_KEY, create_analysis_job


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


def _video(project_patient, active_prescription, action, *, status=TrainingVideo.Status.ATTACHED):
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
@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", "download-url/"),
        ("post", "analysis-jobs/"),
        ("get", "analysis-jobs/latest/"),
    ],
)
def test_inaccessible_doctor_receives_404_for_all_video_endpoints(
    method,
    suffix,
    project_patient,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    video = _video(project_patient, active_prescription, action)
    path = f"/api/training/videos/{video.id}/{suffix}"

    assert resolve(path).func.view_class.permission_classes
    response = getattr(_client(_other_doctor()), method)(path)

    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(
    TRAINING_HEALTH_ENFORCE_ROW_SCOPE=False,
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_DOWNLOAD_DOMAIN="https://cdn.example.com",
)
def test_doctor_can_access_other_doctors_video_endpoints_by_default(
    project_patient,
    active_prescription,
    django_capture_on_commit_callbacks,
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
    with patch("apps.training.tasks.run_motion_analysis_job.delay") as delay:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            created = _client(other_doctor).post(
                f"/api/training/videos/{video.id}/analysis-jobs/"
            )

    assert download.status_code == 200
    assert download.data["url"].startswith(
        f"https://cdn.example.com/{video.object_key}?e="
    )
    assert latest.status_code == 200
    assert latest.data is None
    assert created.status_code == 201
    job = MotionAnalysisJob.objects.get(pk=created.data["id"])
    assert job.requested_by == other_doctor
    assert len(callbacks) == 1
    delay.assert_not_called()


@pytest.mark.django_db
def test_create_analysis_job_enqueues_only_after_transaction_commit(
    doctor,
    project_patient,
    active_prescription,
    django_capture_on_commit_callbacks,
):
    action = _shoulder_press_action(active_prescription)
    video = _video(project_patient, active_prescription, action)

    with patch("apps.training.tasks.run_motion_analysis_job.delay") as delay:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            response = _client(doctor).post(
                f"/api/training/videos/{video.id}/analysis-jobs/"
            )
            delay.assert_not_called()

        assert response.status_code == 201, response.data
        assert len(callbacks) == 1
        job = MotionAnalysisJob.objects.get(pk=response.data["id"])
        assert job.status == MotionAnalysisJob.Status.PENDING
        assert job.requested_by == doctor

        callbacks[0]()
        delay.assert_called_once_with(job.id)


@pytest.mark.django_db
def test_analysis_job_rejects_non_shoulder_press_and_unattached_video(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    wrong_action_video = _video(project_patient, active_prescription, prescription_action)
    shoulder_action = _shoulder_press_action(active_prescription)
    unattached_video = _video(
        project_patient,
        active_prescription,
        shoulder_action,
        status=TrainingVideo.Status.RECORDING,
    )

    wrong_action_response = _client(doctor).post(
        f"/api/training/videos/{wrong_action_video.id}/analysis-jobs/"
    )
    unattached_response = _client(doctor).post(
        f"/api/training/videos/{unattached_video.id}/analysis-jobs/"
    )

    assert wrong_action_response.status_code == 400
    assert "肩部推举" in str(wrong_action_response.data)
    assert unattached_response.status_code == 400
    assert "绑定" in str(unattached_response.data)
    assert MotionAnalysisJob.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "active_status",
    [MotionAnalysisJob.Status.PENDING, MotionAnalysisJob.Status.RUNNING],
)
def test_api_rejects_duplicate_active_analysis_job(
    active_status,
    doctor,
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
        status=active_status,
    )

    response = _client(doctor).post(f"/api/training/videos/{video.id}/analysis-jobs/")

    assert response.status_code == 400
    assert "分析任务" in str(response.data)
    assert MotionAnalysisJob.objects.filter(training_video=video).count() == 1


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
def test_failed_job_allows_retry_and_latest_endpoint_returns_new_job(
    doctor,
    project_patient,
    active_prescription,
    django_capture_on_commit_callbacks,
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

    with patch("apps.training.tasks.run_motion_analysis_job.delay"):
        with django_capture_on_commit_callbacks(execute=False):
            create_response = _client(doctor).post(
                f"/api/training/videos/{video.id}/analysis-jobs/"
            )

    latest_response = _client(doctor).get(
        f"/api/training/videos/{video.id}/analysis-jobs/latest/"
    )

    assert create_response.status_code == 201, create_response.data
    assert create_response.data["id"] != failed.id
    assert latest_response.status_code == 200
    assert latest_response.data["id"] == create_response.data["id"]


@pytest.mark.django_db
def test_service_validation_failure_registers_no_enqueue_callback(
    doctor,
    project_patient,
    active_prescription,
    django_capture_on_commit_callbacks,
):
    action = _shoulder_press_action(active_prescription)
    video = _video(
        project_patient,
        active_prescription,
        action,
        status=TrainingVideo.Status.RECORDING,
    )

    with patch("apps.training.tasks.run_motion_analysis_job.delay") as delay:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            response = _client(doctor).post(
                f"/api/training/videos/{video.id}/analysis-jobs/"
            )

    assert response.status_code == 400
    assert callbacks == []
    delay.assert_not_called()
    assert MotionAnalysisJob.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_rolled_back_job_creation_never_enqueues(
    doctor,
    project_patient,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    video = _video(project_patient, active_prescription, action)

    with patch("apps.training.tasks.run_motion_analysis_job.delay") as delay:
        with pytest.raises(RuntimeError, match="force rollback"):
            with transaction.atomic():
                create_analysis_job(video=video, requested_by=doctor)
                raise RuntimeError("force rollback")

    delay.assert_not_called()
    assert MotionAnalysisJob.objects.count() == 0
