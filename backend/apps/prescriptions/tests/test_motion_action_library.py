import pytest

from apps.prescriptions.models import ActionLibraryItem


@pytest.mark.django_db
def test_motion_actions_are_seeded_by_migration():
    actions = ActionLibraryItem.objects.filter(training_type="运动训练").order_by("source_key")

    assert actions.count() == 5
    assert list(actions.values_list("source_key", flat=True)) == [
        "motion-aerobic-high-knee",
        "motion-balance-sit-stand",
        "motion-resistance-leg-kickback",
        "motion-resistance-row",
        "motion-resistance-shoulder-press",
    ]

    sit_stand = ActionLibraryItem.objects.get(source_key="motion-balance-sit-stand")
    assert sit_stand.name == "坐站转移训练"
    assert sit_stand.internal_type == ActionLibraryItem.InternalType.MOTION
    assert sit_stand.action_type == "平衡训练"
    assert "找一把高度45CM的椅子" in sit_stand.instruction_text
    assert "起身时重心充分前移" in sit_stand.instruction_text
    assert sit_stand.suggested_frequency == "2 次/周"
    assert sit_stand.suggested_duration_minutes == 15
    assert sit_stand.has_ai_supervision is True


@pytest.mark.django_db
def test_action_snapshot_keeps_merged_instruction_and_video(project_patient, doctor):
    action = ActionLibraryItem.objects.create(
        source_key="custom-motion-test",
        name="测试动作",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="有氧训练",
        instruction_text="步骤一。\n\n要点：保持躯干稳定。",
        suggested_frequency="3 次/周",
        suggested_duration_minutes=20,
        video_url="https://example.com/video.mp4",
        has_ai_supervision=True,
    )
    prescription = project_patient.prescriptions.create(version=1, opened_by=doctor)

    snapshot = prescription.add_action_snapshot(
        action,
        weekly_frequency="3 次/周",
        duration_minutes=20,
        repetitions=None,
    )

    action.name = "动作库已改名"
    action.instruction_text = "动作库新文案"
    action.video_url = "https://example.com/new.mp4"
    action.save()

    snapshot.refresh_from_db()
    assert snapshot.action_name_snapshot == "测试动作"
    assert snapshot.action_instruction_snapshot == "步骤一。\n\n要点：保持躯干稳定。"
    assert snapshot.video_url_snapshot == "https://example.com/video.mp4"
    assert snapshot.has_ai_supervision_snapshot is True
    assert snapshot.weekly_frequency == "3 次/周"
