# Generated manually for motion prescription fields.

from django.db import migrations, models


def forwards(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    PrescriptionAction = apps.get_model("prescriptions", "PrescriptionAction")

    for action in ActionLibraryItem.objects.all():
        parts = []
        if getattr(action, "execution_description", ""):
            parts.append(action.execution_description)
        if getattr(action, "key_points", ""):
            parts.append(f"动作要点：{action.key_points}")
        action.instruction_text = "\n\n".join(parts)
        action.save(update_fields=["instruction_text"])

    for snapshot in PrescriptionAction.objects.all():
        snapshot.action_instruction_snapshot = getattr(
            snapshot, "execution_description_snapshot", ""
        )
        snapshot.weekly_frequency = getattr(snapshot, "frequency", "")
        snapshot.save(update_fields=["action_instruction_snapshot", "weekly_frequency"])


def backwards(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    PrescriptionAction = apps.get_model("prescriptions", "PrescriptionAction")

    for action in ActionLibraryItem.objects.all():
        instruction = action.instruction_text or ""
        marker = "\n\n动作要点："
        if marker in instruction:
            action.execution_description, action.key_points = instruction.split(marker, 1)
        else:
            action.execution_description = instruction
            action.key_points = ""
        action.save(update_fields=["execution_description", "key_points"])

    for snapshot in PrescriptionAction.objects.all():
        snapshot.execution_description_snapshot = snapshot.action_instruction_snapshot
        snapshot.frequency = snapshot.weekly_frequency
        snapshot.save(update_fields=["execution_description_snapshot", "frequency"])


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0002_prescription_project_patient_set_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="actionlibraryitem",
            name="source_key",
            field=models.CharField(
                blank=True, max_length=120, null=True, unique=True, verbose_name="动作编码"
            ),
        ),
        migrations.AddField(
            model_name="actionlibraryitem",
            name="instruction_text",
            field=models.TextField(blank=True, verbose_name="动作说明文案"),
        ),
        migrations.AddField(
            model_name="actionlibraryitem",
            name="suggested_repetitions",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="建议次数"),
        ),
        migrations.AddField(
            model_name="actionlibraryitem",
            name="video_url",
            field=models.URLField(blank=True, max_length=500, verbose_name="视频URL"),
        ),
        migrations.AddField(
            model_name="actionlibraryitem",
            name="has_ai_supervision",
            field=models.BooleanField(default=False, verbose_name="是否支持AI监督"),
        ),
        migrations.AddField(
            model_name="prescriptionaction",
            name="action_instruction_snapshot",
            field=models.TextField(blank=True, verbose_name="动作说明文案快照"),
        ),
        migrations.AddField(
            model_name="prescriptionaction",
            name="video_url_snapshot",
            field=models.URLField(blank=True, max_length=500, verbose_name="视频URL快照"),
        ),
        migrations.AddField(
            model_name="prescriptionaction",
            name="has_ai_supervision_snapshot",
            field=models.BooleanField(default=False, verbose_name="是否支持AI监督快照"),
        ),
        migrations.AddField(
            model_name="prescriptionaction",
            name="weekly_frequency",
            field=models.CharField(blank=True, max_length=80, verbose_name="每周频次"),
        ),
        migrations.AddField(
            model_name="prescriptionaction",
            name="repetitions",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="次数"),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name="actionlibraryitem", name="execution_description"),
        migrations.RemoveField(model_name="actionlibraryitem", name="key_points"),
        migrations.RemoveField(
            model_name="prescriptionaction", name="execution_description_snapshot"
        ),
        migrations.RemoveField(model_name="prescriptionaction", name="frequency"),
    ]
