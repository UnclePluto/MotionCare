from django.db import models

from apps.common.models import UserStampedModel


class Patient(UserStampedModel):
    class Gender(models.TextChoices):
        MALE = "male", "男"
        FEMALE = "female", "女"
        UNKNOWN = "unknown", "未知"

    name = models.CharField("姓名", max_length=80)
    gender = models.CharField("性别", max_length=16, choices=Gender.choices)
    birth_date = models.DateField("出生日期", null=True, blank=True)
    age = models.PositiveIntegerField("年龄", null=True, blank=True)
    phone = models.CharField("手机号", max_length=20, unique=True)
    primary_doctor = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="patients",
    )
    symptom_note = models.TextField("症状或备注", blank=True)
    is_active = models.BooleanField("是否启用", default=True)

    def __str__(self) -> str:
        return f"{self.name}（{self.phone}）"


class PatientBaseline(UserStampedModel):
    patient = models.OneToOneField(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="baseline",
    )

    subject_id = models.CharField(max_length=64, blank=True, default="")
    name_initials = models.CharField(max_length=32, blank=True, default="")

    demographics = models.JSONField(blank=True, default=dict)
    surgery_allergy = models.JSONField(blank=True, default=dict)
    comorbidities = models.JSONField(blank=True, default=dict)
    lifestyle = models.JSONField(blank=True, default=dict)
    baseline_medications = models.JSONField(blank=True, default=dict)

