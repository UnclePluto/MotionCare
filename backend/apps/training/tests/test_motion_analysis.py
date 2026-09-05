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
from apps.training.analysis import analyze_shoulder_press_keypoints
from apps.training.models import MotionAnalysisJob, TrainingRecord, TrainingVideo
from apps.training.pose_inference import PP_TINYPOSE_MODEL_NAME
from apps.training.shoulder_press_v2 import (
    SHOULDER_PRESS_RULE_VERSION,
    analyze_shoulder_press_keypoints_v2,
)
from apps.training.video_services import SHOULDER_PRESS_SOURCE_KEY


OFFICIAL_MOTION_SOURCE_KEYS = (
    "motion-aerobic-high-knee",
    "motion-balance-sit-stand",
    "motion-resistance-leg-kickback",
    "motion-resistance-row",
    SHOULDER_PRESS_SOURCE_KEY,
)
UNSUPPORTED_ANALYSIS_SOURCE_KEYS = OFFICIAL_MOTION_SOURCE_KEYS[:-1]


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
    job.skeleton_object_hash = "skeleton-hash"
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


def _frame(
    timestamp_ms,
    position,
    *,
    left_score=0.95,
    right_score=0.95,
    left_position=None,
    right_position=None,
):
    positions = {
        "down": {
            "left_elbow": (0.32, 0.56),
            "left_wrist": (0.24, 0.52),
            "right_elbow": (0.68, 0.56),
            "right_wrist": (0.76, 0.52),
        },
        "partial": {
            "left_elbow": (0.36, 0.44),
            "left_wrist": (0.32, 0.39),
            "right_elbow": (0.64, 0.44),
            "right_wrist": (0.68, 0.39),
        },
        "partial_low": {
            "left_elbow": (0.36, 0.45),
            "left_wrist": (0.32, 0.44),
            "right_elbow": (0.64, 0.45),
            "right_wrist": (0.68, 0.44),
        },
        "partial_peak": {
            "left_elbow": (0.39, 0.40),
            "left_wrist": (0.36, 0.35),
            "right_elbow": (0.61, 0.40),
            "right_wrist": (0.64, 0.35),
        },
        "up": {
            "left_elbow": (0.40, 0.37),
            "left_wrist": (0.40, 0.25),
            "right_elbow": (0.60, 0.37),
            "right_wrist": (0.60, 0.25),
        },
    }
    keypoints = {}
    for side, score, selected_position in (
        ("left", left_score, left_position or position),
        ("right", right_score, right_position or position),
    ):
        keypoints[f"{side}_shoulder"] = {
            "x": 0.4 if side == "left" else 0.6,
            "y": 0.5,
            "score": score,
        }
        keypoints[f"{side}_hip"] = {
            "x": 0.42 if side == "left" else 0.58,
            "y": 0.8,
            "score": score,
        }
        for joint in ("elbow", "wrist"):
            x, y = positions[selected_position][f"{side}_{joint}"]
            keypoints[f"{side}_{joint}"] = {"x": x, "y": y, "score": score}
    return {"timestamp_ms": timestamp_ms, "keypoints": keypoints}


def _sequence(samples):
    return [_frame(timestamp_ms, position, **kwargs) for timestamp_ms, position, kwargs in samples]


def test_counts_only_debounced_down_up_down_repetitions():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (250, "up", {}),  # 单帧噪声不得确认状态
            (350, "partial", {}),
            (500, "up", {}),
            (600, "up", {}),
            (850, "partial", {}),
            (1200, "down", {}),
            (1300, "down", {}),
            (1600, "partial", {}),
            (1900, "up", {}),
            (2000, "up", {}),
            (2300, "partial", {}),
            (2700, "down", {}),
            (2800, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 2
    assert result["standard_count"] == 2
    assert result["nonstandard_count"] == 0
    assert len(result["rep_details"]) == 2
    assert result["total_count"] == result["standard_count"] + result["nonstandard_count"]


def test_sustained_up_state_is_confirmed_only_once():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (500, "up", {}),
            (600, "up", {}),
            (700, "up", {}),
            (800, "up", {}),
            (900, "up", {}),
            (1000, "up", {}),
            (1400, "down", {}),
            (1500, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert result["standard_count"] == 1


def test_uses_the_more_stable_side_when_other_side_has_low_confidence():
    frames = _sequence(
        [
            (0, "down", {"left_score": 0.2, "left_position": "up"}),
            (100, "down", {"left_score": 0.2, "left_position": "partial"}),
            (500, "up", {"left_score": 0.2, "left_position": "down"}),
            (600, "up", {"left_score": 0.2, "left_position": "partial"}),
            (1200, "down", {"left_score": 0.2, "left_position": "up"}),
            (1300, "down", {"left_score": 0.2, "left_position": "partial"}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert result["standard_count"] == 1
    assert result["rep_details"][0]["side"] == "right"
    assert "low_confidence" not in result["rep_details"][0]["flags"]


def test_uses_bilateral_average_when_both_sides_are_stable():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (500, "up", {}),
            (600, "up", {}),
            (1200, "down", {}),
            (1300, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert result["rep_details"][0]["side"] == "bilateral"


def test_ignores_incomplete_leading_and_trailing_half_repetitions():
    frames = _sequence(
        [
            (0, "up", {}),
            (100, "up", {}),
            (500, "down", {}),
            (600, "down", {}),
            (1000, "up", {}),
            (1100, "up", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 0
    assert result["rep_details"] == []


def test_does_not_count_a_stationary_partial_pose_as_an_attempt():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (500, "partial", {}),
            (600, "partial", {}),
            (700, "partial", {}),
            (800, "partial", {}),
            (1200, "down", {}),
            (1300, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 0
    assert result["rep_details"] == []


def test_marks_a_rising_and_returning_low_amplitude_attempt_as_range_too_small():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (400, "partial_low", {}),
            (600, "partial_peak", {}),
            (800, "partial_low", {}),
            (1200, "down", {}),
            (1300, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert result["standard_count"] == 0
    assert result["nonstandard_count"] == 1
    assert result["rep_details"][0]["flags"] == ["range_too_small"]


def test_marks_too_fast_repetition_as_tempo_abnormal():
    frames = _sequence(
        [
            (0, "down", {}),
            (40, "down", {}),
            (180, "up", {}),
            (220, "up", {}),
            (500, "down", {}),
            (540, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert "tempo_abnormal" in result["rep_details"][0]["flags"]


def test_marks_repetition_with_low_joint_confidence_nonstandard():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (500, "up", {"left_score": 0.2, "right_score": 0.2}),
            (600, "up", {"left_score": 0.2, "right_score": 0.2}),
            (1200, "down", {}),
            (1300, "down", {}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert result["standard_count"] == 0
    assert result["nonstandard_count"] == 1
    assert "low_confidence" in result["rep_details"][0]["flags"]
    assert result["quality_flags"] == ["camera_angle_unverified"]


def test_includes_the_terminal_down_confirmation_frame_in_rep_quality():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (500, "up", {}),
            (600, "up", {}),
            (1200, "down", {}),
            (1300, "down", {"left_score": 0.1, "right_score": 0.1}),
        ]
    )

    result = analyze_shoulder_press_keypoints(frames)

    assert result["total_count"] == 1
    assert result["standard_count"] == 0
    assert result["rep_details"][0]["start_ms"] == 0
    assert result["rep_details"][0]["end_ms"] == 1300
    assert "low_confidence" in result["rep_details"][0]["flags"]


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
        algorithm_version=PP_TINYPOSE_MODEL_NAME,
        rule_version="shoulder-press-v1",
    )
    return job, video, record


@pytest.mark.parametrize(
    "source_key, expected_available",
    [
        ("motion-aerobic-high-knee", False),
        ("motion-balance-sit-stand", False),
        ("motion-resistance-leg-kickback", False),
        ("motion-resistance-row", False),
        (SHOULDER_PRESS_SOURCE_KEY, True),
        (None, False),
    ],
)
def test_motion_analysis_registry_only_exposes_shoulder_press(
    source_key,
    expected_available,
):
    from apps.training.analysis_registry import analysis_available, get_motion_analyzer

    analyzer = get_motion_analyzer(source_key)

    assert analysis_available(source_key) is expected_available
    if expected_available:
        assert analyzer is not None
        assert analyzer.source_key == SHOULDER_PRESS_SOURCE_KEY
        assert analyzer.algorithm_version == PP_TINYPOSE_MODEL_NAME
        assert analyzer.rule_version == SHOULDER_PRESS_RULE_VERSION
        assert analyzer.analyze_keypoints is analyze_shoulder_press_keypoints_v2
    else:
        assert analyzer is None


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
