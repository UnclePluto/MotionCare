from django.db import models

from apps.common.models import UserStampedModel


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

