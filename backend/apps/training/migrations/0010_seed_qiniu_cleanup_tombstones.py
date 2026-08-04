from django.conf import settings
from django.db import migrations


def seed_existing_qiniu_cleanup_tombstones(apps, schema_editor):
    TrainingVideo = apps.get_model("training", "TrainingVideo")
    VideoAssemblyJob = apps.get_model("training", "VideoAssemblyJob")
    QiniuCleanupTombstone = apps.get_model("training", "QiniuCleanupTombstone")

    jobs = {
        job.training_video_id: job
        for job in VideoAssemblyJob.objects.all().iterator()
    }
    for video in TrainingVideo.objects.all().iterator():
        job = jobs.get(video.id)
        attempt_count = job.attempt_count if job is not None else 0
        job_key = job.qiniu_object_key if job is not None else ""
        object_key = video.object_key or ""
        if attempt_count == 0 and not job_key and not object_key:
            continue

        prefix = (
            f"training-videos/attempts/{video.id}-{video.client_session_id}/attempt-"
        )
        if job is not None and job_key.startswith(prefix):
            job.qiniu_attempt_object_key = job_key
            job.save(update_fields=["qiniu_attempt_object_key"])

        canonical_key = object_key or ("" if job_key.startswith(prefix) else job_key)
        if video.status == "attached" and object_key:
            canonical_key = object_key
        QiniuCleanupTombstone.objects.update_or_create(
            attempt_key_prefix=prefix,
            defaults={
                "session_id": video.client_session_id,
                "bucket": video.bucket or settings.QINIU_BUCKET,
                "max_attempt_number": attempt_count,
                "canonical_key": canonical_key,
                "retain_canonical": (
                    video.project_patient_id is not None
                    and video.cleanup_requested_at is None
                    and video.status != "expired"
                ),
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0009_current_training_pipeline"),
    ]

    operations = [
        migrations.RunPython(
            seed_existing_qiniu_cleanup_tombstones,
            migrations.RunPython.noop,
        ),
    ]
