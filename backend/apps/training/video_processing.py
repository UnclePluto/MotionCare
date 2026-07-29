import hashlib
import json
import math
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

import fcntl

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    TrainingRecord,
    TrainingVideo,
    TrainingVideoSegment,
    VideoProcessingJob,
)
from .qiniu import QiniuStorageClient


class QiniuObjectConflictError(RuntimeError):
    pass


@contextmanager
def video_job_lock(job_id):
    lock_directory = Path(settings.TRAINING_VIDEO_TEMP_ROOT) / ".job-locks"
    lock_directory.mkdir(parents=True, exist_ok=True)
    lock_file = (lock_directory / f"{job_id}.lock").open("a+")
    acquired = False
    try:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            pass
        yield acquired
    finally:
        if acquired:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def _concat_path(path):
    return str(path).replace("'", "'\\''")


def merge_video_segments(segment_paths, output_path, *, command_runner=subprocess.run):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_path = output_path.parent / "concat.txt"
    concat_path.write_text(
        "".join(f"file '{_concat_path(Path(path))}'\n" for path in segment_paths),
        encoding="utf-8",
    )
    base = [
        settings.TRAINING_VIDEO_FFMPEG_COMMAND,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
    ]
    common = {
        "check": True,
        "capture_output": True,
        "text": True,
        "timeout": settings.TRAINING_VIDEO_PROCESS_TIMEOUT_SECONDS,
    }
    try:
        command_runner(
            [*base, "-c", "copy", "-movflags", "+faststart", str(output_path)],
            **common,
        )
    except subprocess.CalledProcessError:
        output_path.unlink(missing_ok=True)
        command_runner(
            [
                *base,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            **common,
        )
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg 未生成有效的合并视频")


def probe_video(file_path, *, command_runner=subprocess.run):
    result = command_runner(
        [
            settings.TRAINING_VIDEO_FFPROBE_COMMAND,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type",
            "-of",
            "json",
            str(file_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=settings.TRAINING_VIDEO_PROCESS_TIMEOUT_SECONDS,
    )
    payload = json.loads(result.stdout)
    if not any(stream.get("codec_type") == "video" for stream in payload.get("streams", [])):
        raise RuntimeError("合并结果不包含视频流")
    duration = float(payload.get("format", {}).get("duration") or 0)
    size = int(payload.get("format", {}).get("size") or Path(file_path).stat().st_size)
    if duration <= 0 or size <= 0:
        raise RuntimeError("合并结果时长或大小无效")
    return {"duration_seconds": duration, "size_bytes": size}


def ensure_qiniu_final_object(*, client, bucket, key, file_path):
    file_path = Path(file_path)
    expected_hash = client.file_hash(file_path)
    expected_size = file_path.stat().st_size
    existing = client.stat_object(bucket, key)
    if existing is not None:
        if existing.get("hash") != expected_hash or existing.get("size") != expected_size:
            raise QiniuObjectConflictError("七牛固定 key 已存在不匹配对象，禁止覆盖")
        return existing
    client.upload_file(bucket, key, file_path)
    verified = client.stat_object(bucket, key)
    if verified is None:
        raise RuntimeError("七牛完整视频上传后校验失败：远端对象不存在")
    if verified.get("hash") != expected_hash or verified.get("size") != expected_size:
        raise RuntimeError("七牛完整视频上传后校验失败")
    return verified


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _set_stage(job_id, status, progress_percent):
    now = timezone.now()
    with transaction.atomic():
        job = VideoProcessingJob.objects.select_for_update().select_related(
            "training_video"
        ).get(pk=job_id)
        job.status = status
        job.current_stage = status
        job.progress_percent = progress_percent
        if job.started_at is None:
            job.started_at = now
        job.failure_reason = ""
        job.next_retry_at = None
        job.save(
            update_fields=[
                "status",
                "current_stage",
                "progress_percent",
                "started_at",
                "failure_reason",
                "next_retry_at",
                "updated_at",
            ]
        )
        video_status = getattr(TrainingVideo.Status, status.upper(), None)
        if video_status:
            job.training_video.status = video_status
            job.training_video.save(update_fields=["status", "updated_at"])


def _validate_segments(video):
    segments = list(
        video.segments.filter(status=TrainingVideoSegment.Status.UPLOADED).order_by(
            "sequence_index"
        )
    )
    if len(segments) != video.segment_count:
        raise RuntimeError("服务端训练视频分片数量不完整")
    for expected_index, segment in enumerate(segments):
        if segment.sequence_index != expected_index:
            raise RuntimeError("服务端训练视频分片序号不连续")
        path = Path(segment.server_file_path)
        if not path.is_file():
            raise RuntimeError(f"训练视频分片 {expected_index} 不存在")
        if _sha256_file(path) != segment.object_hash:
            raise RuntimeError(f"训练视频分片 {expected_index} 校验失败")
    return segments


def _bind_training_record(job_id, qiniu_object):
    with transaction.atomic():
        job = VideoProcessingJob.objects.select_for_update().select_related(
            "training_video__project_patient",
            "training_video__prescription",
            "training_video__prescription_action",
        ).get(pk=job_id)
        video = job.training_video
        if video.training_record_id is None:
            record = TrainingRecord.objects.create(
                project_patient=video.project_patient,
                prescription=video.prescription,
                prescription_action=video.prescription_action,
                training_date=video.training_date,
                status=TrainingRecord.Status.COMPLETED,
                actual_duration_minutes=max(1, math.ceil(video.duration_seconds / 60)),
                form_data={
                    "video_id": video.id,
                    "video_object_key": video.object_key,
                },
                note="小程序肩部推举录像跟练",
            )
            video.training_record = record
        video.object_hash = qiniu_object["hash"]
        video.size_bytes = qiniu_object["size"]
        video.uploaded_at = timezone.now()
        video.status = TrainingVideo.Status.CLEANING
        video.save(
            update_fields=[
                "training_record",
                "object_hash",
                "size_bytes",
                "uploaded_at",
                "status",
                "updated_at",
            ]
        )


def _cleanup_server_video_files(video_id):
    root = Path(settings.TRAINING_VIDEO_TEMP_ROOT).resolve()
    session_dir = (root / str(video_id)).resolve()
    if session_dir.parent != root:
        raise RuntimeError("训练视频临时目录越界")
    if session_dir.exists():
        shutil.rmtree(session_dir)


def _mark_succeeded(job_id):
    with transaction.atomic():
        job = VideoProcessingJob.objects.select_for_update().select_related(
            "training_video"
        ).get(pk=job_id)
        job.status = VideoProcessingJob.Status.SUCCEEDED
        job.current_stage = VideoProcessingJob.Status.SUCCEEDED
        job.progress_percent = 100
        job.finished_at = timezone.now()
        job.failure_reason = ""
        job.next_retry_at = None
        job.save(
            update_fields=[
                "status",
                "current_stage",
                "progress_percent",
                "finished_at",
                "failure_reason",
                "next_retry_at",
                "updated_at",
            ]
        )
        job.training_video.status = TrainingVideo.Status.ATTACHED
        job.training_video.failure_reason = ""
        job.training_video.save(
            update_fields=["status", "failure_reason", "updated_at"]
        )


def _mark_failed(job_id, error):
    with transaction.atomic():
        job = VideoProcessingJob.objects.select_for_update().select_related(
            "training_video"
        ).get(pk=job_id)
        job.status = VideoProcessingJob.Status.FAILED
        job.attempt_count += 1
        job.failure_reason = str(error)[:2000]
        delay_seconds = min(
            settings.TRAINING_VIDEO_RETRY_BASE_SECONDS * (2 ** (job.attempt_count - 1)),
            settings.TRAINING_VIDEO_RETRY_MAX_SECONDS,
        )
        candidate_retry_at = timezone.now() + timezone.timedelta(seconds=delay_seconds)
        if job.attempt_count < job.max_attempts and candidate_retry_at < job.expires_at:
            job.next_retry_at = candidate_retry_at
        else:
            job.next_retry_at = None
        job.save(
            update_fields=[
                "status",
                "attempt_count",
                "failure_reason",
                "next_retry_at",
                "updated_at",
            ]
        )
        job.training_video.status = TrainingVideo.Status.PROCESSING_FAILED
        job.training_video.failure_reason = job.failure_reason
        job.training_video.save(
            update_fields=["status", "failure_reason", "updated_at"]
        )


def _process_video_job_locked(job_id, *, qiniu_client=None):
    job = VideoProcessingJob.objects.select_related("training_video").get(pk=job_id)
    if job.status in {VideoProcessingJob.Status.SUCCEEDED, VideoProcessingJob.Status.EXPIRED}:
        return job_id
    video = job.training_video
    try:
        if video.training_record_id and video.object_hash:
            _set_stage(job_id, VideoProcessingJob.Status.CLEANING, 95)
            _cleanup_server_video_files(video.id)
            _mark_succeeded(job_id)
            return job_id

        _set_stage(job_id, VideoProcessingJob.Status.VALIDATING_SEGMENTS, 10)
        video.refresh_from_db()
        segments = _validate_segments(video)
        session_dir = Path(settings.TRAINING_VIDEO_TEMP_ROOT) / str(video.id)
        processing_dir = session_dir / "processing"
        processing_dir.mkdir(parents=True, exist_ok=True)
        output_path = processing_dir / "merged.mp4"

        _set_stage(job_id, VideoProcessingJob.Status.MERGING, 30)
        merge_video_segments(
            [Path(segment.server_file_path) for segment in segments], output_path
        )
        _set_stage(job_id, VideoProcessingJob.Status.VERIFYING_MERGE, 55)
        probe = probe_video(output_path)
        expected_duration = sum(segment.duration_seconds for segment in segments)
        allowed_error = max(2, len(segments))
        if abs(probe["duration_seconds"] - expected_duration) > allowed_error:
            raise RuntimeError("合并视频时长与训练分片总时长不一致")

        _set_stage(job_id, VideoProcessingJob.Status.UPLOADING_QINIU, 70)
        client = qiniu_client or QiniuStorageClient()
        qiniu_object = ensure_qiniu_final_object(
            client=client,
            bucket=video.bucket,
            key=video.object_key,
            file_path=output_path,
        )
        _set_stage(job_id, VideoProcessingJob.Status.VERIFYING_QINIU, 85)
        _bind_training_record(job_id, qiniu_object)
        _set_stage(job_id, VideoProcessingJob.Status.CLEANING, 95)
        _cleanup_server_video_files(video.id)
        _mark_succeeded(job_id)
    except Exception as exc:
        _mark_failed(job_id, exc)
    return job_id


def process_video_job(job_id, *, qiniu_client=None):
    with video_job_lock(job_id) as acquired:
        if not acquired:
            return job_id
        return _process_video_job_locked(job_id, qiniu_client=qiniu_client)
