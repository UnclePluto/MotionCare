from django.conf import settings
from django.db import models

from apps.common.models import UserStampedModel


class MotionResultSource(models.TextChoices):
    ALGORITHM = "algorithm", "算法"
    DOCTOR = "doctor", "医生"


class TrainingRecord(UserStampedModel):
    class Status(models.TextChoices):
        COMPLETED = "completed", "已完成"
        PARTIAL = "partial", "部分完成"
        MISSED = "missed", "未完成"

    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="training_records",
    )
    prescription = models.ForeignKey("prescriptions.Prescription", on_delete=models.PROTECT)
    prescription_action = models.ForeignKey(
        "prescriptions.PrescriptionAction", on_delete=models.PROTECT
    )
    training_date = models.DateField("训练日期")
    status = models.CharField("完成状态", max_length=20, choices=Status.choices)
    actual_duration_minutes = models.PositiveIntegerField("实际时长", null=True, blank=True)
    score = models.DecimalField("得分", max_digits=6, decimal_places=2, null=True, blank=True)
    form_data = models.JSONField("分类表单数据", default=dict)
    note = models.TextField("备注", blank=True)
    motion_total_count = models.PositiveIntegerField("动作总次数", null=True, blank=True)
    motion_standard_count = models.PositiveIntegerField("标准动作次数", null=True, blank=True)
    motion_nonstandard_count = models.PositiveIntegerField(
        "非标准动作次数", null=True, blank=True
    )
    motion_quality_data = models.JSONField("动作质量数据", default=dict)
    motion_result_source = models.CharField(
        "动作结果来源",
        max_length=20,
        choices=MotionResultSource.choices,
        blank=True,
        default="",
    )
    motion_result_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="motion_results_updated",
    )
    motion_result_updated_at = models.DateTimeField("动作结果更新时间", null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        motion_total_count__isnull=True,
                        motion_standard_count__isnull=True,
                        motion_nonstandard_count__isnull=True,
                    )
                    | models.Q(
                        motion_total_count__isnull=False,
                        motion_standard_count__isnull=False,
                        motion_nonstandard_count__isnull=False,
                        motion_total_count=(
                            models.F("motion_standard_count")
                            + models.F("motion_nonstandard_count")
                        ),
                    )
                ),
                name="training_record_motion_counts_consistent",
            )
        ]

    def set_motion_result(self, counts, quality_data, source, updated_by, now):
        self.motion_total_count = counts.total_count
        self.motion_standard_count = counts.standard_count
        self.motion_nonstandard_count = counts.nonstandard_count
        self.motion_quality_data = dict(quality_data)
        self.motion_result_source = source
        self.motion_result_updated_by = updated_by
        self.motion_result_updated_at = now


from .video_models import (  # noqa: E402,F401
    LegacyTrainingVideoSegmentArchive,
    MotionAnalysisJob,
    QiniuCleanupTombstone,
    TrainingVideo,
    TrainingVideoSegment,
    VideoAssemblyJob,
)
