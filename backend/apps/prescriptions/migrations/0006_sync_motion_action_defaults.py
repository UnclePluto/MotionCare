from django.db import migrations, models


MOTION_ACTION_DEFAULTS = {
    "motion-aerobic-high-knee": {
        "suggested_frequency": "3 次/周",
        "suggested_duration_minutes": 20,
    },
    "motion-balance-sit-stand": {
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 15,
    },
    "motion-resistance-row": {
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 10,
    },
    "motion-resistance-leg-kickback": {
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 10,
    },
    "motion-resistance-shoulder-press": {
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 10,
    },
}


def sync_motion_action_defaults(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    for source_key, defaults in MOTION_ACTION_DEFAULTS.items():
        ActionLibraryItem.objects.filter(source_key=source_key).update(**defaults)


def fill_existing_archived_at(apps, schema_editor):
    Prescription = apps.get_model("prescriptions", "Prescription")
    Prescription.objects.filter(
        status__in=["archived", "terminated"],
        archived_at__isnull=True,
    ).update(archived_at=models.F("updated_at"))


def sync_data(apps, schema_editor):
    sync_motion_action_defaults(apps, schema_editor)
    fill_existing_archived_at(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0005_prescription_archived_at"),
    ]

    operations = [
        migrations.RunPython(sync_data, migrations.RunPython.noop),
    ]
