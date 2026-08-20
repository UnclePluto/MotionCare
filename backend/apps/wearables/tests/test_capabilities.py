import pytest

from apps.wearables.capabilities import get_capability_profile


@pytest.mark.parametrize("model", [None, "", "   ", "UNKNOWN"])
def test_miwitracker_ring_is_available_without_model_capability(model):
    profile = get_capability_profile("miwitracker", model)

    assert profile.ring == "9018"


def test_other_providers_do_not_inherit_miwitracker_ring_capability():
    profile = get_capability_profile("other-provider", "UNKNOWN")

    assert profile.ring is None
