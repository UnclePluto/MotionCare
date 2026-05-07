from django.db import models

from apps.common.models import UserStampedModel


class DailyHealthRecord(UserStampedModel):
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="daily_health"
    )
    record_date = models.DateField("日期")
    steps = models.PositiveIntegerField("步数", null=True, blank=True)
    exercise_minutes = models.PositiveIntegerField("运动时长", null=True, blank=True)
    average_heart_rate = models.PositiveIntegerField("平均心率", null=True, blank=True)
    max_heart_rate = models.PositiveIntegerField("最高心率", null=True, blank=True)
    min_heart_rate = models.PositiveIntegerField("最低心率", null=True, blank=True)
    sleep_hours = models.DecimalField("睡眠时长", max_digits=4, decimal_places=1, null=True, blank=True)
    note = models.TextField("备注", blank=True)

    class Meta:
        unique_together = [("patient", "record_date")]

