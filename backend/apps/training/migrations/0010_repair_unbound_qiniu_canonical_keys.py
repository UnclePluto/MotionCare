from django.db import migrations


def _attempt_key_prefix(video):
    return f"training-videos/attempts/{video.id}-{video.client_session_id}/attempt-"


def _is_fabricated_canonical_key(key):
    return key.startswith("training-videos/None/")


def _canonical_key(video, prescription_project_patient_ids):
    project_patient_id = video.project_patient_id
    if project_patient_id is None:
        project_patient_id = prescription_project_patient_ids.get(video.prescription_id)
    if project_patient_id is None:
        return ""
    return (
        f"training-videos/{project_patient_id}/"
        f"{video.training_date:%Y/%m/%d}/{video.client_session_id}.mp4"
    )


def repair_unbound_qiniu_canonical_keys(apps, schema_editor):
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
        prefix = _attempt_key_prefix(video)
        previous_key = job.qiniu_object_key or ""
        attempt_key = job.qiniu_attempt_object_key or ""

        if previous_key.startswith(prefix):
            attempt_key = previous_key

        if video.object_key:
            canonical_key = video.object_key
        elif previous_key and not previous_key.startswith(prefix) and not _is_fabricated_canonical_key(
            previous_key
        ):
            canonical_key = previous_key
        else:
            canonical_key = _canonical_key(video, prescription_project_patient_ids)

        update_fields = []
        if job.qiniu_attempt_object_key != attempt_key:
            job.qiniu_attempt_object_key = attempt_key
            update_fields.append("qiniu_attempt_object_key")
        if job.qiniu_object_key != canonical_key:
            job.qiniu_object_key = canonical_key
            update_fields.append("qiniu_object_key")
        if update_fields:
            job.save(update_fields=update_fields)

        retain_canonical = (
            video.cleanup_requested_at is None
            and (
                video.status == "attached"
                or (
                    video.project_patient_id is not None
                    and video.status != "expired"
                )
            )
        )
        tombstone = QiniuCleanupTombstone.objects.filter(
            attempt_key_prefix=prefix
        ).first()
        if tombstone is None:
            continue
        max_attempt_number = max(
            tombstone.max_attempt_number,
            job.attempt_count,
        )
        if (
            tombstone.canonical_key != canonical_key
            or tombstone.retain_canonical != retain_canonical
            or tombstone.max_attempt_number != max_attempt_number
        ):
            tombstone.canonical_key = canonical_key
            tombstone.retain_canonical = retain_canonical
            tombstone.max_attempt_number = max_attempt_number
            tombstone.save(
                update_fields=[
                    "canonical_key",
                    "retain_canonical",
                    "max_attempt_number",
                    "updated_at",
                ]
            )


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0009_repair_qiniu_canonical_keys"),
    ]

    operations = [
        migrations.RunPython(
            repair_unbound_qiniu_canonical_keys,
            migrations.RunPython.noop,
        ),
    ]
