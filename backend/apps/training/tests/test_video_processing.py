import hashlib
import subprocess
from pathlib import Path

import pytest
from django.utils import timezone
from unittest.mock import patch

from apps.training.models import (
    TrainingRecord,
    TrainingVideo,
    TrainingVideoSegment,
    VideoProcessingJob,
)
from apps.training.video_processing import (
    QiniuObjectConflictError,
    ensure_qiniu_final_object,
    merge_video_segments,
    process_video_job,
    video_job_lock,
)
from apps.training.tasks import (
    expire_training_video_jobs,
    process_training_video_job,
    retry_failed_video_processing_jobs,
)


class FakeQiniuClient:
    def __init__(self, existing=None):
        self.existing = existing
        self.upload_calls = []

    def file_hash(self, file_path):
        return "final-hash"

    def stat_object(self, bucket, key):
        return self.existing

    def upload_file(self, bucket, key, file_path):
        self.upload_calls.append((bucket, key, str(file_path)))
        self.existing = {
            "key": key,
            "hash": self.file_hash(file_path),
            "size": Path(file_path).stat().st_size,
        }
        return self.existing


def test_merge_video_segments_falls_back_to_transcode_and_keeps_order(tmp_path):
    first = tmp_path / "segment-0.mp4"
    second = tmp_path / "segment-1.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    output = tmp_path / "merged.mp4"
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, command)
        output.write_bytes(b"merged")

    merge_video_segments([first, second], output, command_runner=runner)

    concat_file = tmp_path / "concat.txt"
    concat_lines = concat_file.read_text().splitlines()
    assert str(first) in concat_lines[0]
    assert str(second) in concat_lines[1]
    assert "copy" in calls[0]
    assert "libx264" in calls[1]
    assert output.read_bytes() == b"merged"


def test_qiniu_existing_matching_object_is_reused_without_upload(tmp_path):
    merged = tmp_path / "merged.mp4"
    merged.write_bytes(b"merged")
    client = FakeQiniuClient(
        existing={"key": "training/final.mp4", "hash": "final-hash", "size": 6}
    )

    result = ensure_qiniu_final_object(
        client=client,
        bucket="motioncare",
        key="training/final.mp4",
        file_path=merged,
    )

    assert result["hash"] == "final-hash"
    assert client.upload_calls == []


def test_qiniu_existing_mismatched_object_is_not_overwritten(tmp_path):
    merged = tmp_path / "merged.mp4"
    merged.write_bytes(b"merged")
    client = FakeQiniuClient(
        existing={"key": "training/final.mp4", "hash": "other-hash", "size": 6}
    )

    with pytest.raises(QiniuObjectConflictError):
        ensure_qiniu_final_object(
            client=client,
            bucket="motioncare",
            key="training/final.mp4",
            file_path=merged,
        )

    assert client.upload_calls == []


def test_qiniu_upload_requires_remote_stat_confirmation(tmp_path):
    merged = tmp_path / "merged.mp4"
    merged.write_bytes(b"merged")

    class MissingAfterUploadClient(FakeQiniuClient):
        def stat_object(self, bucket, key):
            return None

        def upload_file(self, bucket, key, file_path):
            self.upload_calls.append((bucket, key, str(file_path)))
            return {"key": key, "hash": "final-hash", "size": 6}

    client = MissingAfterUploadClient()

    with pytest.raises(RuntimeError, match="校验失败"):
        ensure_qiniu_final_object(
            client=client,
            bucket="motioncare",
            key="training/final.mp4",
            file_path=merged,
        )


@pytest.mark.django_db
def test_process_video_job_creates_one_record_and_removes_server_video_files(
    project_patient,
    active_prescription,
    prescription_action,
    settings,
    tmp_path,
    monkeypatch,
):
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key="training/final.mp4",
        status=TrainingVideo.Status.QUEUED,
        segment_count=2,
        uploaded_segment_count=2,
        duration_seconds=1,
        training_date=timezone.localdate(),
        recording_finished_at=timezone.now(),
        processing_expires_at=timezone.now() + timezone.timedelta(hours=48),
    )
    session_dir = settings.TRAINING_VIDEO_TEMP_ROOT / str(video.id)
    session_dir.mkdir(parents=True)
    for index, content in enumerate([b"segment-a", b"segment-b"]):
        path = session_dir / f"segment-{index:06d}.mp4"
        path.write_bytes(content)
        TrainingVideoSegment.objects.create(
            training_video=video,
            sequence_index=index,
            server_file_path=str(path),
            content_type="video/mp4",
            size_bytes=len(content),
            duration_seconds=30,
            object_hash=hashlib.sha256(content).hexdigest(),
        )
    job = VideoProcessingJob.objects.create(
        training_video=video,
        expires_at=video.processing_expires_at,
    )

    def fake_merge(segment_paths, output_path, **kwargs):
        assert [Path(path).name for path in segment_paths] == [
            "segment-000000.mp4",
            "segment-000001.mp4",
        ]
        Path(output_path).write_bytes(b"merged")

    monkeypatch.setattr(
        "apps.training.video_processing.merge_video_segments", fake_merge
    )
    monkeypatch.setattr(
        "apps.training.video_processing.probe_video",
        lambda path: {"duration_seconds": 60, "size_bytes": 6},
    )
    client = FakeQiniuClient()

    process_video_job(job.id, qiniu_client=client)
    process_video_job(job.id, qiniu_client=client)

    video.refresh_from_db()
    job.refresh_from_db()
    assert video.status == TrainingVideo.Status.ATTACHED
    assert job.status == VideoProcessingJob.Status.SUCCEEDED
    assert video.object_hash == "final-hash"
    assert TrainingRecord.objects.filter(project_patient=project_patient).count() == 1
    assert not session_dir.exists()
    assert len(client.upload_calls) == 1


@pytest.mark.django_db
def test_processing_failure_is_scheduled_for_automatic_retry(
    project_patient,
    active_prescription,
    prescription_action,
    settings,
    tmp_path,
    monkeypatch,
):
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key="training/retry.mp4",
        status=TrainingVideo.Status.QUEUED,
        segment_count=1,
        uploaded_segment_count=1,
        duration_seconds=30,
        training_date=timezone.localdate(),
        processing_expires_at=timezone.now() + timezone.timedelta(hours=48),
    )
    session_dir = settings.TRAINING_VIDEO_TEMP_ROOT / str(video.id)
    session_dir.mkdir(parents=True)
    segment_path = session_dir / "segment-000000.mp4"
    segment_path.write_bytes(b"segment")
    TrainingVideoSegment.objects.create(
        training_video=video,
        sequence_index=0,
        server_file_path=str(segment_path),
        size_bytes=7,
        duration_seconds=30,
        object_hash=hashlib.sha256(b"segment").hexdigest(),
    )
    job = VideoProcessingJob.objects.create(
        training_video=video,
        expires_at=video.processing_expires_at,
    )
    monkeypatch.setattr(
        "apps.training.video_processing.merge_video_segments",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("merge failed")),
    )

    before = timezone.now()
    process_video_job(job.id, qiniu_client=FakeQiniuClient())

    job.refresh_from_db()
    assert job.status == VideoProcessingJob.Status.FAILED
    assert job.attempt_count == 1
    assert job.next_retry_at is not None
    assert job.next_retry_at >= before + timezone.timedelta(
        seconds=settings.TRAINING_VIDEO_RETRY_BASE_SECONDS
    )
    assert session_dir.exists()


@pytest.mark.django_db
def test_retry_scheduler_only_enqueues_due_failed_jobs(
    project_patient, active_prescription, prescription_action
):
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key="training/retry-due.mp4",
        status=TrainingVideo.Status.PROCESSING_FAILED,
    )
    job = VideoProcessingJob.objects.create(
        training_video=video,
        status=VideoProcessingJob.Status.FAILED,
        attempt_count=1,
        next_retry_at=timezone.now() - timezone.timedelta(seconds=1),
        expires_at=timezone.now() + timezone.timedelta(hours=47),
    )
    future_video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key="training/retry-future.mp4",
        status=TrainingVideo.Status.PROCESSING_FAILED,
    )
    future_job = VideoProcessingJob.objects.create(
        training_video=future_video,
        status=VideoProcessingJob.Status.FAILED,
        attempt_count=1,
        next_retry_at=timezone.now() + timezone.timedelta(minutes=10),
        expires_at=timezone.now() + timezone.timedelta(hours=47),
    )
    VideoProcessingJob.objects.filter(pk=future_job.id).update(
        updated_at=timezone.now() - timezone.timedelta(hours=1)
    )

    with patch("apps.training.tasks.process_training_video_job.delay") as delay:
        retry_failed_video_processing_jobs()

    delay.assert_called_once_with(job.id)
    job.refresh_from_db()
    assert job.status == VideoProcessingJob.Status.QUEUED
    assert job.next_retry_at is None


@pytest.mark.django_db
def test_retry_scheduler_requeues_stale_in_progress_job(
    project_patient, active_prescription, prescription_action, settings
):
    settings.TRAINING_VIDEO_STALE_JOB_SECONDS = 60
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key="training/stale.mp4",
        status=TrainingVideo.Status.MERGING,
    )
    job = VideoProcessingJob.objects.create(
        training_video=video,
        status=VideoProcessingJob.Status.MERGING,
        expires_at=timezone.now() + timezone.timedelta(hours=47),
    )
    VideoProcessingJob.objects.filter(pk=job.id).update(
        updated_at=timezone.now() - timezone.timedelta(minutes=5)
    )

    with patch("apps.training.tasks.process_training_video_job.delay") as delay:
        retry_failed_video_processing_jobs()

    delay.assert_called_once_with(job.id)


def test_processing_task_uses_late_acknowledgement():
    assert process_training_video_job.acks_late is True
    assert process_training_video_job.reject_on_worker_lost is True


@pytest.mark.django_db
def test_expiry_task_removes_server_files_after_48_hours(
    project_patient,
    active_prescription,
    prescription_action,
    settings,
    tmp_path,
):
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key="training/expired.mp4",
        status=TrainingVideo.Status.PROCESSING_FAILED,
    )
    session_dir = settings.TRAINING_VIDEO_TEMP_ROOT / str(video.id)
    session_dir.mkdir(parents=True)
    (session_dir / "segment.mp4").write_bytes(b"segment")
    job = VideoProcessingJob.objects.create(
        training_video=video,
        status=VideoProcessingJob.Status.FAILED,
        expires_at=timezone.now() - timezone.timedelta(seconds=1),
    )

    expire_training_video_jobs()

    job.refresh_from_db()
    video.refresh_from_db()
    assert job.status == VideoProcessingJob.Status.EXPIRED
    assert video.status == TrainingVideo.Status.EXPIRED
    assert not session_dir.exists()


@pytest.mark.django_db
def test_expiry_task_does_not_clean_a_running_locked_job(
    project_patient,
    active_prescription,
    prescription_action,
    settings,
    tmp_path,
):
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key="training/running-expired.mp4",
        status=TrainingVideo.Status.MERGING,
    )
    session_dir = settings.TRAINING_VIDEO_TEMP_ROOT / str(video.id)
    session_dir.mkdir(parents=True)
    (session_dir / "segment.mp4").write_bytes(b"segment")
    job = VideoProcessingJob.objects.create(
        training_video=video,
        status=VideoProcessingJob.Status.MERGING,
        expires_at=timezone.now() - timezone.timedelta(seconds=1),
    )

    with video_job_lock(job.id) as acquired:
        assert acquired is True
        expire_training_video_jobs()

    job.refresh_from_db()
    assert job.status == VideoProcessingJob.Status.MERGING
    assert session_dir.exists()


@pytest.mark.django_db
def test_expiry_task_removes_unfinished_orphan_session_after_48_hours(
    project_patient,
    active_prescription,
    prescription_action,
    settings,
    tmp_path,
):
    settings.TRAINING_VIDEO_TEMP_ROOT = tmp_path / "training_video_temp"
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        bucket="motioncare",
        object_key="training/orphan.mp4",
        status=TrainingVideo.Status.UPLOADING,
    )
    TrainingVideo.objects.filter(pk=video.id).update(
        created_at=timezone.now() - timezone.timedelta(hours=49)
    )
    session_dir = settings.TRAINING_VIDEO_TEMP_ROOT / str(video.id)
    session_dir.mkdir(parents=True)
    (session_dir / "segment.mp4").write_bytes(b"segment")

    expire_training_video_jobs()

    video.refresh_from_db()
    assert video.status == TrainingVideo.Status.EXPIRED
    assert not session_dir.exists()
