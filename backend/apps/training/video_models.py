from django.conf import settings
from django.db import models

from apps.common.models import UserStampedModel


class TrainingVideo(UserStampedModel):
    class Status(models.TextChoices):
        UPLOADING = "uploading", "上传中"
        UPLOADED = "uploaded", "已上传"
        ATTACHED = "attached", "已绑定"
        FAILED = "failed", "失败"
        EXPIRED = "expired", "已过期"

    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="training_video_uploads",
    )
    prescription = models.ForeignKey("prescriptions.Prescription", on_delete=models.PROTECT)
    prescription_action = models.ForeignKey(
        "prescriptions.PrescriptionAction",
        on_delete=models.PROTECT,
    )
    training_record = models.OneToOneField(
        "training.TrainingRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="video",
    )
    storage_backend = models.CharField("存储后端", max_length=40, default="qiniu_kodo")
    bucket = models.CharField("空间", max_length=120)
    object_key = models.CharField("对象 Key", max_length=500, unique=True)
    object_hash = models.CharField("对象 Hash", max_length=120, blank=True)
    original_filename = models.CharField("原始文件名", max_length=255, blank=True)
    content_type = models.CharField("文件类型", max_length=120)
    size_bytes = models.PositiveBigIntegerField("文件大小")
    duration_seconds = models.PositiveIntegerField("视频时长")
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADING,
    )
    upload_token_expires_at = models.DateTimeField("上传凭证过期时间")
    uploaded_at = models.DateTimeField("上传完成时间", null=True, blank=True)
    failure_reason = models.TextField("失败原因", blank=True)


class MotionAnalysisJob(UserStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待分析"
        RUNNING = "running", "分析中"
        SUCCEEDED = "succeeded", "分析成功"
        FAILED = "failed", "分析失败"

    training_video = models.ForeignKey(
        TrainingVideo,
        on_delete=models.CASCADE,
        related_name="analysis_jobs",
    )
    training_record = models.ForeignKey(
        "training.TrainingRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="motion_analysis_jobs",
    )
    project_patient = models.ForeignKey("studies.ProjectPatient", on_delete=models.CASCADE)
    prescription_action = models.ForeignKey(
        "prescriptions.PrescriptionAction",
        on_delete=models.PROTECT,
    )
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    algorithm_name = models.CharField("算法名称", max_length=80, default="pp-tiny-pose")
    algorithm_version = models.CharField("算法版本", max_length=80, blank=True)
    rule_version = models.CharField("规则版本", max_length=80, default="shoulder-press-v1")
    total_count = models.PositiveIntegerField("总次数", null=True, blank=True)
    standard_count = models.PositiveIntegerField("标准次数", null=True, blank=True)
    nonstandard_count = models.PositiveIntegerField("不标准次数", null=True, blank=True)
    result_payload = models.JSONField("分析结果", default=dict)
    failure_reason = models.TextField("失败原因", blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_motion_analysis_jobs",
    )
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["training_video"],
                condition=models.Q(status__in=["pending", "running"]),
                name="unique_active_motion_analysis_job_per_video",
            )
        ]
