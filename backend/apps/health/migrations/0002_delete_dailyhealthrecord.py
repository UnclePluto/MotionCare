from django.db import migrations


def assert_no_manual_health_records(apps, schema_editor):
    DailyHealthRecord = apps.get_model("health", "DailyHealthRecord")
    if DailyHealthRecord.objects.exists():
        raise RuntimeError("检测到手工健康数据，停止删除；请先确认归档策略")


class Migration(migrations.Migration):
    dependencies = [
        ("health", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            assert_no_manual_health_records,
            migrations.RunPython.noop,
        ),
        migrations.DeleteModel(
            name="DailyHealthRecord",
        ),
    ]
