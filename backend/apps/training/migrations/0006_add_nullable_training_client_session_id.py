from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0005_prepare_legacy_training_pipeline"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingvideo",
            name="client_session_id",
            field=models.UUIDField(null=True, verbose_name="客户端会话 ID"),
        ),
    ]
