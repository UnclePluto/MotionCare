from django.db import models

from apps.common.models import UserStampedModel


class StudyProject(UserStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        ACTIVE = "active", "进行中"
        ARCHIVED = "archived", "已归档"

    name = models.CharField("项目名称", max_length=160)
    description = models.TextField("项目描述", blank=True)
    crf_template_version = models.CharField("CRF模板版本", max_length=40, default="1.1")
    visit_plan = models.JSONField("访视计划", default=list)
    status = models.CharField(
        "项目状态", max_length=20, choices=Status.choices, default=Status.DRAFT
    )

    def __str__(self) -> str:
        return self.name


class StudyGroup(UserStampedModel):
    project = models.ForeignKey(StudyProject, on_delete=models.CASCADE, related_name="groups")
    name = models.CharField("分组名称", max_length=100)
    description = models.TextField("分组说明", blank=True)
    target_ratio = models.PositiveIntegerField("目标比例", default=1)
    sort_order = models.PositiveIntegerField("排序", default=0)
    is_active = models.BooleanField("是否启用", default=True)

    class Meta:
        unique_together = [("project", "name")]
        ordering = ["project_id", "sort_order", "id"]


class ProjectPatient(UserStampedModel):
    project = models.ForeignKey(
        StudyProject, on_delete=models.CASCADE, related_name="project_patients"
    )
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="project_links"
    )
    group = models.ForeignKey(StudyGroup, null=True, blank=True, on_delete=models.PROTECT)
    enrolled_at = models.DateTimeField("入组时间", auto_now_add=True)

    class Meta:
        unique_together = [("project", "patient")]
