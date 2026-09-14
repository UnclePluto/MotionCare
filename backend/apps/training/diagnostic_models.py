from django.db import models
from django.utils import timezone


class TrainingUploadDiagnostic(models.Model):
    class Stage(models.TextChoices):
        RECORDING = "recording", "录制"
        COMPRESSION = "compression", "压缩"
        FILE_READ = "file_read", "读取文件"
        SESSION = "session", "创建会话"
        STATUS = "status", "查询状态"
        UPLOAD = "upload", "上传分片"
        FINALIZE = "finalize", "提交完成"

    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="training_upload_diagnostics",
    )
    event_id = models.UUIDField()
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    client_session_id = models.UUIDField(null=True, blank=True, db_index=True)
    # A diagnostic never owns or changes a training video. Keep the correlation
    # ID even if the independently retained video is subsequently removed.
    video_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    segment_index = models.PositiveIntegerField(null=True, blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    stage = models.CharField(max_length=16, choices=Stage.choices)
    error_code = models.CharField(max_length=64)
    message = models.CharField(max_length=500)
    network_type = models.CharField(max_length=32)
    platform = models.CharField(max_length=32)
    sdk_version = models.CharField(max_length=32)
    app_version = models.CharField(max_length=32)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project_patient", "event_id"],
                name="unique_upload_diagnostic_event_per_patient",
            )
        ]
