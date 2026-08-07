from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0012_repair_unbound_qiniu_canonical_keys"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingvideo",
            name="training_started_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="训练开始时间"),
        ),
        migrations.AddField(
            model_name="trainingvideo",
            name="training_ended_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="训练结束时间"),
        ),
    ]
