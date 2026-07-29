from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class ProviderMeasurement:
    metric_type: str
    measured_at: datetime
    values: dict[str, int | Decimal]
    raw_payload: dict


@dataclass(frozen=True)
class ProviderDailySteps:
    record_date: date
    steps: int | None
    distance: Decimal | None
    calorie: Decimal | None
    raw_payload: dict


@dataclass(frozen=True)
class ProviderDeviceStatus:
    external_device_id: str | None
    model: str | None
    status: str | None
    battery_level: int | None
    last_communication_at: datetime | None
    raw_payload: dict


@dataclass(frozen=True)
class ProviderCommandResult:
    code: int
    message: str
    raw_payload: dict


class ProviderError(Exception):
    def __init__(self, message: str, *, code: int | None = None):
        self.code = code
        super().__init__(f"厂商接口错误（code={code}）：{message}" if code is not None else message)


class WearableProvider(Protocol):
    def get_heart_rates(
        self, external_device_id: str, begin_at: datetime, end_at: datetime
    ) -> list[ProviderMeasurement]: ...

    def get_blood_pressures(
        self, external_device_id: str, begin_at: datetime, end_at: datetime
    ) -> list[ProviderMeasurement]: ...

    def get_blood_oxygen(
        self, external_device_id: str, begin_at: datetime, end_at: datetime
    ) -> list[ProviderMeasurement]: ...

    def get_daily_steps(
        self, external_device_id: str, begin_date: date, end_date: date
    ) -> list[ProviderDailySteps]: ...

    def get_device_status(self, external_device_id: str) -> ProviderDeviceStatus: ...

    def send_command(
        self,
        external_device_id: str,
        command_code: str,
        command_value: str = "",
        request_id: str | None = None,
    ) -> ProviderCommandResult: ...
