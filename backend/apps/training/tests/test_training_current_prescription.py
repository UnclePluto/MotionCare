import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient

from apps.training.models import TrainingRecord
from apps.training.services import create_training_record


@pytest.mark.django_db
def test_training_requires_active_prescription(project_patient):
    with pytest.raises(ValidationError, match="当前无生效处方"):
        create_training_record(project_patient=project_patient, training_date="2026-05-06")


@pytest.mark.django_db
def test_training_uses_current_active_prescription(active_prescription, prescription_action):
    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date="2026-05-06",
        prescription_action=prescription_action,
        status="completed",
        actual_duration_minutes=20,
    )

    assert record.prescription == active_prescription
    assert record.prescription_action == prescription_action
    assert record.status == "completed"


@pytest.mark.django_db
def test_training_rejects_action_from_archived_prescription(
    active_prescription, prescription_action, doctor
):
    newer = Prescription.objects.create(
        project_patient=active_prescription.project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    active_prescription.status = Prescription.Status.ARCHIVED
    active_prescription.save(update_fields=["status"])

    with pytest.raises(ValidationError, match="只能录入当前生效处方下的动作"):
        create_training_record(
            project_patient=active_prescription.project_patient,
            training_date="2026-05-06",
            prescription_action=prescription_action,
            status="completed",
        )

    assert newer.status == Prescription.Status.ACTIVE


@pytest.mark.django_db
def test_training_create_ignores_malicious_controlled_foreign_key_ids(
    active_prescription,
    prescription_action,
    doctor,
    project,
    group,
):
    other_patient = Patient.objects.create(
        name="患者乙",
        phone="13900002222",
        primary_doctor=doctor,
    )
    other_project_patient = ProjectPatient.objects.create(
        project=project,
        patient=other_patient,
        group=group,
    )
    other_prescription = Prescription.objects.create(
        project_patient=other_project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    other_action = ActionLibraryItem.objects.create(
        name="错误动作",
        training_type="运动训练",
        internal_type=ActionLibraryItem.InternalType.MOTION,
        action_type="力量训练",
    )
    other_prescription_action = other_prescription.add_action_snapshot(other_action)

    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date="2026-05-06",
        prescription_action=prescription_action,
        status=TrainingRecord.Status.COMPLETED,
        prescription_id=other_prescription.id,
        prescription_action_id=other_prescription_action.id,
        project_patient_id=other_project_patient.id,
    )

    assert record.project_patient == active_prescription.project_patient
    assert record.prescription == active_prescription
    assert record.prescription_action == prescription_action


@pytest.mark.django_db
def test_training_create_rejects_invalid_game_result_form_data(active_prescription):
    game = ActionLibraryItem.objects.create(
        name="颜色顺序记忆",
        training_type="认知训练",
        internal_type=ActionLibraryItem.InternalType.GAME,
        action_type="记忆力训练",
    )
    game_action = active_prescription.add_action_snapshot(game)

    with pytest.raises(ValidationError, match="游戏原始明细必须是对象"):
        create_training_record(
            project_patient=active_prescription.project_patient,
            training_date="2026-05-06",
            prescription_action=game_action,
            status=TrainingRecord.Status.COMPLETED,
            form_data={"raw_detail": []},
        )

    assert not TrainingRecord.objects.filter(prescription_action=game_action).exists()


@pytest.mark.django_db
def test_training_create_accepts_real_game_raw_detail(active_prescription):
    game = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    game_action = active_prescription.add_action_snapshot(game)

    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date="2026-05-16",
        prescription_action=game_action,
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=10,
        score=90,
        form_data={
            "accuracy_rate": 90,
            "error_count": 1,
            "difficulty": "中等",
            "raw_detail": {
                "game_code": "game-memory-color-sequence",
                "ended_by": "timer",
                "ended_early": False,
                "prescribed_difficulty": "简单",
                "difficulty_adjusted": True,
                "difficulty_adjust_reason": "太简单，想提高难度",
                "upload_mode": "retry",
                "retry_count": 2,
                "total_retry_count": 12,
                "session_duration_seconds": 600,
                "suggested_duration_minutes": 10,
                "completed_units": 10,
                "correct_units": 9,
            },
        },
    )

    assert record.form_data["raw_detail"]["total_retry_count"] == 12


@pytest.mark.django_db
@pytest.mark.parametrize(
    "source_key",
    [
        "game-memory-pattern-sequence",
        "game-executive-category-switch",
        "game-audiovisual-sound-discrimination",
        "game-audiovisual-puzzle",
    ],
)
def test_training_create_accepts_remaining_official_game_codes(
    active_prescription,
    source_key,
):
    game = ActionLibraryItem.objects.get(source_key=source_key)
    game_action = active_prescription.add_action_snapshot(game, sort_order=9)

    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date="2026-05-16",
        prescription_action=game_action,
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=10,
        score=88,
        form_data={
            "accuracy_rate": 80,
            "error_count": 2,
            "difficulty": "中等",
            "raw_detail": {
                "game_code": source_key,
                "ended_by": "timer",
                "ended_early": False,
                "prescribed_difficulty": "中等",
                "difficulty_adjusted": False,
                "difficulty_adjust_reason": "",
                "upload_mode": "direct",
                "retry_count": 0,
                "total_retry_count": 0,
                "session_duration_seconds": 600,
                "suggested_duration_minutes": 10,
                "completed_units": 10,
                "correct_units": 8,
            },
        },
        note="",
    )

    assert record.prescription_action == game_action
    assert record.form_data["raw_detail"]["game_code"] == source_key


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("raw_detail", "message"),
    [
        ({"ended_by": "unknown"}, "游戏结束方式必须是 timer 或 manual"),
        ({"ended_early": "false"}, "游戏提前结束标记必须是布尔值"),
        ({"retry_count": -1}, "游戏补传次数必须是非负整数"),
        ({"total_retry_count": True}, "游戏累计补传次数必须是非负整数"),
        ({"upload_mode": "later"}, "游戏上传方式必须是 direct 或 retry"),
        ({"game_code": "wrong-game"}, "游戏编码必须匹配处方动作"),
        ({"completed_units": True}, "游戏会话数值必须是非负整数"),
    ],
)
def test_training_create_rejects_invalid_real_game_raw_detail(
    active_prescription,
    raw_detail,
    message,
):
    game = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    game_action = active_prescription.add_action_snapshot(game)

    with pytest.raises(ValidationError, match=message):
        create_training_record(
            project_patient=active_prescription.project_patient,
            training_date="2026-05-16",
            prescription_action=game_action,
            status=TrainingRecord.Status.COMPLETED,
            form_data={
                "accuracy_rate": 90,
                "error_count": 1,
                "difficulty": "中等",
                "raw_detail": raw_detail,
            },
        )


@pytest.mark.django_db
def test_training_create_rejects_game_code_when_action_has_no_source_key(active_prescription):
    game = ActionLibraryItem.objects.create(
        name="院内自定义游戏",
        training_type="认知训练",
        internal_type=ActionLibraryItem.InternalType.GAME,
        action_type="记忆力训练",
    )
    game_action = active_prescription.add_action_snapshot(game)

    with pytest.raises(ValidationError, match="游戏编码必须匹配处方动作"):
        create_training_record(
            project_patient=active_prescription.project_patient,
            training_date="2026-05-16",
            prescription_action=game_action,
            status=TrainingRecord.Status.COMPLETED,
            form_data={
                "raw_detail": {
                    "game_code": "game-memory-color-sequence",
                },
            },
        )


@pytest.mark.django_db
def test_training_create_allows_empty_string_for_optional_game_flags(active_prescription):
    game = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    game_action = active_prescription.add_action_snapshot(game)

    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date="2026-05-16",
        prescription_action=game_action,
        status=TrainingRecord.Status.COMPLETED,
        form_data={
            "raw_detail": {
                "ended_early": "",
            },
        },
    )

    assert record.form_data["raw_detail"]["ended_early"] == ""


@pytest.mark.django_db
def test_training_api_rejects_invalid_game_result_form_data(active_prescription, doctor):
    game = ActionLibraryItem.objects.create(
        name="颜色顺序记忆",
        training_type="认知训练",
        internal_type=ActionLibraryItem.InternalType.GAME,
        action_type="记忆力训练",
    )
    game_action = active_prescription.add_action_snapshot(game)
    client = APIClient()
    client.force_authenticate(user=doctor)

    response = client.post(
        "/api/training/",
        {
            "project_patient": active_prescription.project_patient_id,
            "prescription_action": game_action.id,
            "training_date": "2026-05-06",
            "status": TrainingRecord.Status.COMPLETED,
            "form_data": {"accuracy_rate": True},
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "正确率必须在 0 到 100 之间"
    assert not TrainingRecord.objects.filter(prescription_action=game_action).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["patch", "put"])
def test_training_record_update_methods_are_not_allowed(
    method,
    active_prescription,
    prescription_action,
    doctor,
):
    record = create_training_record(
        project_patient=active_prescription.project_patient,
        training_date="2026-05-06",
        prescription_action=prescription_action,
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=20,
    )
    client = APIClient()
    client.force_authenticate(user=doctor)

    response = getattr(client, method)(
        f"/api/training/{record.id}/",
        {"prescription_action": 999},
        format="json",
    )

    assert response.status_code == 405
    record.refresh_from_db()
    assert record.project_patient == active_prescription.project_patient
    assert record.prescription == active_prescription
    assert record.prescription_action == prescription_action
