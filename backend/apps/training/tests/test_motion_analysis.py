import uuid
from datetime import timedelta

import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.prescriptions.models import ActionLibraryItem
from apps.training import tasks as training_tasks
from apps.training.models import MotionAnalysisJob, TrainingRecord, TrainingVideo
from apps.training.video_services import SHOULDER_PRESS_SOURCE_KEY


OFFICIAL_MOTION_SOURCE_KEYS = (
    "motion-aerobic-high-knee",
    "motion-balance-sit-stand",
    "motion-resistance-leg-kickback",
    "motion-resistance-row",
    SHOULDER_PRESS_SOURCE_KEY,
)
UNSUPPORTED_ANALYSIS_SOURCE_KEYS = ("motion-aerobic-high-knee",)
QINIU_ETAG = "F" + "a" * 27


def test_business_analysis_profile_freezes_supported_versions():
    from apps.training.motion_analysis_support import get_analysis_profile

    profile = get_analysis_profile(SHOULDER_PRESS_SOURCE_KEY)

    assert profile is not None
    assert profile.algorithm_name == "pp-tiny-pose"
    assert profile.algorithm_version == "PP-TinyPose_128x96"
    assert profile.rule_version == "shoulder-press-v2"
    assert profile.parameter_version == "shoulder-press-v2-defaults"
    assert profile.subject_tracker_version == "primary-subject-v1"
    assert get_analysis_profile("motion-aerobic-high-knee") is None
    assert get_analysis_profile(None) is None


@pytest.mark.django_db
def test_skeleton_object_key_is_private_unpredictable_and_contains_no_identity(
    project_patient,
    active_prescription,
):
    from apps.training.motion_analysis_storage import build_skeleton_object_key

    _, first_video, _ = _analysis_job(project_patient, active_prescription)
    first_key = build_skeleton_object_key(first_video)
    second_key = build_skeleton_object_key(first_video)

    assert first_key != second_key
    assert first_key.startswith(
        f"motion-analysis/{project_patient.id}/{first_video.training_date:%Y/%m}/"
    )
    assert first_key.endswith("/skeleton.mp4")
    assert project_patient.patient.name not in first_key
    assert project_patient.patient.phone not in first_key


@pytest.mark.django_db
def test_doctor_cannot_create_or_recreate_analysis_job(
    doctor,
    project_patient,
    active_prescription,
):
    _, video, _ = _analysis_job(project_patient, active_prescription)
    client = APIClient()
    client.force_authenticate(doctor)

    response = client.post(f"/api/training/videos/{video.id}/analysis-jobs/")

    assert response.status_code == 404


def _set_complete_skeleton_metadata(job):
    job.skeleton_bucket = "motioncare-training"
    job.skeleton_object_key = (
        f"motion-analysis/{job.project_patient_id}/2026/09/"
        "11111111-1111-4111-8111-111111111111/skeleton.mp4"
    )
    job.skeleton_object_hash = QINIU_ETAG
    job.skeleton_size_bytes = 2048
    job.skeleton_duration_seconds = 120.0
    job.skeleton_width = 720
    job.skeleton_height = 1280
    job.skeleton_fps = 29.97


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_DOWNLOAD_DOMAIN="https://cdn.example.com",
    QINIU_DOWNLOAD_TOKEN_TTL_SECONDS=600,
)
def test_skeleton_url_is_issued_only_for_latest_succeeded_job_with_complete_metadata(
    doctor,
    project_patient,
    active_prescription,
):
    job, video, _ = _analysis_job(project_patient, active_prescription)
    job.status = MotionAnalysisJob.Status.SUCCEEDED
    _set_complete_skeleton_metadata(job)
    job.finished_at = timezone.now()
    job.save()
    before = int(timezone.now().timestamp())

    response = APIClient()
    response.force_authenticate(doctor)
    result = response.get(f"/api/training/videos/{video.id}/analysis-jobs/latest/skeleton-url/")
    after = int(timezone.now().timestamp())

    assert result.status_code == 200, result.data
    assert result.data["url"].startswith(f"https://cdn.example.com/{job.skeleton_object_key}?e=")
    assert "token=ak-test:" in result.data["url"]
    expiry = int(result.data["url"].split("?e=", 1)[1].split("&", 1)[0])
    assert before + 600 <= expiry <= after + 600


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("analysis_status", "missing_field"),
    [
        (MotionAnalysisJob.Status.PENDING, None),
        (MotionAnalysisJob.Status.RUNNING, None),
        (MotionAnalysisJob.Status.FAILED, None),
        (MotionAnalysisJob.Status.SUCCEEDED, "skeleton_bucket"),
        (MotionAnalysisJob.Status.SUCCEEDED, "skeleton_object_key"),
        (MotionAnalysisJob.Status.SUCCEEDED, "skeleton_object_hash"),
        (MotionAnalysisJob.Status.SUCCEEDED, "skeleton_size_bytes"),
        (MotionAnalysisJob.Status.SUCCEEDED, "skeleton_duration_seconds"),
        (MotionAnalysisJob.Status.SUCCEEDED, "skeleton_width"),
        (MotionAnalysisJob.Status.SUCCEEDED, "skeleton_height"),
        (MotionAnalysisJob.Status.SUCCEEDED, "skeleton_fps"),
    ],
)
def test_skeleton_url_is_unavailable_for_non_success_or_incomplete_metadata(
    analysis_status,
    missing_field,
    doctor,
    project_patient,
    active_prescription,
):
    job, video, _ = _analysis_job(project_patient, active_prescription)
    job.status = analysis_status
    _set_complete_skeleton_metadata(job)
    if missing_field:
        field = MotionAnalysisJob._meta.get_field(missing_field)
        setattr(job, missing_field, "" if field.get_internal_type() == "CharField" else None)
    job.save()
    client = APIClient()
    client.force_authenticate(doctor)

    response = client.get(f"/api/training/videos/{video.id}/analysis-jobs/latest/skeleton-url/")

    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(
    QINIU_BUCKET="motioncare-training",
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_DOWNLOAD_DOMAIN="https://cdn.example.com",
)
@pytest.mark.parametrize(
    "corruption",
    [
        "wrong_bucket",
        "wrong_project",
        "wrong_month",
        "non_v4_uuid",
        "wrong_filename",
        "malformed_hash",
        "empty_file",
    ],
)
def test_skeleton_url_rejects_nonempty_but_untrusted_database_metadata(
    corruption,
    doctor,
    project_patient,
    active_prescription,
    monkeypatch,
):
    job, video, _ = _analysis_job(project_patient, active_prescription)
    job.status = MotionAnalysisJob.Status.SUCCEEDED
    _set_complete_skeleton_metadata(job)
    if corruption == "wrong_bucket":
        job.skeleton_bucket = "other-private-bucket"
    elif corruption == "wrong_project":
        job.skeleton_object_key = job.skeleton_object_key.replace(
            f"motion-analysis/{project_patient.id}/",
            f"motion-analysis/{project_patient.id + 1}/",
            1,
        )
    elif corruption == "wrong_month":
        job.skeleton_object_key = job.skeleton_object_key.replace("/2026/09/", "/2026/08/")
    elif corruption == "non_v4_uuid":
        job.skeleton_object_key = job.skeleton_object_key.replace(
            "11111111-1111-4111-8111-111111111111",
            "11111111-1111-1111-8111-111111111111",
        )
    elif corruption == "wrong_filename":
        job.skeleton_object_key = job.skeleton_object_key.removesuffix("skeleton.mp4") + "other.mp4"
    elif corruption == "malformed_hash":
        job.skeleton_object_hash = "not-a-qiniu-etag"
    elif corruption == "empty_file":
        job.skeleton_size_bytes = 0
    job.save()
    signed = []

    def signer(**kwargs):
        signed.append(kwargs)
        return "https://should-not-be-issued.example"

    monkeypatch.setattr(
        "apps.training.video_views.create_private_object_download_url",
        signer,
    )
    client = APIClient()
    client.force_authenticate(doctor)

    response = client.get(f"/api/training/videos/{video.id}/analysis-jobs/latest/skeleton-url/")

    assert response.status_code == 404
    assert signed == []


@pytest.mark.django_db
@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=True)
def test_skeleton_url_requires_row_level_access(
    project_patient,
    active_prescription,
):
    job, video, _ = _analysis_job(project_patient, active_prescription)
    job.status = MotionAnalysisJob.Status.SUCCEEDED
    _set_complete_skeleton_metadata(job)
    job.save()
    unrelated_doctor = User.objects.create_user(
        phone="13800009997",
        password="pass123456",
        name="无权限医生",
        role=User.Role.DOCTOR,
    )
    client = APIClient()
    client.force_authenticate(unrelated_doctor)

    response = client.get(f"/api/training/videos/{video.id}/analysis-jobs/latest/skeleton-url/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_latest_analysis_status_response_never_exposes_internal_job_data(
    doctor,
    project_patient,
    active_prescription,
):
    job, video, _ = _analysis_job(project_patient, active_prescription)
    job.status = MotionAnalysisJob.Status.FAILED
    job.failure_code = "subject_unstable"
    job.failure_reason = "token=secret /private/patient/video.mp4"
    job.result_payload = {
        "signed_url": "https://private.example/video?token=url-secret",
        "patient_note": "患者隐私",
    }
    job.skeleton_bucket = "private-bucket"
    job.skeleton_object_key = "motion-analysis/private/skeleton.mp4"
    job.lease_token_hash = "lease-secret-hash"
    job.save()
    client = APIClient()
    client.force_authenticate(doctor)

    response = client.get(f"/api/training/videos/{video.id}/analysis-jobs/latest/")

    serialized = str(response.data)
    assert response.status_code == 200
    assert set(response.data) == {
        "id",
        "status",
        "analysis_failure_message",
        "skeleton_available",
        "started_at",
        "finished_at",
        "created_at",
    }
    assert response.data["status"] == MotionAnalysisJob.Status.FAILED
    assert response.data["analysis_failure_message"] == ("自动分析未完成，请填写训练结果")
    for secret in (
        "failure_reason",
        "subject_unstable",
        "secret",
        "private-bucket",
        "motion-analysis/private",
        "患者隐私",
    ):
        assert secret not in serialized


def _analysis_job(project_patient, active_prescription):
    item = ActionLibraryItem.objects.get(source_key=SHOULDER_PRESS_SOURCE_KEY)
    action = active_prescription.add_action_snapshot(
        item,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=2,
    )
    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=2,
    )
    video = TrainingVideo.objects.create(
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
        status=TrainingVideo.Status.ATTACHED,
        uploaded_at=timezone.now(),
    )
    job = MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=record,
        project_patient=project_patient,
        prescription_action=action,
        algorithm_version="PP-TinyPose_128x96",
        rule_version="shoulder-press-v1",
    )
    return job, video, record


def _mark_job_running(job, *, started_at, lease_expires_at):
    job.status = MotionAnalysisJob.Status.RUNNING
    job.started_at = started_at
    job.lease_token_hash = "lease-hash"
    job.lease_expires_at = lease_expires_at
    job.finished_at = None
    job.save(
        update_fields=[
            "status",
            "started_at",
            "lease_token_hash",
            "lease_expires_at",
            "finished_at",
            "updated_at",
        ]
    )


@pytest.mark.django_db
def test_recovery_marks_expired_lease_failed_without_using_started_at(
    project_patient,
    active_prescription,
):
    job, _, _ = _analysis_job(project_patient, active_prescription)
    now = timezone.now()
    _mark_job_running(
        job,
        started_at=now,
        lease_expires_at=now - timedelta(seconds=1),
    )

    recovered_count = training_tasks.recover_stale_motion_analysis_jobs.run()

    job.refresh_from_db()
    assert recovered_count == 1
    assert job.status == MotionAnalysisJob.Status.FAILED
    assert job.finished_at is not None
    assert job.failure_code == "lease_expired"
    assert job.failure_reason == "动作分析任务租约已过期"
    assert job.lease_token_hash == ""
    assert job.lease_expires_at is None


@pytest.mark.django_db
def test_recovery_leaves_lease_expiring_exactly_now_unchanged_even_if_started_long_ago(
    project_patient,
    active_prescription,
):
    from apps.training.motion_analysis_monitoring import expire_stale_motion_analysis_jobs

    job, _, _ = _analysis_job(project_patient, active_prescription)
    now = timezone.now()
    _mark_job_running(
        job,
        started_at=now - timedelta(days=1),
        lease_expires_at=now,
    )

    recovered_count = expire_stale_motion_analysis_jobs(now=now)

    job.refresh_from_db()
    assert recovered_count == 0
    assert job.status == MotionAnalysisJob.Status.RUNNING
    assert job.finished_at is None
    assert job.failure_reason == ""


def test_stale_recovery_task_is_scheduled_in_celery_beat():
    schedule = settings.CELERY_BEAT_SCHEDULE["recover-stale-motion-analysis-jobs"]

    assert schedule["task"] == ("apps.training.tasks.recover_stale_motion_analysis_jobs")
    assert schedule["schedule"] == settings.MOTION_ANALYSIS_STALE_RECOVERY_INTERVAL_SECONDS
