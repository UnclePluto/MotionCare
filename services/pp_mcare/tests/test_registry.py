from pp_mcare.registry import get_action_plugin


SUPPORTED_VERSIONS = (
    "motion-resistance-shoulder-press",
    "PP-TinyPose_128x96",
    "shoulder-press-v2",
    "shoulder-press-v2-defaults",
)


def test_registry_resolves_only_exact_shoulder_press_v2_versions():
    plugin = get_action_plugin(*SUPPORTED_VERSIONS)

    assert plugin is not None
    assert plugin.source_key == SUPPORTED_VERSIONS[0]
    assert plugin.algorithm_version == SUPPORTED_VERSIONS[1]
    assert plugin.rule_version == SUPPORTED_VERSIONS[2]
    assert plugin.parameter_version == SUPPORTED_VERSIONS[3]


def test_registry_rejects_each_nonmatching_capability_component_without_fallback():
    for changed_index, replacement in enumerate(
        (
            "motion-resistance-row",
            "PP-TinyPose_256x192",
            "shoulder-press-v3",
            "shoulder-press-v2-custom",
        )
    ):
        requested = list(SUPPORTED_VERSIONS)
        requested[changed_index] = replacement

        assert get_action_plugin(*requested) is None


def test_registry_does_not_normalize_case_or_whitespace():
    assert (
        get_action_plugin(
            " motion-resistance-shoulder-press",
            *SUPPORTED_VERSIONS[1:],
        )
        is None
    )
    assert (
        get_action_plugin(
            SUPPORTED_VERSIONS[0].upper(),
            *SUPPORTED_VERSIONS[1:],
        )
        is None
    )
