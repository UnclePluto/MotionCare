import io
import os
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import timezone

from apps.prescriptions.models import ActionLibraryItem
from apps.training import tasks as training_tasks
from apps.training.analysis import analyze_shoulder_press_keypoints
from apps.training.models import MotionAnalysisJob, TrainingRecord, TrainingVideo
from apps.training.tasks import download_private_video, run_motion_analysis_job
from apps.training.video_services import SHOULDER_PRESS_SOURCE_KEY, create_analysis_job


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
    )
    return job, video, record


class _DownloadResponse(io.BytesIO):
    def __init__(self, content, *, headers=None, socket_timeout=None):
        super().__init__(content)
        self.headers = headers or {}
        self.socket = _TimeoutAwareSocket(socket_timeout)
        self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=self.socket))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


class _TimeoutAwareSocket:
    def __init__(self, timeout):
        self.timeout = timeout
        self.timeouts = []

    def settimeout(self, timeout):
        self.timeout = timeout
        self.timeouts.append(timeout)


def test_private_video_download_uses_timeout_and_destination(tmp_path):
    opener = Mock(return_value=_DownloadResponse(b"video-bytes"))
    destination = tmp_path / "video.mp4"

    download_private_video(
        "https://cdn.example.com/private.mp4?token=secret",
        destination,
        timeout=17,
        max_bytes=1024,
        deadline_seconds=30,
        opener=opener,
    )

    opener.assert_called_once_with(
        "https://cdn.example.com/private.mp4?token=secret",
        timeout=17,
    )
    assert destination.read_bytes() == b"video-bytes"


def test_private_video_download_rejects_declared_content_length_over_limit(tmp_path):
    opener = Mock(
        return_value=_DownloadResponse(
            b"",
            headers={"Content-Length": "11"},
        )
    )

    with pytest.raises(ValueError, match="超过允许大小"):
        download_private_video(
            "https://cdn.example.com/private.mp4?token=secret",
            tmp_path / "video.mp4",
            timeout=17,
            max_bytes=10,
            deadline_seconds=30,
            opener=opener,
        )


def test_private_video_download_stops_when_streamed_bytes_exceed_limit(tmp_path):
    destination = tmp_path / "video.mp4"

    with pytest.raises(ValueError, match="超过允许大小"):
        download_private_video(
            "https://cdn.example.com/private.mp4?token=secret",
            destination,
            timeout=17,
            max_bytes=10,
            deadline_seconds=30,
            opener=Mock(return_value=_DownloadResponse(b"01234567890")),
        )

    assert destination.read_bytes() == b""


def test_private_video_download_stops_at_overall_deadline(tmp_path):
    clock = [0.0]

    class SlowResponse(_DownloadResponse):
        def read(self, size=-1):
            clock[0] += 0.6
            return b"x" if clock[0] < 1.8 else b""

    with (
        patch("apps.training.tasks.time.monotonic", side_effect=lambda: clock[0]),
        pytest.raises(TimeoutError, match="超过整体下载时限"),
    ):
        download_private_video(
            "https://cdn.example.com/private.mp4?token=secret",
            tmp_path / "video.mp4",
            timeout=17,
            max_bytes=1024,
            deadline_seconds=1,
            opener=Mock(return_value=SlowResponse(b"")),
        )


def test_private_video_download_limits_connect_timeout_to_remaining_deadline(tmp_path):
    class SlowOpener:
        def __init__(self):
            self.timeouts = []

        def __call__(self, url, *, timeout):
            self.timeouts.append(timeout)
            time.sleep(timeout)
            raise TimeoutError("模拟连接超时")

    opener = SlowOpener()
    started_at = time.monotonic()

    with pytest.raises(TimeoutError, match="模拟连接超时"):
        download_private_video(
            "https://cdn.example.com/private.mp4?token=secret",
            tmp_path / "video.mp4",
            timeout=0.4,
            max_bytes=1024,
            deadline_seconds=0.08,
            opener=opener,
        )

    elapsed = time.monotonic() - started_at
    assert opener.timeouts == [pytest.approx(0.08, abs=0.03)]
    assert 0.04 <= elapsed < 0.2


def test_private_video_download_limits_blocking_read_to_remaining_deadline(tmp_path):
    class SlowReadResponse(_DownloadResponse):
        def read(self, size=-1):
            time.sleep(self.socket.timeout)
            raise TimeoutError("模拟读取超时")

    response = SlowReadResponse(b"", socket_timeout=0.4)
    started_at = time.monotonic()

    with pytest.raises(TimeoutError, match="模拟读取超时"):
        download_private_video(
            "https://cdn.example.com/private.mp4?token=secret",
            tmp_path / "video.mp4",
            timeout=0.4,
            max_bytes=1024,
            deadline_seconds=0.08,
            opener=Mock(return_value=response),
        )

    elapsed = time.monotonic() - started_at
    assert response.socket.timeouts == [pytest.approx(0.08, abs=0.03)]
    assert 0.04 <= elapsed < 0.2


def test_private_video_download_reduces_socket_timeout_before_each_read(tmp_path):
    class ChunkedResponse(_DownloadResponse):
        def __init__(self):
            super().__init__(b"", socket_timeout=None)
            self.chunks = iter((b"first", b"second", b""))

        def read(self, size=-1):
            if self.socket.timeout is None:
                raise AssertionError("读取前未设置 socket timeout")
            time.sleep(min(self.socket.timeout, 0.015))
            return next(self.chunks)

    response = ChunkedResponse()

    download_private_video(
        "https://cdn.example.com/private.mp4?token=secret",
        tmp_path / "video.mp4",
        timeout=0.4,
        max_bytes=1024,
        deadline_seconds=0.2,
        opener=Mock(return_value=response),
    )

    assert len(response.socket.timeouts) == 3
    assert all(
        later < earlier
        for earlier, later in zip(response.socket.timeouts, response.socket.timeouts[1:])
    )


def test_private_video_download_rejects_response_without_controllable_socket(tmp_path):
    class UncontrollableResponse(io.BytesIO):
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.close()

    with pytest.raises(RuntimeError, match="无法设置.*socket timeout"):
        download_private_video(
            "https://cdn.example.com/private.mp4?token=secret",
            tmp_path / "video.mp4",
            timeout=0.4,
            max_bytes=1024,
            deadline_seconds=0.2,
            opener=Mock(return_value=UncontrollableResponse(b"")),
        )


@pytest.mark.django_db
@override_settings(
    MOTION_ANALYSIS_DOWNLOAD_TIMEOUT_SECONDS=17,
    MOTION_ANALYSIS_DOWNLOAD_DEADLINE_SECONDS=41,
    MOTION_ANALYSIS_SAMPLE_FPS=4,
    TRAINING_VIDEO_MAX_SIZE_BYTES=900,
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

    def fake_download(
        url,
        destination,
        *,
        timeout,
        max_bytes,
        deadline_seconds,
        opener=None,
    ):
        assert url == "https://cdn.example.com/private.mp4?token=sensitive"
        assert timeout == 17
        assert max_bytes == 900
        assert deadline_seconds == 41
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

    def failing_download(
        url,
        destination,
        *,
        timeout,
        max_bytes,
        deadline_seconds,
        opener=None,
    ):
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
def test_task_cleans_temporary_file_when_download_exceeds_limit(
    project_patient,
    active_prescription,
):
    job, _, _ = _analysis_job(project_patient, active_prescription)
    seen_paths = []

    def oversized_download(
        url,
        destination,
        *,
        timeout,
        max_bytes,
        deadline_seconds,
        opener=None,
    ):
        destination.write_bytes(b"partial")
        seen_paths.append(str(destination))
        raise ValueError("响应内容超过允许大小")

    with (
        patch(
            "apps.training.tasks.create_private_download_url",
            return_value="https://cdn.example.com/private.mp4?token=sensitive",
        ),
        patch(
            "apps.training.tasks.download_private_video",
            side_effect=oversized_download,
        ),
    ):
        run_motion_analysis_job.run(job.id)

    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.FAILED
    assert "超过允许大小" in job.failure_reason
    assert seen_paths and all(not os.path.exists(path) for path in seen_paths)


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


def _mark_job_running(job, *, started_at):
    job.status = MotionAnalysisJob.Status.RUNNING
    job.started_at = started_at
    job.finished_at = None
    job.save(update_fields=["status", "started_at", "finished_at", "updated_at"])


@pytest.mark.django_db
@override_settings(MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS=300)
def test_recovery_marks_stale_running_job_failed_with_audit_reason(
    project_patient,
    active_prescription,
):
    job, _, _ = _analysis_job(project_patient, active_prescription)
    _mark_job_running(job, started_at=timezone.now() - timedelta(seconds=301))

    recovered_count = training_tasks.recover_stale_motion_analysis_jobs.run()

    job.refresh_from_db()
    assert recovered_count == 1
    assert job.status == MotionAnalysisJob.Status.FAILED
    assert job.finished_at is not None
    assert "阶段=running_stale_recovery" in job.failure_reason
    assert "原因=running_timeout" in job.failure_reason


@pytest.mark.django_db
@override_settings(MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS=300)
def test_recovery_leaves_recent_running_job_unchanged(
    project_patient,
    active_prescription,
):
    job, _, _ = _analysis_job(project_patient, active_prescription)
    _mark_job_running(job, started_at=timezone.now() - timedelta(seconds=299))

    recovered_count = training_tasks.recover_stale_motion_analysis_jobs.run()

    job.refresh_from_db()
    assert recovered_count == 0
    assert job.status == MotionAnalysisJob.Status.RUNNING
    assert job.finished_at is None
    assert job.failure_reason == ""


@pytest.mark.django_db
@override_settings(MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS=300)
def test_recovery_allows_doctor_to_create_a_new_job(
    project_patient,
    active_prescription,
):
    stale_job, video, _ = _analysis_job(project_patient, active_prescription)
    _mark_job_running(
        stale_job,
        started_at=timezone.now() - timedelta(seconds=301),
    )
    training_tasks.recover_stale_motion_analysis_jobs.run()

    with patch("apps.training.tasks.run_motion_analysis_job.delay"):
        new_job = create_analysis_job(video=video, requested_by=None)

    stale_job.refresh_from_db()
    assert stale_job.status == MotionAnalysisJob.Status.FAILED
    assert new_job.status == MotionAnalysisJob.Status.PENDING
    assert new_job.training_video_id == video.id


@pytest.mark.django_db
@override_settings(MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS=60)
def test_old_worker_success_does_not_overwrite_recovered_failure(
    project_patient,
    active_prescription,
):
    job, _, _ = _analysis_job(project_patient, active_prescription)
    result_payload = {
        "total_count": 1,
        "standard_count": 1,
        "nonstandard_count": 0,
        "rep_details": [],
        "quality_flags": ["camera_angle_unverified"],
    }

    def fake_download(
        url,
        destination,
        *,
        timeout,
        max_bytes,
        deadline_seconds,
        opener=None,
    ):
        destination.write_bytes(b"video")

    def recover_during_analysis(frames):
        MotionAnalysisJob.objects.filter(pk=job.pk).update(
            started_at=timezone.now() - timedelta(seconds=61)
        )
        assert training_tasks.recover_stale_motion_analysis_jobs.run() == 1
        return result_payload

    with (
        patch(
            "apps.training.tasks.create_private_download_url",
            return_value="https://cdn.example.com/private.mp4?token=sensitive",
        ),
        patch("apps.training.tasks.download_private_video", side_effect=fake_download),
        patch(
            "apps.training.tasks.extract_video_keypoint_frames",
            return_value=[{"timestamp_ms": 0, "keypoints": {}}],
        ),
        patch(
            "apps.training.tasks.analyze_shoulder_press_keypoints",
            side_effect=recover_during_analysis,
        ),
    ):
        run_motion_analysis_job.run(job.id)

    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.FAILED
    assert "原因=running_timeout" in job.failure_reason
    assert job.total_count is None
    assert job.result_payload == {}


@pytest.mark.django_db
@override_settings(MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS=60)
def test_old_worker_failure_does_not_overwrite_recovered_failure(
    project_patient,
    active_prescription,
):
    job, _, _ = _analysis_job(project_patient, active_prescription)
    _mark_job_running(job, started_at=timezone.now() - timedelta(seconds=61))
    training_tasks.recover_stale_motion_analysis_jobs.run()

    training_tasks._persist_failure(job.id, "旧 worker 失败结果")

    job.refresh_from_db()
    assert job.status == MotionAnalysisJob.Status.FAILED
    assert "原因=running_timeout" in job.failure_reason
    assert "旧 worker" not in job.failure_reason


def test_stale_recovery_task_is_scheduled_in_celery_beat():
    schedule = settings.CELERY_BEAT_SCHEDULE["recover-stale-motion-analysis-jobs"]

    assert schedule["task"] == (
        "apps.training.tasks.recover_stale_motion_analysis_jobs"
    )
    assert schedule["schedule"] == settings.MOTION_ANALYSIS_STALE_RECOVERY_INTERVAL_SECONDS
