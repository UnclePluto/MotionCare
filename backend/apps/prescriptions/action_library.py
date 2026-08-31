OFFICIAL_ACTION_SOURCE_KEYS = frozenset(
    {
        "motion-aerobic-high-knee",
        "motion-balance-sit-stand",
        "motion-resistance-leg-kickback",
        "motion-resistance-row",
        "motion-resistance-shoulder-press",
        "game-audiovisual-puzzle",
        "game-audiovisual-sound-discrimination",
        "game-executive-category-switch",
        "game-executive-inhibition",
        "game-memory-color-sequence",
        "game-memory-pattern-sequence",
    }
)

MOTION_ACTION_VIDEO_OBJECT_KEYS = {
    source_key: f"motion-action-videos/v1/{source_key}.mp4"
    for source_key in (
        "motion-aerobic-high-knee",
        "motion-balance-sit-stand",
        "motion-resistance-row",
        "motion-resistance-leg-kickback",
        "motion-resistance-shoulder-press",
    )
}
OFFICIAL_MOTION_ACTION_SOURCE_KEYS = frozenset(MOTION_ACTION_VIDEO_OBJECT_KEYS)


def is_official_motion_action(source_key: str | None) -> bool:
    return source_key in OFFICIAL_MOTION_ACTION_SOURCE_KEYS


def official_action_queryset(queryset):
    return queryset.filter(source_key__in=OFFICIAL_ACTION_SOURCE_KEYS, is_active=True)
