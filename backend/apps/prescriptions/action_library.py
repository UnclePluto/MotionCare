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


def official_action_queryset(queryset):
    return queryset.filter(source_key__in=OFFICIAL_ACTION_SOURCE_KEYS, is_active=True)
