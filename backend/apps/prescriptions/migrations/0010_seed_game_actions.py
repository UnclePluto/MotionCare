from django.db import migrations


GAME_ACTIONS = [
    {
        "source_key": "game-memory-color-sequence",
        "game_no": 1,
        "name": "颜色顺序记忆",
        "action_type": "记忆力训练",
        "description": "按顺序点击变色方块",
        "implementation_cost": "可实现",
        "resource_difficulty": "低",
    },
    {
        "source_key": "game-memory-pattern-sequence",
        "game_no": 2,
        "name": "图案顺序记忆",
        "action_type": "记忆力训练",
        "description": "展示图片，记忆后连续选择相同的图片",
        "implementation_cost": "可实现",
        "resource_difficulty": "低",
    },
    {
        "source_key": "game-executive-inhibition",
        "game_no": 5,
        "name": "反应抑制能力训练",
        "action_type": "执行力训练",
        "description": "出现多个数字，选择不同的数字",
        "implementation_cost": "可实现",
        "resource_difficulty": "低",
    },
    {
        "source_key": "game-executive-category-switch",
        "game_no": 6,
        "name": "分类转换任务",
        "action_type": "执行力训练",
        "description": "展示图片，选择图片内容对应的分类",
        "implementation_cost": "可实现",
        "resource_difficulty": "中等",
    },
    {
        "source_key": "game-audiovisual-sound-discrimination",
        "game_no": 9,
        "name": "声音辨别",
        "action_type": "视听力训练",
        "description": "播放选项对应音频，记忆后，播放声音，选择声音对应的选项",
        "implementation_cost": "可实现（稍晚）",
        "resource_difficulty": "较高",
    },
    {
        "source_key": "game-audiovisual-puzzle",
        "game_no": 10,
        "name": "拼图",
        "action_type": "视听力训练",
        "description": "展示拼图，乱序后要求恢复",
        "implementation_cost": "可实现，但不适合手机端",
        "resource_difficulty": "低",
    },
]


def instruction_text(item):
    return (
        f"{item['description']}\n\n"
        f"实现成本：{item['implementation_cost']}\n"
        f"资源难度：{item['resource_difficulty']}"
    )


def seed_game_actions(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    for item in GAME_ACTIONS:
        ActionLibraryItem.objects.update_or_create(
            source_key=item["source_key"],
            defaults={
                "name": item["name"],
                "training_type": "认知训练",
                "internal_type": "game",
                "action_type": item["action_type"],
                "instruction_text": instruction_text(item),
                "suggested_frequency": "1 次/周",
                "suggested_duration_minutes": 10,
                "default_difficulty": "",
                "video_url": "",
                "has_ai_supervision": False,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0009_prescriptionaction_weekly_target_count"),
    ]

    operations = [
        migrations.RunPython(seed_game_actions, migrations.RunPython.noop),
    ]
