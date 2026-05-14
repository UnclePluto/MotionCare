from django.db import migrations


MOTION_ACTIONS = [
    {
        "source_key": "motion-aerobic-high-knee",
        "name": "椰林步道模拟（原地高抬腿+摆臂）",
        "action_type": "有氧训练",
        "instruction_text": (
            "双脚与肩同宽站立，躯干直立，双手自然垂于身体两侧。\n"
            "左侧大腿屈膝上抬，大腿平行地面，右侧手臂屈肘向前摆动。\n"
            "左腿放下，右侧大腿抬至水平高度，左手向前摆。\n"
            "双腿交替高抬腿，双臂协同前后摆动。\n\n"
            "动作要点：骨盆中立，不塌腰不驼背，抬腿髋部发力。"
        ),
        "suggested_frequency": "3 次/周",
        "suggested_duration_minutes": 20,
        "has_ai_supervision": True,
    },
    {
        "source_key": "motion-balance-sit-stand",
        "name": "坐站转移训练",
        "action_type": "平衡训练",
        "instruction_text": (
            "找一把高度45CM的椅子，坐稳；双脚平放与肩同宽，脚尖位于膝盖正下方。\n"
            "躯干前倾，重心前移，臀部缓慢抬离椅面。\n"
            "双腿发力站直，髋关节膝关节充分伸展。\n"
            "缓慢屈髋屈膝，轻缓坐下。\n\n"
            "动作要点：起身时重心充分前移，禁止用手臂撑椅子发力。"
        ),
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 15,
        "has_ai_supervision": True,
    },
    {
        "source_key": "motion-resistance-row",
        "name": "坐姿划船",
        "action_type": "抗阻训练",
        "instruction_text": (
            "用红/黄两档阻力，坐姿挺直，弹力带踩于双脚，双手握带。\n"
            "双手绕带，绕道手臂伸直，弹力带有阻力为止，拳心朝内。\n"
            "腰背挺直，沉肩，手臂加紧身体，屈肘后拉夹背。\n"
            "顶点处停顿 2 秒，缓慢回放至起始位。\n\n"
            "动作要点：躯干固定，用背部肌群发力，肩胛骨后缩，不耸肩不弯腰。"
        ),
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 10,
        "has_ai_supervision": True,
    },
    {
        "source_key": "motion-resistance-leg-kickback",
        "name": "腿部后踢",
        "action_type": "抗阻训练",
        "instruction_text": (
            "将弹力带一端固定在单侧脚踝处，另一端绑定在固定物体上。\n"
            "躯干直立，双腿自然站立，支撑腿站稳不动。\n"
            "绑有弹力带的发力侧，大腿向后缓慢后踢，感受大腿后侧收紧。\n"
            "顶峰处稍停顿，再缓慢控制回放至起始位，重复次数训练后，换腿练另一侧。\n\n"
            "动作要点：躯干固定不塌腰不晃胯，大腿后侧肌群发力，不是腰部代偿。"
        ),
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 10,
        "has_ai_supervision": False,
    },
    {
        "source_key": "motion-resistance-shoulder-press",
        "name": "肩部推举",
        "action_type": "抗阻训练",
        "instruction_text": (
            "双脚与肩同宽，踩住弹力带中间位置，踩实防滑。\n"
            "双手分别抓握弹力带两端，屈肘小臂抬起，手置于肩侧耳旁。\n"
            "核心收紧、腰背挺直，双手发力垂直向上推举，手臂接近伸直不锁肘。\n"
            "顶点稍停，控制速度缓慢下放回到肩侧，循环重复。\n\n"
            "动作要点：全程收腹立腰，身体不后仰、不挺肚子，避免斜方肌代偿。"
        ),
        "suggested_frequency": "2 次/周",
        "suggested_duration_minutes": 10,
        "has_ai_supervision": False,
    },
]


def seed_motion_actions(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    for item in MOTION_ACTIONS:
        ActionLibraryItem.objects.update_or_create(
            source_key=item["source_key"],
            defaults={
                **item,
                "training_type": "运动训练",
                "internal_type": "motion",
                "is_active": True,
            },
        )


def unseed_motion_actions(apps, schema_editor):
    ActionLibraryItem = apps.get_model("prescriptions", "ActionLibraryItem")
    ActionLibraryItem.objects.filter(
        source_key__in=[item["source_key"] for item in MOTION_ACTIONS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("prescriptions", "0003_motion_prescription_fields"),
    ]

    operations = [
        migrations.RunPython(seed_motion_actions, unseed_motion_actions),
    ]
