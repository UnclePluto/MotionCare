import importlib

import pytest
from django.apps import apps as django_apps

from apps.prescriptions.action_library import (
    MOTION_ACTION_VIDEO_OBJECT_KEYS,
    OFFICIAL_MOTION_ACTION_SOURCE_KEYS,
)
from apps.prescriptions.models import ActionLibraryItem
from apps.prescriptions.motion_videos import MotionVideoResolution


def test_reverse_instruction_split_handles_leading_key_points_only():
    migration = importlib.import_module(
        "apps.prescriptions.migrations.0003_motion_prescription_fields"
    )

    assert migration.split_instruction_text_for_reverse("步骤一。\n\n动作要点：保持稳定") == (
        "步骤一。",
        "保持稳定",
    )
    assert migration.split_instruction_text_for_reverse("动作要点：保持稳定") == (
        "",
        "保持稳定",
    )
    assert migration.split_instruction_text_for_reverse("步骤一。") == ("步骤一。", "")
    assert migration.split_instruction_text_for_reverse("") == ("", "")


def test_official_motion_video_catalog_is_complete():
    assert OFFICIAL_MOTION_ACTION_SOURCE_KEYS == frozenset(
        MOTION_ACTION_VIDEO_OBJECT_KEYS
    )
    assert set(MOTION_ACTION_VIDEO_OBJECT_KEYS.values()) == {
        f"motion-action-videos/v1/{source_key}.mp4"
        for source_key in OFFICIAL_MOTION_ACTION_SOURCE_KEYS
    }


@pytest.mark.django_db
def test_prescription_snapshot_copies_motion_video_object_key(project_patient, doctor):
    action = ActionLibraryItem.objects.get(source_key="motion-resistance-row")
    action.video_object_key = MOTION_ACTION_VIDEO_OBJECT_KEYS[action.source_key]
    action.save(update_fields=["video_object_key", "updated_at"])
    prescription = project_patient.prescriptions.create(version=19, opened_by=doctor)

    snapshot = prescription.add_action_snapshot(action, duration_minutes=10)

    assert snapshot.video_object_key_snapshot == action.video_object_key


@pytest.mark.django_db
def test_data_migration_replays_frozen_v1_keys_when_runtime_catalog_changes(
    project_patient,
    doctor,
    monkeypatch,
):
    action = ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press")
    action.video_url = "https://old.example.com/shoulder.mp4"
    action.video_object_key = ""
    action.save()
    active = project_patient.prescriptions.create(version=20, opened_by=doctor)
    archived = project_patient.prescriptions.create(version=21, opened_by=doctor)
    active_action = active.add_action_snapshot(action, duration_minutes=10)
    archived_action = archived.add_action_snapshot(action, duration_minutes=10)

    migration = importlib.import_module(
        "apps.prescriptions.migrations.0012_motion_action_video_object_keys"
    )
    monkeypatch.setitem(
        MOTION_ACTION_VIDEO_OBJECT_KEYS,
        action.source_key,
        "motion-action-videos/v2/runtime-only.mp4",
    )
    migration.backfill_motion_action_video_keys(django_apps, None)

    action.refresh_from_db()
    active_action.refresh_from_db()
    archived_action.refresh_from_db()
    expected = (
        "motion-action-videos/v1/"
        "motion-resistance-shoulder-press.mp4"
    )
    assert action.video_object_key == expected
    assert action.video_url == ""
    assert active_action.video_object_key_snapshot == expected
    assert archived_action.video_object_key_snapshot == expected
    assert active_action.video_url_snapshot == ""
    assert archived_action.video_url_snapshot == ""


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


@pytest.mark.django_db
def test_action_library_endpoint_uses_motion_fields(client, doctor):
    client.force_login(doctor)

    response = client.get("/api/prescriptions/actions/")

    assert response.status_code == 200
    first = response.json()[0]
    assert "instruction_text" in first
    assert "has_ai_supervision" in first
    assert "suggested_sets" not in first
    assert "suggested_repetitions" not in first
    assert "parameter_mode" not in first
    assert "execution_description" not in first
    assert "key_points" not in first


@pytest.mark.django_db
def test_doctor_action_serializers_return_signed_urls_and_configuration(
    client, doctor, project_patient, monkeypatch
):
    client.force_login(doctor)
    action = ActionLibraryItem.objects.get(source_key="motion-resistance-row")
    prescription = project_patient.prescriptions.create(version=18, opened_by=doctor)
    snapshot = prescription.add_action_snapshot(action, duration_minutes=10)
    monkeypatch.setattr(
        "apps.prescriptions.serializers.resolve_motion_video_url",
        lambda *args, **kwargs: MotionVideoResolution(
            url="https://signed.example.com/row.mp4", unavailable=False
        ),
        raising=False,
    )

    action_response = client.get("/api/prescriptions/actions/")
    prescription_response = client.get("/api/prescriptions/prescription-actions/")

    assert action_response.status_code == 200
    action_row = next(
        row
        for row in action_response.json()
        if row["source_key"] == "motion-resistance-row"
    )
    assert action_row["video_url"] == "https://signed.example.com/row.mp4"
    assert action_row["video_configured"] is True
    assert prescription_response.status_code == 200
    snapshot_row = next(
        row for row in prescription_response.json() if row["id"] == snapshot.id
    )
    assert snapshot_row["video_url_snapshot"] == "https://signed.example.com/row.mp4"


@pytest.mark.django_db
def test_doctor_action_serializers_degrade_when_video_signing_raises(
    client, doctor, project_patient, monkeypatch
):
    client.force_login(doctor)
    action = ActionLibraryItem.objects.get(source_key="motion-resistance-row")
    prescription = project_patient.prescriptions.create(version=17, opened_by=doctor)
    snapshot = prescription.add_action_snapshot(action, duration_minutes=10)

    def raise_signing_error(*args, **kwargs):
        raise RuntimeError("签名服务不可用")

    monkeypatch.setattr(
        "apps.prescriptions.serializers.resolve_motion_video_url",
        raise_signing_error,
    )

    action_response = client.get("/api/prescriptions/actions/")
    prescription_response = client.get("/api/prescriptions/prescription-actions/")

    assert action_response.status_code == 200
    action_row = next(
        row
        for row in action_response.json()
        if row["source_key"] == "motion-resistance-row"
    )
    assert action_row["video_url"] == ""
    assert action_row["video_configured"] is True
    assert prescription_response.status_code == 200
    snapshot_row = next(
        row for row in prescription_response.json() if row["id"] == snapshot.id
    )
    assert snapshot_row["video_url_snapshot"] == ""


@pytest.mark.django_db
def test_action_library_endpoint_returns_only_official_seeded_actions(client, doctor):
    client.force_login(doctor)
    ActionLibraryItem.objects.create(
        name="坐立训练",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="平衡训练",
    )
    ActionLibraryItem.objects.create(
        source_key="custom-motion-test",
        name="测试动作",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="平衡训练",
    )

    response = client.get("/api/prescriptions/actions/")

    assert response.status_code == 200
    source_keys = {row["source_key"] for row in response.json()}
    assert source_keys == {
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
    assert "坐立训练" not in {row["name"] for row in response.json()}
    assert "测试动作" not in {row["name"] for row in response.json()}


@pytest.mark.django_db
def test_prescription_action_endpoint_uses_motion_snapshot_fields(
    client, doctor, project_patient
):
    client.force_login(doctor)
    action = ActionLibraryItem.objects.create(
        source_key="serializer-motion-test",
        name="序列化测试动作",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="有氧训练",
        instruction_text="序列化测试动作说明",
        suggested_frequency="3 次/周",
        suggested_duration_minutes=20,
        video_url="https://example.com/serializer-motion.mp4",
        has_ai_supervision=True,
    )
    prescription = project_patient.prescriptions.create(version=1, opened_by=doctor)
    snapshot = prescription.add_action_snapshot(
        action,
        weekly_frequency="3 次/周",
        duration_minutes=20,
    )

    response = client.get("/api/prescriptions/prescription-actions/")

    assert response.status_code == 200
    row = next(item for item in response.json() if item["id"] == snapshot.id)
    assert row["action_instruction_snapshot"] == action.instruction_text
    assert row["weekly_frequency"] == "3 次/周"
    assert "sets" not in row
    assert "repetitions" not in row
    assert "execution_description_snapshot" not in row
    assert "frequency" not in row
