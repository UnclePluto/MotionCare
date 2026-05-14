from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0006_sync_motion_action_defaults"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="actionlibraryitem",
            name="suggested_sets",
        ),
        migrations.RemoveField(
            model_name="actionlibraryitem",
            name="suggested_repetitions",
        ),
        migrations.RemoveField(
            model_name="prescriptionaction",
            name="sets",
        ),
        migrations.RemoveField(
            model_name="prescriptionaction",
            name="repetitions",
        ),
    ]
