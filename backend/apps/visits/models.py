from django.db import models

from apps.common.models import UserStampedModel


class VisitRecord(UserStampedModel):
    class VisitType(models.TextChoices):
        T0 = "T0", "T0 筛选/入组"
        T1 = "T1", "T1 干预12周"
        T2 = "T2", "T2 干预后36周随访"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        COMPLETED = "completed", "已完成"

    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="visits",
    )
    visit_type = models.CharField("访视类型", max_length=8, choices=VisitType.choices)
    status = models.CharField("状态", max_length=20, choices=Status.choices, default=Status.DRAFT)
    visit_date = models.DateField("访视日期", null=True, blank=True)
    form_data = models.JSONField("访视表单数据", default=dict)

    class Meta:
        unique_together = [("project_patient", "visit_type")]

