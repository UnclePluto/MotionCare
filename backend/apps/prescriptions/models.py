from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import UserStampedModel


class ActionLibraryItem(UserStampedModel):
    class InternalType(models.TextChoices):
        VIDEO = "video", "视频类"
        GAME = "game", "游戏互动类"
        MOTION = "motion", "运动类"

    source_key = models.CharField("动作编码", max_length=120, unique=True, null=True, blank=True)
    name = models.CharField("动作名称", max_length=120)
    training_type = models.CharField("训练类型", max_length=80)
    internal_type = models.CharField("内部类型", max_length=20, choices=InternalType.choices)
    action_type = models.CharField("动作类型", max_length=80)
    instruction_text = models.TextField("动作说明文案", blank=True)
    suggested_frequency = models.CharField("建议频次", max_length=80, blank=True)
    suggested_duration_minutes = models.PositiveIntegerField("建议时长", null=True, blank=True)
    default_difficulty = models.CharField("默认难度", max_length=40, blank=True)
    video_url = models.URLField("视频URL", max_length=500, blank=True)
    has_ai_supervision = models.BooleanField("是否支持AI监督", default=False)
    is_active = models.BooleanField("是否启用", default=True)


class Prescription(UserStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        ACTIVE = "active", "生效中"
        PENDING = "pending", "待生效"
        ARCHIVED = "archived", "已归档"
        TERMINATED = "terminated", "已终止"

    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescriptions",
    )
    version = models.PositiveIntegerField("版本号")
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="opened_prescriptions",
    )
    opened_at = models.DateTimeField("开设时间", auto_now_add=True)
    effective_at = models.DateTimeField("生效时间", null=True, blank=True)
    archived_at = models.DateTimeField("归档时间", null=True, blank=True)
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.DRAFT)
    note = models.TextField("备注", blank=True)

    class Meta:
        unique_together = [("project_patient", "version")]

    def add_action_snapshot(
        self,
        action: ActionLibraryItem,
        *,
        weekly_frequency: str = "",
        duration_minutes: int | None = None,
        weekly_target_count: int = 1,
        difficulty: str = "",
        notes: str = "",
        sort_order: int = 0,
    ):
        if weekly_target_count <= 0:
            raise ValidationError("每周目标次数必须大于 0")
        return PrescriptionAction.objects.create(
            prescription=self,
            action_library_item=action,
            action_name_snapshot=action.name,
            training_type_snapshot=action.training_type,
            internal_type_snapshot=action.internal_type,
            action_type_snapshot=action.action_type,
            action_instruction_snapshot=action.instruction_text,
            video_url_snapshot=action.video_url,
            has_ai_supervision_snapshot=action.has_ai_supervision,
            weekly_frequency=weekly_frequency,
            duration_minutes=duration_minutes,
            weekly_target_count=weekly_target_count,
            difficulty=difficulty,
            notes=notes,
            sort_order=sort_order,
        )


class PrescriptionAction(UserStampedModel):
    prescription = models.ForeignKey(
        Prescription, on_delete=models.CASCADE, related_name="actions"
    )
    action_library_item = models.ForeignKey(ActionLibraryItem, on_delete=models.PROTECT)
    action_name_snapshot = models.CharField("动作名称快照", max_length=120)
    training_type_snapshot = models.CharField("训练类型快照", max_length=80)
    internal_type_snapshot = models.CharField("内部类型快照", max_length=20)
    action_type_snapshot = models.CharField("动作类型快照", max_length=80)
    action_instruction_snapshot = models.TextField("动作说明文案快照", blank=True)
    video_url_snapshot = models.URLField("视频URL快照", max_length=500, blank=True)
    has_ai_supervision_snapshot = models.BooleanField("是否支持AI监督快照", default=False)
    weekly_frequency = models.CharField("每周频次", max_length=80, blank=True)
    duration_minutes = models.PositiveIntegerField("时长", null=True, blank=True)
    weekly_target_count = models.PositiveIntegerField("每周目标次数", default=1)
    difficulty = models.CharField("难度", max_length=40, blank=True)
    notes = models.TextField("注意事项", blank=True)
    sort_order = models.PositiveIntegerField("排序", default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(weekly_target_count__gt=0),
                name="prescription_action_weekly_target_count_gt_0",
            )
        ]
