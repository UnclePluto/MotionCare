from django.db import migrations


OFFICIAL_ACTION_SOURCE_KEYS = {
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


def prune_unofficial_actions(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    PrescriptionAction = apps.get_model("prescriptions", "PrescriptionAction")
    referenced_ids = set(
        PrescriptionAction.objects.filter(action_library_item_id__isnull=False).values_list(
            "action_library_item_id",
            flat=True,
        )
    )
    unofficial_actions = ActionLibraryItem.objects.exclude(
        source_key__in=OFFICIAL_ACTION_SOURCE_KEYS
    )
    unofficial_actions.exclude(id__in=referenced_ids).delete()
    unofficial_actions.filter(id__in=referenced_ids).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0010_seed_game_actions"),
    ]

    operations = [
        migrations.RunPython(prune_unofficial_actions, migrations.RunPython.noop),
    ]
