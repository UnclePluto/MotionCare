import re

from django.db import migrations, models


def parse_weekly_target_count(value):
    if not value:
        return 1
    match = re.search(r"\d+", str(value))
    if not match:
        return 1
    count = int(match.group(0))
    return count if count > 0 else 1


def backfill_weekly_target_count(apps, schema_editor):
    PrescriptionAction = apps.get_model("prescriptions", "PrescriptionAction")
    for action in PrescriptionAction.objects.only("id", "weekly_frequency"):
        action.weekly_target_count = parse_weekly_target_count(action.weekly_frequency)
        action.save(update_fields=["weekly_target_count"])


class Migration(migrations.Migration):

    dependencies = [
        ("prescriptions", "0008_backfill_prescription_action_duration"),
    ]

    operations = [
        migrations.AddField(
            model_name="prescriptionaction",
            name="weekly_target_count",
            field=models.PositiveIntegerField(default=1, verbose_name="每周目标次数"),
        ),
        migrations.RunPython(
            backfill_weekly_target_count, migrations.RunPython.noop
        ),
        migrations.AddConstraint(
            model_name="prescriptionaction",
            constraint=models.CheckConstraint(
                condition=models.Q(weekly_target_count__gt=0),
                name="prescription_action_weekly_target_count_gt_0",
            ),
        ),
    ]
