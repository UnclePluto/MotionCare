from django.db import migrations
from django.utils import timezone


def retire_legacy_training_pipeline(apps, schema_editor):
    TrainingVideo = apps.get_model("training", "TrainingVideo")

    for video in TrainingVideo.objects.filter(training_date__isnull=True).iterator():
        video.training_date = timezone.localdate(video.created_at)
        video.save(update_fields=["training_date"])

    TrainingVideo.objects.exclude(status__in=["attached", "expired"]).update(
        status="failed",
        failure_reason="旧版视频处理会话已停止，请重新训练",
    )


def deduplicate_active_motion_analysis_jobs(apps, schema_editor):
    MotionAnalysisJob = apps.get_model("training", "MotionAnalysisJob")
    retained_video_ids = set()
    active_jobs = MotionAnalysisJob.objects.filter(
        status__in=["pending", "running"]
    ).order_by("training_video_id", "-id")

    for job in active_jobs.iterator():
        if job.training_video_id not in retained_video_ids:
            retained_video_ids.add(job.training_video_id)
            continue
        job.status = "failed"
        job.failure_reason = "升级时合并了重复的活动分析任务"
        job.save(update_fields=["status", "failure_reason"])


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0004_trainingvideo_training_date"),
    ]

    operations = [
        migrations.RunPython(
            retire_legacy_training_pipeline,
            migrations.RunPython.noop,
        ),
        migrations.RunPython(
            deduplicate_active_motion_analysis_jobs,
            migrations.RunPython.noop,
        ),
    ]
