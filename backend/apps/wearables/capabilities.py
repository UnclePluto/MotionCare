from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityProfile:
    ring: str | None = None
    measure_heart_rate: str | None = None
    measure_blood_pressure: str | None = None
    measure_blood_oxygen: str | None = None
    configure_heart_rate_interval: str | None = None
    configure_blood_pressure_interval: str | None = None
    configure_blood_oxygen_interval: str | None = None
    configure_step_switch: str | None = None


# 生产环境默认安全关闭：仅经现场验证的型号才能在部署配置中加入能力映射。
MODEL_CAPABILITIES: dict[tuple[str, str], CapabilityProfile] = {}


def get_capability_profile(provider: str, model: str) -> CapabilityProfile:
    return MODEL_CAPABILITIES.get((provider, model), CapabilityProfile())
