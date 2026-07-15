from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.training.analysis import analyze_shoulder_press_keypoints
from apps.training.models import MotionAnalysisJob, TrainingRecord, TrainingVideo
from apps.training.tasks import run_motion_analysis_job


def _frame(ms, wrist_y, confidence=0.95):
    return {
        "timestamp_ms": ms,
        "keypoints": {
            "left_shoulder": {"x": 0.4, "y": 0.5, "score": confidence},
            "left_wrist": {"x": 0.4, "y": wrist_y, "score": confidence},
        },
    }


def test_shoulder_press_rule_counts_and_classifies_repetitions():
    result = analyze_shoulder_press_keypoints(
        [_frame(0, 0.52), _frame(1000, 0.28), _frame(2200, 0.52)]
    )
    assert result["total_count"] == 1
    assert result["standard_count"] == 1


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_DOWNLOAD_DOMAIN="https://cdn.example.com",
)
def test_analysis_task_persists_rule_result(
    project_patient, active_prescription, prescription_action
):
    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
    )
    video = TrainingVideo.objects.create(
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
    job = MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=record,
        project_patient=project_patient,
        prescription_action=prescription_action,
    )
    frames = [_frame(0, 0.52), _frame(1000, 0.28), _frame(2200, 0.52)]
    with patch("apps.training.tasks.extract_keypoint_frames", return_value=(frames, "v1")):
        run_motion_analysis_job(job.id)

    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.SUCCEEDED
    assert (job.total_count, job.standard_count, job.nonstandard_count) == (1, 1, 0)
