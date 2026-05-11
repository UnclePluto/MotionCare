from django.conf import settings
from django.db import models

from apps.common.models import UserStampedModel


class ActionLibraryItem(UserStampedModel):
    class InternalType(models.TextChoices):
        VIDEO = "video", "视频类"
        GAME = "game", "游戏互动类"
        MOTION = "motion", "运动类"

    name = models.CharField("动作名称", max_length=120)
    training_type = models.CharField("训练类型", max_length=80)
    internal_type = models.CharField("内部类型", max_length=20, choices=InternalType.choices)
    action_type = models.CharField("动作类型", max_length=80)
    execution_description = models.TextField("执行描述", blank=True)
    key_points = models.TextField("动作要点", blank=True)
    suggested_frequency = models.CharField("建议频次", max_length=80, blank=True)
    suggested_duration_minutes = models.PositiveIntegerField("建议时长", null=True, blank=True)
    suggested_sets = models.PositiveIntegerField("建议组数", null=True, blank=True)
    default_difficulty = models.CharField("默认难度", max_length=40, blank=True)
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
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.DRAFT)
    note = models.TextField("备注", blank=True)

    class Meta:
        unique_together = [("project_patient", "version")]

    def add_action_snapshot(
        self,
        action: ActionLibraryItem,
        *,
        frequency: str = "",
        duration_minutes: int | None = None,
        sets: int | None = None,
        difficulty: str = "",
        notes: str = "",
        sort_order: int = 0,
    ):
        return PrescriptionAction.objects.create(
            prescription=self,
            action_library_item=action,
            action_name_snapshot=action.name,
            training_type_snapshot=action.training_type,
            internal_type_snapshot=action.internal_type,
            action_type_snapshot=action.action_type,
            execution_description_snapshot=action.execution_description,
            frequency=frequency,
            duration_minutes=duration_minutes,
            sets=sets,
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
    execution_description_snapshot = models.TextField("执行描述快照", blank=True)
    frequency = models.CharField("频次", max_length=80, blank=True)
    duration_minutes = models.PositiveIntegerField("时长", null=True, blank=True)
    sets = models.PositiveIntegerField("组数", null=True, blank=True)
    difficulty = models.CharField("难度", max_length=40, blank=True)
    notes = models.TextField("注意事项", blank=True)
    sort_order = models.PositiveIntegerField("排序", default=0)

