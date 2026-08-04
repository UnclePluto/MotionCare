import uuid

import django.utils.timezone
from django.db import migrations, models


def archive_legacy_training_video_segments(apps, schema_editor):
    LegacyArchive = apps.get_model(
        "training",
        "LegacyTrainingVideoSegmentArchive",
    )
    TrainingVideoSegment = apps.get_model("training", "TrainingVideoSegment")

    archives = [
        LegacyArchive(
            source_segment_id=segment.id,
            source_training_video_id=segment.training_video_id,
            sequence_index=segment.sequence_index,
            server_file_path=segment.server_file_path,
            size_bytes=segment.size_bytes,
            object_hash=segment.object_hash,
            status=segment.status,
            uploaded_at=segment.uploaded_at,
            failure_reason=segment.failure_reason,
        )
        for segment in TrainingVideoSegment.objects.all().iterator()
    ]
    LegacyArchive.objects.bulk_create(archives, ignore_conflicts=True)


def populate_residual_client_session_ids(apps, schema_editor):
    TrainingVideo = apps.get_model("training", "TrainingVideo")
    for video in TrainingVideo.objects.filter(client_session_id__isnull=True).iterator():
        video.client_session_id = uuid.uuid4()
        video.save(update_fields=["client_session_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0007_populate_training_client_session_ids"),
    ]

    operations = [
        migrations.CreateModel(
            name="LegacyTrainingVideoSegmentArchive",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "source_segment_id",
                    models.PositiveBigIntegerField(
                        unique=True,
                        verbose_name="旧分片 ID",
                    ),
                ),
                (
                    "source_training_video_id",
                    models.PositiveBigIntegerField(
                        db_index=True,
                        verbose_name="旧视频 ID",
                    ),
                ),
                (
                    "sequence_index",
                    models.PositiveIntegerField(verbose_name="旧分片序号"),
                ),
                (
                    "server_file_path",
                    models.CharField(
                        max_length=500,
                        verbose_name="旧服务端临时文件",
                    ),
                ),
                (
                    "size_bytes",
                    models.PositiveBigIntegerField(verbose_name="旧分片大小"),
                ),
                (
                    "object_hash",
                    models.CharField(
                        max_length=64,
                        verbose_name="旧文件 SHA-256",
                    ),
                ),
                (
                    "status",
                    models.CharField(max_length=20, verbose_name="旧分片状态"),
                ),
                (
                    "uploaded_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="旧上传完成时间",
                    ),
                ),
                (
                    "failure_reason",
                    models.TextField(blank=True, verbose_name="旧失败原因"),
                ),
                (
                    "archived_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        verbose_name="归档时间",
                    ),
                ),
            ],
        ),
        migrations.RunSQL(
            sql="LOCK TABLE training_trainingvideo IN ACCESS EXCLUSIVE MODE",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(
            populate_residual_client_session_ids,
            migrations.RunPython.noop,
        ),
        migrations.RunSQL(
            sql="SET CONSTRAINTS ALL IMMEDIATE",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(
            archive_legacy_training_video_segments,
            migrations.RunPython.noop,
        ),
        migrations.DeleteModel(
            name="VideoProcessingJob",
        ),
        migrations.DeleteModel(
            name="TrainingVideoSegment",
        ),
        migrations.RemoveField(
            model_name="trainingvideo",
            name="processing_expires_at",
        ),
        migrations.RemoveField(
            model_name="trainingvideo",
            name="recording_finished_at",
        ),
        migrations.RemoveField(
            model_name="trainingvideo",
            name="segment_count",
        ),
        migrations.AlterField(
            model_name="trainingvideo",
            name="client_session_id",
            field=models.UUIDField(
                default=uuid.uuid4,
                verbose_name="客户端会话 ID",
            ),
        ),
        migrations.AlterField(
            model_name="trainingvideo",
            name="training_date",
            field=models.DateField(
                default=django.utils.timezone.localdate,
                verbose_name="训练日期",
            ),
        ),
    ]
