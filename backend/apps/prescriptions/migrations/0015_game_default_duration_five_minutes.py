from django.db import migrations


def update_game_defaults(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    ActionLibraryItem.objects.using(schema_editor.connection.alias).filter(
        internal_type="game",
    ).update(suggested_duration_minutes=5)


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0014_counted_motion_doses"),
    ]

    operations = [
        migrations.RunPython(update_game_defaults, migrations.RunPython.noop),
    ]
