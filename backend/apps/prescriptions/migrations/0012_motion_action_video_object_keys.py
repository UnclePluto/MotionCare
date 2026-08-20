from django.db import migrations, models

MOTION_ACTION_VIDEO_OBJECT_KEYS_V1 = {
    "motion-aerobic-high-knee": (
        "motion-action-videos/v1/motion-aerobic-high-knee.mp4"
    ),
    "motion-balance-sit-stand": (
        "motion-action-videos/v1/motion-balance-sit-stand.mp4"
    ),
    "motion-resistance-row": (
        "motion-action-videos/v1/motion-resistance-row.mp4"
    ),
    "motion-resistance-leg-kickback": (
        "motion-action-videos/v1/motion-resistance-leg-kickback.mp4"
    ),
    "motion-resistance-shoulder-press": (
        "motion-action-videos/v1/motion-resistance-shoulder-press.mp4"
    ),
}


def backfill_motion_action_video_keys(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    PrescriptionAction = apps.get_model("prescriptions", "PrescriptionAction")

    for source_key, object_key in MOTION_ACTION_VIDEO_OBJECT_KEYS_V1.items():
        ActionLibraryItem.objects.filter(source_key=source_key).update(
            video_object_key=object_key,
            video_url="",
        )
        PrescriptionAction.objects.filter(
            action_library_item__source_key=source_key
        ).update(
            video_object_key_snapshot=object_key,
            video_url_snapshot="",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0011_prune_unofficial_action_library_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="actionlibraryitem",
            name="video_object_key",
            field=models.CharField(blank=True, max_length=500, verbose_name="视频对象键"),
        ),
        migrations.AddField(
            model_name="prescriptionaction",
            name="video_object_key_snapshot",
            field=models.CharField(blank=True, max_length=500, verbose_name="视频对象键快照"),
        ),
        migrations.RunPython(backfill_motion_action_video_keys, migrations.RunPython.noop),
    ]
