from django.db import migrations


HIGH_KNEE_SOURCE_KEY = "motion-aerobic-high-knee"


def disable_high_knee_ai_supervision(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    PrescriptionAction = apps.get_model("prescriptions", "PrescriptionAction")
    alias = schema_editor.connection.alias
    ActionLibraryItem.objects.using(alias).filter(
        source_key=HIGH_KNEE_SOURCE_KEY
    ).update(has_ai_supervision=False)
    PrescriptionAction.objects.using(alias).filter(
        action_library_item__source_key=HIGH_KNEE_SOURCE_KEY
    ).update(has_ai_supervision_snapshot=False)


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0012_motion_action_video_object_keys"),
    ]

    operations = [
        migrations.RunPython(
            disable_high_knee_ai_supervision,
            migrations.RunPython.noop,
        ),
    ]
