from django.db import transaction
from django.utils import timezone

from apps.patients.models import Patient
from apps.wearables.models import WearableBinding, WearableDevice


class BindingConflict(Exception):
    """有效绑定与请求发生冲突。"""

    def __init__(self, message: str, *, conflicting_patient_id: int | None = None):
        super().__init__(message)
        self.conflicting_patient_id = conflicting_patient_id


class DeviceNotFound(Exception):
    """未找到启用的设备。"""


class BindingAlreadyUnbound(Exception):
    """绑定已结束，不能重复解绑。"""


class InvalidUnbindTime(ValueError):
    """解绑时间不在有效绑定区间之后。"""


def mask_patient_name(name: str) -> str:
    """患者姓名统一仅保留首字符。"""
    normalized = name.strip()
    return f"{normalized[0]}*" if normalized else "*"


def bind_device(*, project_patient, short_code: str, actor, bound_at=None):
    """将启用设备绑定给项目患者所关联的全局患者。"""
    bound_at = bound_at or timezone.now()
    with transaction.atomic():
        patient = Patient.objects.select_for_update().get(pk=project_patient.patient_id)
        try:
            device = WearableDevice.objects.select_for_update().get(
                short_code=short_code,
                enabled=True,
            )
        except WearableDevice.DoesNotExist as exc:
            raise DeviceNotFound from exc

        active_for_patient = (
            WearableBinding.objects.select_for_update()
            .filter(patient=patient, unbound_at__isnull=True)
            .first()
        )
        active_for_device = (
            WearableBinding.objects.select_for_update()
            .filter(device=device, unbound_at__isnull=True)
            .first()
        )

        if active_for_patient and active_for_patient.device_id == device.id:
            return active_for_patient, False
        if active_for_patient:
            raise BindingConflict("患者已有其他有效设备绑定。")
        if active_for_device:
            raise BindingConflict(
                "设备已绑定至其他患者。",
                conflicting_patient_id=active_for_device.patient_id,
            )

        return (
            WearableBinding.objects.create(
                patient=patient,
                device=device,
                bound_at=bound_at,
                bound_by=actor,
            ),
            True,
        )


def unbind_device(*, binding, actor, reason: str = "", unbound_at=None):
    """结束有效绑定，保留完整的历史绑定区间。"""
    unbound_at = unbound_at or timezone.now()
    with transaction.atomic():
        binding = WearableBinding.objects.select_for_update().get(pk=binding.pk)
        if binding.unbound_at is not None:
            raise BindingAlreadyUnbound("该设备绑定已解绑，不能重复操作。")
        if unbound_at <= binding.bound_at:
            raise InvalidUnbindTime("解绑时间必须晚于绑定时间。")
        binding.unbound_at = unbound_at
        binding.unbound_by = actor
        binding.unbind_reason = reason
        binding.save(update_fields=["unbound_at", "unbound_by", "unbind_reason", "updated_at"])
        return binding
