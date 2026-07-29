from django.db import migrations


def _canonical_key(video, prescription_project_patient_ids):
    project_patient_id = video.project_patient_id
    if project_patient_id is None:
        project_patient_id = prescription_project_patient_ids.get(video.prescription_id)
    return (
        f"training-videos/{project_patient_id}/"
        f"{video.training_date:%Y/%m/%d}/{video.client_session_id}.mp4"
    )


def repair_qiniu_canonical_keys(apps, schema_editor):
    Prescription = apps.get_model("prescriptions", "Prescription")
    TrainingVideo = apps.get_model("training", "TrainingVideo")
    VideoAssemblyJob = apps.get_model("training", "VideoAssemblyJob")
    QiniuCleanupTombstone = apps.get_model("training", "QiniuCleanupTombstone")

    prescription_project_patient_ids = dict(
        Prescription.objects.values_list("id", "project_patient_id")
    )
    videos = {
        video.id: video
        for video in TrainingVideo.objects.all().iterator()
    }
    for job in VideoAssemblyJob.objects.all().iterator():
        video = videos[job.training_video_id]
        prefix = (
            f"training-videos/attempts/{video.id}-{video.client_session_id}/attempt-"
        )
        previous_key = job.qiniu_object_key or ""
        update_fields = []

        if previous_key.startswith(prefix):
            job.qiniu_attempt_object_key = previous_key
            update_fields.append("qiniu_attempt_object_key")

        if video.status == "attached" and video.object_key:
            canonical_key = video.object_key
        elif previous_key.startswith(prefix) or not previous_key:
            canonical_key = _canonical_key(video, prescription_project_patient_ids)
        else:
            canonical_key = previous_key

        if job.qiniu_object_key != canonical_key:
            job.qiniu_object_key = canonical_key
            update_fields.append("qiniu_object_key")
        if update_fields:
            job.save(update_fields=list(dict.fromkeys(update_fields)))

        retain_canonical = (
            video.status == "attached"
            or (
                video.project_patient_id is not None
                and video.cleanup_requested_at is None
                and video.status != "expired"
            )
        )
        QiniuCleanupTombstone.objects.filter(attempt_key_prefix=prefix).update(
            canonical_key=canonical_key,
            retain_canonical=retain_canonical,
            max_attempt_number=max(job.attempt_count, 0),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0008_qiniucleanuptombstone_and_more"),
    ]

    operations = [
        migrations.RunPython(
            repair_qiniu_canonical_keys,
            migrations.RunPython.noop,
        ),
    ]
