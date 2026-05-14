from django.db import migrations


def backfill_prescription_action_duration(apps, schema_editor):
    PrescriptionAction = apps.get_model("prescriptions", "PrescriptionAction")
    actions = (
        PrescriptionAction.objects.filter(duration_minutes__isnull=True)
        .select_related("action_library_item")
        .only("id", "duration_minutes", "action_library_item__suggested_duration_minutes")
    )
    for action in actions.iterator():
        suggested_duration = action.action_library_item.suggested_duration_minutes
        if suggested_duration:
            action.duration_minutes = suggested_duration
            action.save(update_fields=["duration_minutes"])


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0007_remove_motion_count_fields"),
    ]

    operations = [
        migrations.RunPython(backfill_prescription_action_duration, migrations.RunPython.noop),
    ]
