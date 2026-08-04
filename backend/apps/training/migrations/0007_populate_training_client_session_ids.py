import uuid

from django.db import migrations


def populate_client_session_ids(apps, schema_editor):
    TrainingVideo = apps.get_model("training", "TrainingVideo")
    for video in TrainingVideo.objects.filter(client_session_id__isnull=True).iterator():
        video.client_session_id = uuid.uuid4()
        video.save(update_fields=["client_session_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0006_add_nullable_training_client_session_id"),
    ]

    operations = [
        migrations.RunPython(
            populate_client_session_ids,
            migrations.RunPython.noop,
        ),
    ]
