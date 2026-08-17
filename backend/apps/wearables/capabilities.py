from dataclasses import dataclass, replace


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

# miwitracker 平台通用的“寻找设备 / 响铃”指令码，不依赖具体型号。
MIWITRACKER_RING_COMMAND_CODE = "9018"


def get_capability_profile(provider: str, model: str | None) -> CapabilityProfile:
    if not isinstance(model, str) or not model.strip():
        return CapabilityProfile()
    configured = MODEL_CAPABILITIES.get((provider, model), CapabilityProfile())
    if provider == "miwitracker" and not configured.ring:
        # 响铃（寻找设备）是 miwitracker 全平台通用指令；其余能力仍按型号验证。
        return replace(configured, ring=MIWITRACKER_RING_COMMAND_CODE)
    return configured
