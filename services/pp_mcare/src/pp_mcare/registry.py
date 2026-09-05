from __future__ import annotations

from .actions.base import ActionPlugin
from .actions.shoulder_press_v2 import ShoulderPressV2Plugin


_SHOULDER_PRESS_V2 = ShoulderPressV2Plugin()
_PLUGINS: dict[tuple[str, str, str, str], ActionPlugin] = {
    (
        _SHOULDER_PRESS_V2.source_key,
        _SHOULDER_PRESS_V2.algorithm_version,
        _SHOULDER_PRESS_V2.rule_version,
        _SHOULDER_PRESS_V2.parameter_version,
    ): _SHOULDER_PRESS_V2
}


def get_action_plugin(
    source_key: str,
    algorithm_version: str,
    rule_version: str,
    parameter_version: str,
) -> ActionPlugin | None:
    return _PLUGINS.get((source_key, algorithm_version, rule_version, parameter_version))
