from django.db import migrations, models


def stop_legacy_direct_upload_sessions(apps, schema_editor):
    TrainingVideo = apps.get_model("training", "TrainingVideo")
    TrainingVideo.objects.filter(status__in=["uploading", "uploaded"]).update(
        status="failed",
        failure_reason="旧直传会话已停止，请重新训练",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0004_segmented_training_video"),
    ]

    operations = [
        migrations.RunPython(
            stop_legacy_direct_upload_sessions,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="trainingvideo",
            name="upload_token_expires_at",
        ),
        migrations.AlterField(
            model_name="trainingvideo",
            name="status",
            field=models.CharField(
                choices=[
                    ("recording", "录制中"),
                    ("uploading_segments", "分段上传中"),
                    ("queued", "等待合并"),
                    ("assembling", "合并中"),
                    ("uploading_qiniu", "上传七牛中"),
                    ("attached", "已绑定"),
                    ("failed", "失败"),
                    ("expired", "已过期"),
                ],
                default="recording",
                max_length=20,
                verbose_name="状态",
            ),
        ),
    ]
