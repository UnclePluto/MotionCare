import pytest

from apps.prescriptions.models import ActionLibraryItem, Prescription


@pytest.mark.django_db
def test_game_actions_are_seeded_by_migration():
    actions = ActionLibraryItem.objects.filter(
        internal_type=ActionLibraryItem.InternalType.GAME
    ).order_by("source_key")

    assert actions.count() == 6
    assert list(actions.values_list("source_key", flat=True)) == [
        "game-audiovisual-puzzle",
        "game-audiovisual-sound-discrimination",
        "game-executive-category-switch",
        "game-executive-inhibition",
        "game-memory-color-sequence",
        "game-memory-pattern-sequence",
    ]

    color = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    assert color.name == "颜色顺序记忆"
    assert color.training_type == "认知训练"
    assert color.internal_type == ActionLibraryItem.InternalType.GAME
    assert color.action_type == "记忆力训练"
    assert color.instruction_text == "按顺序点击变色方块\n\n实现成本：可实现\n资源难度：低"
    assert color.suggested_frequency == "1 次/周"
    assert color.suggested_duration_minutes == 10
    assert color.has_ai_supervision is False
    assert color.is_active is True


@pytest.mark.django_db
def test_action_library_endpoint_filters_game_actions(client, doctor):
    client.force_login(doctor)

    response = client.get(
        "/api/prescriptions/actions/",
        {"internal_type": ActionLibraryItem.InternalType.GAME},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 6
    assert {row["internal_type"] for row in body} == {"game"}
    assert {row["training_type"] for row in body} == {"认知训练"}
    assert "颜色顺序记忆" in {row["name"] for row in body}


@pytest.mark.django_db
def test_game_action_snapshot_keeps_prescription_fields(project_patient, doctor):
    action = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    prescription = Prescription.objects.create(
        project_patient=project_patient,
        version=1,
        opened_by=doctor,
    )

    snapshot = prescription.add_action_snapshot(
        action,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=12,
        difficulty="中",
        notes="从简单难度开始",
    )

    action.name = "动作库已改名"
    action.instruction_text = "动作库新说明"
    action.save(update_fields=["name", "instruction_text", "updated_at"])

    snapshot.refresh_from_db()
    assert snapshot.action_name_snapshot == "颜色顺序记忆"
    assert snapshot.training_type_snapshot == "认知训练"
    assert snapshot.internal_type_snapshot == "game"
    assert snapshot.action_type_snapshot == "记忆力训练"
    assert "按顺序点击变色方块" in snapshot.action_instruction_snapshot
    assert snapshot.weekly_frequency == "2 次/周"
    assert snapshot.weekly_target_count == 2
    assert snapshot.duration_minutes == 12
    assert snapshot.difficulty == "中"
    assert snapshot.notes == "从简单难度开始"
