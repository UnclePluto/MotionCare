import io
import os
import uuid
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.prescriptions.models import ActionLibraryItem
from apps.training.analysis import analyze_shoulder_press_keypoints
from apps.training.models import MotionAnalysisJob, TrainingRecord, TrainingVideo
from apps.training.tasks import download_private_video, run_motion_analysis_job
from apps.training.video_services import SHOULDER_PRESS_SOURCE_KEY


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


def test_marks_a_low_amplitude_attempt_as_range_too_small():
    frames = _sequence(
        [
            (0, "down", {}),
            (100, "down", {}),
            (500, "partial", {}),
            (600, "partial", {}),
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
        upload_token_expires_at=timezone.now(),
        uploaded_at=timezone.now(),
    )
    job = MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=record,
        project_patient=project_patient,
        prescription_action=action,
    )
    return job, video, record


class _DownloadResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


def test_private_video_download_uses_timeout_and_destination(tmp_path):
    opener = Mock(return_value=_DownloadResponse(b"video-bytes"))
    destination = tmp_path / "video.mp4"

    download_private_video(
        "https://cdn.example.com/private.mp4?token=secret",
        destination,
        timeout=17,
        opener=opener,
    )

    opener.assert_called_once_with(
        "https://cdn.example.com/private.mp4?token=secret",
        timeout=17,
    )
    assert destination.read_bytes() == b"video-bytes"


@pytest.mark.django_db
@override_settings(
    MOTION_ANALYSIS_DOWNLOAD_TIMEOUT_SECONDS=17,
    MOTION_ANALYSIS_SAMPLE_FPS=4,
)
def test_task_downloads_analyzes_persists_success_and_cleans_temp_file(
    project_patient,
    active_prescription,
):
    job, video, record = _analysis_job(project_patient, active_prescription)
    seen_paths = []
    result_payload = {
        "total_count": 2,
        "standard_count": 1,
        "nonstandard_count": 1,
        "rep_details": [],
        "quality_flags": ["camera_angle_unverified"],
    }

    def fake_download(url, destination, *, timeout, opener=None):
        assert url == "https://cdn.example.com/private.mp4?token=sensitive"
        assert timeout == 17
        destination.write_bytes(b"video")
        seen_paths.append(str(destination))

    def fake_extract(path, *, sample_fps):
        assert os.path.exists(path)
        assert sample_fps == 4
        return [{"timestamp_ms": 0, "keypoints": {}}]

    with (
        patch(
            "apps.training.tasks.create_private_download_url",
            return_value="https://cdn.example.com/private.mp4?token=sensitive",
        ),
        patch("apps.training.tasks.download_private_video", side_effect=fake_download),
        patch(
            "apps.training.tasks.extract_video_keypoint_frames",
            side_effect=fake_extract,
        ),
        patch(
            "apps.training.tasks.analyze_shoulder_press_keypoints",
            return_value=result_payload,
        ),
    ):
        returned = run_motion_analysis_job.run(job.id)

    job.refresh_from_db()
    video.refresh_from_db()
    record.refresh_from_db()
    assert returned.pk == job.pk
    assert job.status == MotionAnalysisJob.Status.SUCCEEDED
    assert job.started_at is not None
    assert job.finished_at is not None
    assert job.total_count == 2
    assert job.standard_count == 1
    assert job.nonstandard_count == 1
    assert job.result_payload == result_payload
    assert job.failure_reason == ""
    assert seen_paths and all(not os.path.exists(path) for path in seen_paths)
    assert video.status == TrainingVideo.Status.ATTACHED
    assert record.status == TrainingRecord.Status.COMPLETED


@pytest.mark.django_db
def test_task_persists_sanitized_failure_and_cleans_temp_without_touching_video(
    project_patient,
    active_prescription,
):
    job, video, record = _analysis_job(project_patient, active_prescription)
    seen_paths = []

    def failing_download(url, destination, *, timeout, opener=None):
        destination.write_bytes(b"partial")
        seen_paths.append(str(destination))
        raise RuntimeError(
            "download failed: https://cdn.example.com/private.mp4?e=1&token=ak:secret"
        )

    with (
        patch(
            "apps.training.tasks.create_private_download_url",
            return_value="https://cdn.example.com/private.mp4?e=1&token=ak:secret",
        ),
        patch("apps.training.tasks.download_private_video", side_effect=failing_download),
    ):
        returned = run_motion_analysis_job.run(job.id)

    job.refresh_from_db()
    video.refresh_from_db()
    record.refresh_from_db()
    assert returned.pk == job.pk
    assert job.status == MotionAnalysisJob.Status.FAILED
    assert job.started_at is not None
    assert job.finished_at is not None
    assert "下载视频" in job.failure_reason
    assert "RuntimeError" in job.failure_reason
    assert "https://" not in job.failure_reason
    assert "ak:secret" not in job.failure_reason
    assert seen_paths and all(not os.path.exists(path) for path in seen_paths)
    assert TrainingVideo.objects.filter(pk=video.pk).exists()
    assert TrainingRecord.objects.filter(pk=record.pk).exists()
    assert video.status == TrainingVideo.Status.ATTACHED
    assert record.status == TrainingRecord.Status.COMPLETED


@pytest.mark.django_db
@pytest.mark.parametrize(
    "terminal_status",
    [
        MotionAnalysisJob.Status.SUCCEEDED,
        MotionAnalysisJob.Status.FAILED,
        MotionAnalysisJob.Status.RUNNING,
    ],
)
def test_repeated_terminal_or_running_task_is_idempotent(
    terminal_status,
    project_patient,
    active_prescription,
):
    job, _, _ = _analysis_job(project_patient, active_prescription)
    job.status = terminal_status
    job.started_at = timezone.now()
    if terminal_status != MotionAnalysisJob.Status.RUNNING:
        job.finished_at = timezone.now()
    job.save(update_fields=["status", "started_at", "finished_at", "updated_at"])

    with patch("apps.training.tasks.create_private_download_url") as download_url:
        returned = run_motion_analysis_job.run(job.id)

    assert returned.pk == job.pk
    assert returned.status == terminal_status
    download_url.assert_not_called()
