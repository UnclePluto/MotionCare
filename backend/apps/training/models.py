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
    client_session_id = models.UUIDField(
        "游戏客户端会话 ID", null=True, blank=True, unique=True
    )
    client_payload_fingerprint = models.CharField(
        "游戏客户端语义指纹", max_length=64, blank=True
    )
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


class GameQuestionResult(models.Model):
    class ResultType(models.TextChoices):
        ANSWERED = "answered", "已作答"
        TIMEOUT = "timeout", "答题超时"
        INTERRUPTED = "interrupted", "未完成"

    class CaptureVersion(models.TextChoices):
        LEGACY_WALL_CLOCK_V0 = "legacy_wall_clock_v0", "历史墙上时钟"
        ACTIVE_RESPONSE_V1 = "active_response_v1", "有效作答时间"
        ACTIVE_RESPONSE_V2 = "active_response_v2", "有效作答及逐步选择时间"

    training_record = models.ForeignKey(
        TrainingRecord,
        on_delete=models.CASCADE,
        related_name="question_results",
    )
    question_index = models.PositiveIntegerField("题号")
    game_code = models.CharField("游戏编码快照", max_length=80, db_index=True)
    difficulty = models.CharField("实际难度", max_length=40, db_index=True)
    response_duration_ms = models.PositiveIntegerField("有效作答时长毫秒")
    is_correct = models.BooleanField("是否正确")
    result_type = models.CharField(
        "结果类型", max_length=20, choices=ResultType.choices
    )
    swap_count = models.PositiveIntegerField(
        "拼图交换次数", null=True, blank=True
    )
    expected_step_count = models.PositiveIntegerField("应选择步数", null=True, blank=True)
    click_count = models.PositiveIntegerField("拼图点击次数", null=True, blank=True)
    capture_version = models.CharField(
        "采集版本", max_length=32, choices=CaptureVersion.choices
    )

    class Meta:
        ordering = ["question_index", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["training_record", "question_index"],
                name="game_question_record_index_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(question_index__gt=0),
                name="game_question_index_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(response_duration_ms__gte=0),
                name="game_question_duration_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(result_type="timeout")
                    | models.Q(is_correct=False)
                ),
                name="game_question_timeout_incorrect",
            ),
        ]


class GameQuestionSelectionStep(models.Model):
    question = models.ForeignKey(GameQuestionResult, on_delete=models.CASCADE, related_name="selection_steps")
    step_index = models.PositiveIntegerField("选择序号")
    selected_value = models.CharField("所选内容", max_length=32)
    expected_value = models.CharField("正确内容", max_length=32)
    response_duration_ms = models.PositiveIntegerField("有效选择耗时毫秒")
    is_correct = models.BooleanField("是否正确")

    class Meta:
        ordering = ["step_index", "id"]
        constraints = [
            models.UniqueConstraint(fields=["question", "step_index"], name="game_selection_question_index_uniq"),
            models.CheckConstraint(condition=models.Q(step_index__gte=1, step_index__lte=5), name="game_selection_index_range"),
            models.CheckConstraint(condition=models.Q(response_duration_ms__gte=0, response_duration_ms__lte=3600000), name="game_selection_duration_range"),
        ]


class TrainingDetailExportLog(models.Model):
    class Status(models.TextChoices):
        GENERATING = "generating", "生成中"
        SUCCEEDED = "succeeded", "已生成"
        FAILED = "failed", "失败"

    class ErrorCode(models.TextChoices):
        NONE = "", "无"
        LIMIT_EXCEEDED = "limit_exceeded", "超出容量"
        DEADLINE_EXCEEDED = "deadline_exceeded", "生成超时"
        GENERATION_FAILED = "generation_failed", "生成失败"
        AUDIT_FAILED = "audit_failed", "审计失败"
        SCOPE_CHANGED = "scope_changed", "授权范围变化"

    operator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    patient_id_snapshot = models.PositiveBigIntegerField()
    project_id_snapshot = models.PositiveBigIntegerField()
    project_patient_id_snapshot = models.PositiveBigIntegerField()
    filters = models.JSONField(default=dict)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.GENERATING)
    format_version = models.CharField(max_length=32, default="training_detail_v2")
    row_counts = models.JSONField(default=dict)
    error_code = models.CharField(max_length=32, choices=ErrorCode.choices, blank=True, default="")


from .video_models import (  # noqa: E402,F401
    LegacyTrainingVideoSegmentArchive,
    MotionAnalysisJob,
    QiniuCleanupTombstone,
    TrainingVideo,
    TrainingVideoSegment,
    VideoAssemblyJob,
)
