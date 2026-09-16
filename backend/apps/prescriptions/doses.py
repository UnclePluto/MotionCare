COUNTED_MOTION_KEYS = frozenset(
    {
        "motion-balance-sit-stand",
        "motion-resistance-row",
        "motion-resistance-leg-kickback",
        "motion-resistance-shoulder-press",
    }
)


def is_counted_motion(source_key):
    return source_key in COUNTED_MOTION_KEYS


def count_unit_for(source_key):
    return "per_side" if source_key == "motion-resistance-leg-kickback" else "total"
