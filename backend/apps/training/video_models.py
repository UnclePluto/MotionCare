import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import UserStampedModel


class TrainingVideo(UserStampedModel):
    class CleanupStatus(models.TextChoices):
        NONE = "", "无需清理"
        PENDING = "pending", "待清理"
        RUNNING = "running", "清理中"
        FAILED = "failed", "清理失败"

    class Status(models.TextChoices):
        RECORDING = "recording", "录制中"
        UPLOADING_SEGMENTS = "uploading_segments", "分段上传中"
        QUEUED = "queued", "等待合并"
        ASSEMBLING = "assembling", "合并中"
        UPLOADING_QINIU = "uploading_qiniu", "上传七牛中"
        ATTACHED = "attached", "已绑定"
        FAILED = "failed", "失败"
        EXPIRED = "expired", "已过期"

    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
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
    client_session_id = models.UUIDField("客户端会话 ID", default=uuid.uuid4)
    training_date = models.DateField("训练日期", default=timezone.localdate)
    note = models.TextField("备注", blank=True)
    expected_duration_seconds = models.PositiveIntegerField("计划时长", null=True, blank=True)
    actual_duration_seconds = models.PositiveIntegerField("实际时长", null=True, blank=True)
    expected_segment_count = models.PositiveIntegerField("计划分段数", null=True, blank=True)
    uploaded_segment_count = models.PositiveIntegerField("已上传分段数", default=0)
    finalized_at = models.DateTimeField("提交完成时间", null=True, blank=True)
    storage_backend = models.CharField("存储后端", max_length=40, default="qiniu_kodo")
    bucket = models.CharField("空间", max_length=120, blank=True, default="")
    object_key = models.CharField("对象 Key", max_length=500, unique=True, null=True, blank=True)
    object_hash = models.CharField("对象 Hash", max_length=120, blank=True)
    original_filename = models.CharField("原始文件名", max_length=255, blank=True)
    content_type = models.CharField("文件类型", max_length=120, default="video/mp4")
    size_bytes = models.PositiveBigIntegerField("文件大小", default=0)
    duration_seconds = models.PositiveIntegerField("视频时长", default=0)
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.RECORDING,
    )
    uploaded_at = models.DateTimeField("上传完成时间", null=True, blank=True)
    failure_reason = models.TextField("失败原因", blank=True)
    cleanup_status = models.CharField(
        "解绑清理状态",
        max_length=20,
        choices=CleanupStatus.choices,
        default=CleanupStatus.NONE,
        blank=True,
    )
    cleanup_requested_at = models.DateTimeField("解绑清理请求时间", null=True, blank=True)
    cleanup_heartbeat_at = models.DateTimeField("解绑清理心跳时间", null=True, blank=True)
    cleanup_attempt_count = models.PositiveIntegerField("解绑清理尝试次数", default=0)
    cleanup_error = models.TextField("解绑清理失败原因", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project_patient", "client_session_id"],
                name="unique_training_video_client_session_per_patient",
            )
        ]


class TrainingVideoSegment(UserStampedModel):
    class Status(models.TextChoices):
        UPLOADING = "uploading", "上传中"
        UPLOADED = "uploaded", "已上传"
        DELETED = "deleted", "已删除"
        FAILED = "failed", "失败"

    training_video = models.ForeignKey(
        TrainingVideo,
        on_delete=models.CASCADE,
        related_name="segments",
    )
    index = models.PositiveIntegerField("分段序号")
    duration_ms = models.PositiveIntegerField("分段时长毫秒")
    size_bytes = models.PositiveBigIntegerField("分段大小")
    sha256 = models.CharField("SHA-256", max_length=64, blank=True)
    relative_path = models.CharField("临时相对路径", max_length=500, blank=True)
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADING,
    )
    uploaded_at = models.DateTimeField("上传完成时间", null=True, blank=True)
    failure_reason = models.TextField("失败原因", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["training_video", "index"],
                name="unique_training_video_segment_index",
            )
        ]


class VideoAssemblyJob(UserStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        RUNNING = "running", "处理中"
        SUCCEEDED = "succeeded", "成功"
        FAILED = "failed", "失败"

    class CleanupStatus(models.TextChoices):
        PENDING = "pending", "待清理"
        SUCCEEDED = "succeeded", "清理成功"
        FAILED = "failed", "清理失败"

    training_video = models.OneToOneField(
        TrainingVideo,
        on_delete=models.CASCADE,
        related_name="assembly_job",
    )
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempt_count = models.PositiveIntegerField("尝试次数", default=0)
    output_relative_path = models.CharField("输出相对路径", max_length=500, blank=True)
    qiniu_object_key = models.CharField("七牛对象 Key", max_length=500, blank=True)
    qiniu_object_hash = models.CharField("七牛对象 Hash", max_length=120, blank=True)
    qiniu_upload_deadline_at = models.DateTimeField(
        "七牛上传截止时间",
        null=True,
        blank=True,
    )
    cleanup_status = models.CharField(
        "清理状态",
        max_length=20,
        choices=CleanupStatus.choices,
        default=CleanupStatus.PENDING,
    )
    cleanup_attempt_count = models.PositiveIntegerField("清理尝试次数", default=0)
    failure_reason = models.TextField("失败原因", blank=True)
    cleanup_error = models.TextField("清理失败原因", blank=True)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    heartbeat_at = models.DateTimeField("心跳时间", null=True, blank=True)


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
