import re

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import TimeStampedModel


class WearableDevice(TimeStampedModel):
    provider = models.CharField("厂商", max_length=64)
    external_device_id = models.CharField("厂商设备标识", max_length=128)
    identifier_type = models.CharField("设备标识类型", max_length=64)
    model = models.CharField("设备型号", max_length=128, blank=True)
    short_code = models.CharField("设备固定简码", max_length=4, unique=True)
    enabled = models.BooleanField("是否启用", default=True)
    last_communication_at = models.DateTimeField("最近通信时间", null=True, blank=True)
    last_battery_level = models.PositiveSmallIntegerField("最近电量", null=True, blank=True)
    last_device_status = models.CharField("最近设备状态", max_length=32, blank=True)
    last_status_checked_at = models.DateTimeField("最近状态检查时间", null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "external_device_id"],
                name="uniq_wearable_device_external_identity",
            ),
            models.CheckConstraint(
                condition=models.Q(short_code__regex=r"^\d{4}$"),
                name="wearable_device_short_code_four_digits",
            ),
        ]

    def clean(self):
        super().clean()
        if not re.fullmatch(r"\d{4}", self.short_code):
            raise ValidationError({"short_code": "设备固定简码必须为四位数字。"})


class WearableBinding(TimeStampedModel):
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="wearable_bindings",
    )
    device = models.ForeignKey(
        WearableDevice,
        on_delete=models.CASCADE,
        related_name="bindings",
    )
    bound_at = models.DateTimeField("绑定时间")
    unbound_at = models.DateTimeField("解绑时间", null=True, blank=True)
    bound_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wearable_bindings_bound",
    )
    unbound_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wearable_bindings_unbound",
    )
    unbind_reason = models.TextField("解绑原因", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patient"],
                condition=models.Q(unbound_at__isnull=True),
                name="uniq_active_wearable_binding_per_patient",
            ),
            models.UniqueConstraint(
                fields=["device"],
                condition=models.Q(unbound_at__isnull=True),
                name="uniq_active_wearable_binding_per_device",
            ),
            models.CheckConstraint(
                condition=models.Q(unbound_at__isnull=True)
                | models.Q(unbound_at__gt=models.F("bound_at")),
                name="wearable_binding_end_after_start",
            ),
        ]


class WearableMeasurement(TimeStampedModel):
    class MetricType(models.TextChoices):
        HEART_RATE = "heart_rate", "心率"
        BLOOD_PRESSURE = "blood_pressure", "血压"
        BLOOD_OXYGEN = "blood_oxygen", "血氧"

    class AttributionStatus(models.TextChoices):
        ATTRIBUTED = "attributed", "已归属"
        OUTSIDE_BINDING = "outside_binding", "绑定区间外"
        AMBIGUOUS = "ambiguous", "归属不明确"

    provider = models.CharField("厂商", max_length=64)
    device = models.ForeignKey(
        WearableDevice,
        on_delete=models.CASCADE,
        related_name="measurements",
    )
    binding = models.ForeignKey(
        WearableBinding,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="measurements",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wearable_measurements",
    )
    metric_type = models.CharField("指标类型", max_length=32, choices=MetricType.choices)
    measured_at = models.DateTimeField("测量时间")
    heart_rate = models.PositiveSmallIntegerField("心率", null=True, blank=True)
    systolic = models.PositiveSmallIntegerField("收缩压", null=True, blank=True)
    diastolic = models.PositiveSmallIntegerField("舒张压", null=True, blank=True)
    blood_oxygen = models.PositiveSmallIntegerField("血氧", null=True, blank=True)
    source_fingerprint = models.CharField("来源指纹", max_length=64)
    attribution_status = models.CharField(
        "归属状态",
        max_length=32,
        choices=AttributionStatus.choices,
        default=AttributionStatus.OUTSIDE_BINDING,
    )
    raw_payload = models.JSONField("原始数据", default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "device", "metric_type", "source_fingerprint"],
                name="uniq_wearable_measurement_source",
            )
        ]


class WearableDailySource(TimeStampedModel):
    class AttributionStatus(models.TextChoices):
        ATTRIBUTED = "attributed", "已归属"
        OUTSIDE_BINDING = "outside_binding", "绑定区间外"
        AMBIGUOUS = "ambiguous", "归属不明确"

    provider = models.CharField("厂商", max_length=64)
    device = models.ForeignKey(
        WearableDevice,
        on_delete=models.CASCADE,
        related_name="daily_sources",
    )
    record_date = models.DateField("记录日期")
    steps = models.PositiveIntegerField("步数", null=True, blank=True)
    distance = models.DecimalField("距离", max_digits=10, decimal_places=2, null=True, blank=True)
    calorie = models.DecimalField("卡路里", max_digits=10, decimal_places=2, null=True, blank=True)
    binding = models.ForeignKey(
        WearableBinding,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_sources",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wearable_daily_sources",
    )
    attribution_status = models.CharField(
        "归属状态",
        max_length=32,
        choices=AttributionStatus.choices,
        default=AttributionStatus.OUTSIDE_BINDING,
    )
    raw_payload = models.JSONField("原始数据", default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "device", "record_date"],
                name="uniq_wearable_daily_source",
            )
        ]


class WearableDailySummary(TimeStampedModel):
    class AttributionStatus(models.TextChoices):
        ATTRIBUTED = "attributed", "已归属"
        OUTSIDE_BINDING = "outside_binding", "绑定区间外"
        AMBIGUOUS = "ambiguous", "归属不明确"

    class SyncStatus(models.TextChoices):
        PENDING = "pending", "待同步"
        SUCCEEDED = "succeeded", "同步成功"
        FAILED = "failed", "同步失败"

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="wearable_daily_summaries",
    )
    record_date = models.DateField("记录日期")
    heart_rate_avg = models.DecimalField("平均心率", max_digits=6, decimal_places=2, null=True, blank=True)
    heart_rate_min = models.PositiveSmallIntegerField("最低心率", null=True, blank=True)
    heart_rate_max = models.PositiveSmallIntegerField("最高心率", null=True, blank=True)
    heart_rate_count = models.PositiveIntegerField("心率测量次数", default=0)
    systolic_avg = models.DecimalField("平均收缩压", max_digits=6, decimal_places=2, null=True, blank=True)
    diastolic_avg = models.DecimalField("平均舒张压", max_digits=6, decimal_places=2, null=True, blank=True)
    blood_pressure_count = models.PositiveIntegerField("血压测量次数", default=0)
    blood_oxygen_avg = models.DecimalField("平均血氧", max_digits=6, decimal_places=2, null=True, blank=True)
    blood_oxygen_min = models.PositiveSmallIntegerField("最低血氧", null=True, blank=True)
    blood_oxygen_max = models.PositiveSmallIntegerField("最高血氧", null=True, blank=True)
    blood_oxygen_count = models.PositiveIntegerField("血氧测量次数", default=0)
    steps = models.PositiveIntegerField("步数", null=True, blank=True)
    steps_attribution_status = models.CharField(
        "步数归属状态",
        max_length=32,
        choices=AttributionStatus.choices,
        default=AttributionStatus.OUTSIDE_BINDING,
    )
    heart_rate_sync_status = models.CharField(
        "心率同步状态",
        max_length=16,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
    )
    blood_pressure_sync_status = models.CharField(
        "血压同步状态",
        max_length=16,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
    )
    blood_oxygen_sync_status = models.CharField(
        "血氧同步状态",
        max_length=16,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
    )
    steps_sync_status = models.CharField(
        "步数同步状态",
        max_length=16,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
    )
    calculated_at = models.DateTimeField("计算时间", null=True, blank=True)
    calculation_version = models.CharField("计算版本", max_length=32, default="1")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "record_date"],
                name="uniq_wearable_daily_summary",
            )
        ]


class WearableSyncCursor(TimeStampedModel):
    device = models.ForeignKey(
        WearableDevice,
        on_delete=models.CASCADE,
        related_name="sync_cursors",
    )
    metric_type = models.CharField("指标类型", max_length=32)
    last_success_window_end = models.DateTimeField("最近成功窗口结束时间", null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["device", "metric_type"],
                name="uniq_wearable_sync_cursor",
            )
        ]


class WearableSyncRun(TimeStampedModel):
    class Status(models.TextChoices):
        RUNNING = "running", "运行中"
        SUCCEEDED = "succeeded", "成功"
        FAILED = "failed", "失败"

    device = models.ForeignKey(
        WearableDevice,
        on_delete=models.CASCADE,
        related_name="sync_runs",
    )
    metric_type = models.CharField("指标类型", max_length=32)
    scheduled_at = models.DateTimeField("计划时间", null=True, blank=True)
    window_start = models.DateTimeField("同步窗口开始时间", null=True, blank=True)
    window_end = models.DateTimeField("同步窗口结束时间", null=True, blank=True)
    status = models.CharField("同步状态", max_length=16, choices=Status.choices)
    returned_count = models.PositiveIntegerField("返回数量", default=0)
    error_code = models.CharField("错误码", max_length=64, blank=True)
    error_message = models.TextField("错误信息", blank=True)
    retry_count = models.PositiveSmallIntegerField("重试次数", default=0)


class WearableCommandLog(TimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "排队中"
        SUCCEEDED = "succeeded", "成功"
        OFFLINE = "offline", "设备离线"
        TIMEOUT = "timeout", "超时"
        FAILED = "failed", "失败"

    device = models.ForeignKey(
        WearableDevice,
        on_delete=models.CASCADE,
        related_name="command_logs",
    )
    command_type = models.CharField("命令类型", max_length=64)
    command_code = models.CharField("命令编码", max_length=64, blank=True)
    request_payload = models.JSONField("请求参数", default=dict)
    provider_code = models.CharField("厂商返回码", max_length=64, blank=True)
    status = models.CharField("命令状态", max_length=16, choices=Status.choices)
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wearable_command_logs",
    )
    requested_at = models.DateTimeField("实际发命令时间", null=True, blank=True)
    poll_attempts = models.PositiveSmallIntegerField("轮询次数", default=0)
    poll_deadline_at = models.DateTimeField("轮询截止时间", null=True, blank=True)
    next_poll_at = models.DateTimeField("下次轮询时间", null=True, blank=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)
