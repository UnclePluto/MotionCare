from celery import shared_task
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from .analysis import analyze_shoulder_press_keypoints, extract_keypoint_frames
from .models import MotionAnalysisJob, TrainingVideo, VideoProcessingJob
from .video_services import get_analysis_video_input


@shared_task(acks_late=True, reject_on_worker_lost=True)
def process_training_video_job(job_id):
    from .video_processing import process_video_job

    return process_video_job(job_id)


@shared_task
def retry_failed_video_processing_jobs():
    now = timezone.now()
    stale_before = now - timezone.timedelta(
        seconds=settings.TRAINING_VIDEO_STALE_JOB_SECONDS
    )
    job_ids = []
    with transaction.atomic():
        jobs = list(
            VideoProcessingJob.objects.select_for_update(skip_locked=True)
            .filter(
                expires_at__gt=now,
                attempt_count__lt=models.F("max_attempts"),
            )
            .filter(
                models.Q(
                    status=VideoProcessingJob.Status.FAILED,
                    next_retry_at__lte=now,
                )
                | models.Q(
                    status__in=[
                        VideoProcessingJob.Status.QUEUED,
                        VideoProcessingJob.Status.VALIDATING_SEGMENTS,
                        VideoProcessingJob.Status.MERGING,
                        VideoProcessingJob.Status.VERIFYING_MERGE,
                        VideoProcessingJob.Status.UPLOADING_QINIU,
                        VideoProcessingJob.Status.VERIFYING_QINIU,
                        VideoProcessingJob.Status.CLEANING,
                    ],
                    updated_at__lte=stale_before,
                )
            )
            .exclude(
                status__in=[
                    VideoProcessingJob.Status.SUCCEEDED,
                    VideoProcessingJob.Status.EXPIRED,
                ]
            )
        )
        for job in jobs:
            if job.status == VideoProcessingJob.Status.FAILED:
                job.status = VideoProcessingJob.Status.QUEUED
                job.next_retry_at = None
                job.save(update_fields=["status", "next_retry_at", "updated_at"])
            job_ids.append(job.id)
    for job_id in job_ids:
        try:
            process_training_video_job.delay(job_id)
        except Exception as exc:
            retry_at = timezone.now() + timezone.timedelta(
                seconds=settings.TRAINING_VIDEO_RETRY_BASE_SECONDS
            )
            VideoProcessingJob.objects.filter(pk=job_id).update(
                status=VideoProcessingJob.Status.FAILED,
                next_retry_at=retry_at,
                failure_reason=f"视频任务重投失败：{str(exc)[:1800]}",
            )
    return len(job_ids)


@shared_task
def expire_training_video_jobs():
    from .video_processing import _cleanup_server_video_files, video_job_lock

    now = timezone.now()
    expired_count = 0
    job_ids = list(
        VideoProcessingJob.objects.filter(expires_at__lte=now)
        .exclude(
            status__in=[
                VideoProcessingJob.Status.SUCCEEDED,
                VideoProcessingJob.Status.EXPIRED,
            ]
        )
        .values_list("id", flat=True)
    )
    for job_id in job_ids:
        with video_job_lock(job_id) as acquired:
            if not acquired:
                continue
            with transaction.atomic():
                job = (
                    VideoProcessingJob.objects.select_for_update()
                    .select_related("training_video")
                    .get(pk=job_id)
                )
                if job.status in {
                    VideoProcessingJob.Status.SUCCEEDED,
                    VideoProcessingJob.Status.EXPIRED,
                }:
                    continue
                _cleanup_server_video_files(job.training_video_id)
                job.status = VideoProcessingJob.Status.EXPIRED
                job.current_stage = VideoProcessingJob.Status.EXPIRED
                job.next_retry_at = None
                job.finished_at = now
                job.save(
                    update_fields=[
                        "status",
                        "current_stage",
                        "next_retry_at",
                        "finished_at",
                        "updated_at",
                    ]
                )
                job.training_video.status = TrainingVideo.Status.EXPIRED
                job.training_video.failure_reason = "视频处理超过 48 小时，临时文件已清理"
                job.training_video.save(
                    update_fields=["status", "failure_reason", "updated_at"]
                )
                expired_count += 1
    stale_before = now - timezone.timedelta(
        hours=settings.TRAINING_VIDEO_PROCESSING_RETENTION_HOURS
    )
    orphan_video_ids = list(
        TrainingVideo.objects.filter(
            processing_job__isnull=True,
            status__in=[
                TrainingVideo.Status.RECORDING,
                TrainingVideo.Status.UPLOADING,
            ],
            created_at__lte=stale_before,
        ).values_list("id", flat=True)
    )
    for video_id in orphan_video_ids:
        with transaction.atomic():
            video = TrainingVideo.objects.select_for_update().get(pk=video_id)
            if video.status not in {
                TrainingVideo.Status.RECORDING,
                TrainingVideo.Status.UPLOADING,
            }:
                continue
            _cleanup_server_video_files(video.id)
            video.status = TrainingVideo.Status.EXPIRED
            video.failure_reason = "录像会话超过 48 小时未结束，临时文件已清理"
            video.save(update_fields=["status", "failure_reason", "updated_at"])
            expired_count += 1
    return expired_count


@shared_task
def run_motion_analysis_job(job_id):
    with transaction.atomic():
        job = MotionAnalysisJob.objects.select_for_update().get(pk=job_id)
        if job.status != MotionAnalysisJob.Status.PENDING:
            return job.id
        job.status = MotionAnalysisJob.Status.RUNNING
        job.started_at = timezone.now()
        job.failure_reason = ""
        job.save(update_fields=["status", "started_at", "failure_reason", "updated_at"])
    job = MotionAnalysisJob.objects.select_related("training_video").get(pk=job_id)
    try:
        video_input = get_analysis_video_input(job.training_video)
        frames, algorithm_version = extract_keypoint_frames(video_input)
        if not frames:
            raise RuntimeError("PP-TinyPose 未识别到人体关键点")
        result = analyze_shoulder_press_keypoints(frames)
        job.status = MotionAnalysisJob.Status.SUCCEEDED
        job.algorithm_version = algorithm_version
        job.total_count = result["total_count"]
        job.standard_count = result["standard_count"]
        job.nonstandard_count = result["nonstandard_count"]
        job.result_payload = result
    except Exception as exc:
        job.status = MotionAnalysisJob.Status.FAILED
        job.failure_reason = str(exc)[:2000]
    job.finished_at = timezone.now()
    job.save(
        update_fields=[
            "status",
            "algorithm_version",
            "total_count",
            "standard_count",
            "nonstandard_count",
            "result_payload",
            "failure_reason",
            "finished_at",
            "updated_at",
        ]
    )
    return job.id
