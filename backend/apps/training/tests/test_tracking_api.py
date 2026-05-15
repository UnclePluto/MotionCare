from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.training.models import TrainingRecord


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _doctor(phone="13800002222", name="医生乙"):
    return User.objects.create_user(
        phone=phone,
        password="pass123456",
        name=name,
        role=User.Role.DOCTOR,
    )


def _admin(phone="13800003333", name="管理员"):
    return User.objects.create_user(
        phone=phone,
        password="pass123456",
        name=name,
        role=User.Role.ADMIN,
    )


def _patient(doctor, name="患者乙", phone="13900002222"):
    return Patient.objects.create(
        name=name,
        gender=Patient.Gender.UNKNOWN,
        age=72,
        phone=phone,
        primary_doctor=doctor,
    )


def _project_patient(doctor, patient, project_name="研究项目", group_name="干预组"):
    project = StudyProject.objects.create(name=project_name, created_by=doctor)
    group = StudyGroup.objects.create(project=project, name=group_name, target_ratio=1)
    return ProjectPatient.objects.create(project=project, patient=patient, group=group)


def _active_prescription(project_patient, doctor, version=1):
    return Prescription.objects.create(
        project_patient=project_patient,
        version=version,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )


def _action(
    prescription,
    *,
    name="坐立训练",
    internal_type=ActionLibraryItem.InternalType.MOTION,
    action_type="平衡训练",
    weekly_target_count=2,
    sort_order=0,
):
    item = ActionLibraryItem.objects.create(
        name=name,
        training_type="康复训练",
        internal_type=internal_type,
        action_type=action_type,
    )
    return prescription.add_action_snapshot(
        item,
        weekly_frequency=f"{weekly_target_count} 次/周",
        duration_minutes=10,
        weekly_target_count=weekly_target_count,
        sort_order=sort_order,
    )


def _record(
    project_patient,
    prescription,
    action,
    *,
    training_date,
    status=TrainingRecord.Status.COMPLETED,
    duration=10,
    score=None,
    form_data=None,
    note="",
):
    return TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=prescription,
        prescription_action=action,
        training_date=training_date,
        status=status,
        actual_duration_minutes=duration,
        score=score,
        form_data=form_data or {},
        note=note,
    )


@pytest.mark.django_db
def test_patient_search_returns_accessible_patient_summaries(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    today = timezone.localdate()
    _record(
        project_patient,
        active_prescription,
        prescription_action,
        training_date=today,
        status=TrainingRecord.Status.COMPLETED,
    )
    _record(
        project_patient,
        active_prescription,
        prescription_action,
        training_date=today - timezone.timedelta(days=1),
        status=TrainingRecord.Status.PARTIAL,
    )
    _record(
        project_patient,
        active_prescription,
        prescription_action,
        training_date=today - timezone.timedelta(days=31),
        status=TrainingRecord.Status.COMPLETED,
    )
    other_doctor = _doctor(phone="13800004444", name="其他医生")
    other_patient = _patient(other_doctor, name="不可见患者", phone="13900004444")
    _project_patient(other_doctor, other_patient, project_name="其他医生项目")

    response = _client(doctor).get("/api/training/tracking/patients/", {"q": "患者甲"})

    assert response.status_code == 200, response.data
    assert len(response.data) == 1
    row = response.data[0]
    assert row["patient"] == {
        "id": project_patient.patient_id,
        "name": "患者甲",
        "phone_masked": "139****1111",
    }
    assert row["project_count"] == 1
    assert row["last_training_at"] == today.isoformat()
    assert row["last_30_days_completed_count"] == 1

    phone_response = _client(doctor).get(
        "/api/training/tracking/patients/",
        {"q": "13900001111"},
    )
    assert [item["patient"]["id"] for item in phone_response.data] == [
        project_patient.patient_id
    ]

    admin_response = _client(_admin()).get("/api/training/tracking/patients/")
    admin_patient_ids = {item["patient"]["id"] for item in admin_response.data}
    assert {project_patient.patient_id, other_patient.id}.issubset(admin_patient_ids)


@pytest.mark.django_db
def test_tracking_detail_returns_default_project_current_prescription_trends_and_game_summary(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    today = timezone.localdate()
    prescription_action.weekly_target_count = 2
    prescription_action.save(update_fields=["weekly_target_count", "updated_at"])
    game_action = _action(
        active_prescription,
        name="颜色记忆",
        internal_type=ActionLibraryItem.InternalType.GAME,
        action_type="认知游戏",
        weekly_target_count=2,
        sort_order=2,
    )
    _record(
        project_patient,
        active_prescription,
        prescription_action,
        training_date=today,
        duration=20,
        note="第一次运动",
    )
    _record(
        project_patient,
        active_prescription,
        prescription_action,
        training_date=today,
        duration=15,
        note="第二次运动",
    )
    _record(
        project_patient,
        active_prescription,
        game_action,
        training_date=today,
        duration=8,
        score=Decimal("90.00"),
        form_data={
            "accuracy_rate": 92,
            "error_count": 3,
            "difficulty": "简单",
            "raw_detail": {"rounds": 6},
        },
        note="游戏顺利",
    )
    _record(
        project_patient,
        active_prescription,
        game_action,
        training_date=today - timezone.timedelta(days=10),
        duration=9,
        score=Decimal("80.00"),
        form_data={
            "accuracy_rate": 80,
            "error_count": 2,
            "difficulty": "普通",
        },
    )

    response = _client(doctor).get(
        f"/api/training/tracking/patients/{project_patient.patient_id}/"
    )

    assert response.status_code == 200, response.data
    assert response.data["patient"]["phone_masked"] == "139****1111"
    assert response.data["selected_project_patient"]["id"] == project_patient.id
    assert response.data["project_patients"] == [
        {
            "id": project_patient.id,
            "project": project_patient.project_id,
            "project_name": project_patient.project.name,
            "project_status": project_patient.project.status,
            "group": project_patient.group_id,
            "group_name": project_patient.group.name,
            "enrolled_at": project_patient.enrolled_at.isoformat(),
        }
    ]
    assert response.data["current_prescription"] == {
        "id": active_prescription.id,
        "version": 1,
        "status": Prescription.Status.ACTIVE,
        "effective_at": active_prescription.effective_at.isoformat(),
    }

    completion_by_action = {
        item["prescription_action"]: item for item in response.data["prescription_completion"]
    }
    assert completion_by_action[prescription_action.id]["completed_count"] == 2
    assert completion_by_action[prescription_action.id]["completion_rate"] == 1.0
    assert completion_by_action[game_action.id]["completed_count"] == 1
    assert completion_by_action[game_action.id]["completion_rate"] == 0.5
    assert completion_by_action[game_action.id]["internal_type"] == "game"

    trend = response.data["trend"]
    assert len(trend["daily"]) == 30
    assert len(trend["moving_average"]) == 30
    assert trend["daily"][-1] == {
        "date": today.isoformat(),
        "completed_count": 3,
        "duration_minutes": 43,
        "game_average_score": 90.0,
    }
    assert trend["moving_average"][-1]["date"] == today.isoformat()
    assert trend["moving_average"][-1]["completed_count_avg"] > 0
    assert trend["weekly"]
    assert {"week_start", "week_end", "completed_count", "duration_minutes", "game_average_score"} <= set(
        trend["weekly"][0]
    )

    game_summary = response.data["game_summary"]
    assert game_summary["average_score"] == 85.0
    assert game_summary["average_accuracy_rate"] == 86.0
    assert game_summary["total_error_count"] == 5
    assert game_summary["by_game"] == [
        {
            "prescription_action": game_action.id,
            "action_name": "颜色记忆",
            "record_count": 2,
            "average_score": 85.0,
            "average_accuracy_rate": 86.0,
            "recent_record_at": today.isoformat(),
        }
    ]

    recent = response.data["recent_records"]
    assert len(recent) == 4
    latest_game = next(item for item in recent if item["prescription_action"] == game_action.id)
    assert latest_game["score"] == 90.0
    assert latest_game["game_accuracy_rate"] == 92.0
    assert latest_game["game_error_count"] == 3
    assert latest_game["game_difficulty"] == "简单"
    assert latest_game["note"] == "游戏顺利"


@pytest.mark.django_db
def test_tracking_detail_switches_project_patient_and_defaults_by_recent_training_or_enrollment(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    patient = project_patient.patient
    today = timezone.localdate()
    second_pp = _project_patient(doctor, patient, project_name="第二研究", group_name="对照组")
    second_prescription = _active_prescription(second_pp, doctor, version=1)
    second_action = _action(second_prescription, name="第二项目动作")
    _record(
        second_pp,
        second_prescription,
        second_action,
        training_date=today - timezone.timedelta(days=1),
    )

    default_response = _client(doctor).get(f"/api/training/tracking/patients/{patient.id}/")
    assert default_response.status_code == 200, default_response.data
    assert default_response.data["selected_project_patient"]["id"] == second_pp.id

    switched_response = _client(doctor).get(
        f"/api/training/tracking/patients/{patient.id}/",
        {"project_patient": project_patient.id},
    )
    assert switched_response.status_code == 200, switched_response.data
    assert switched_response.data["selected_project_patient"]["id"] == project_patient.id

    no_training_patient = _patient(doctor, name="无训练患者", phone="13900005555")
    older_pp = _project_patient(doctor, no_training_patient, project_name="旧项目")
    newer_pp = _project_patient(doctor, no_training_patient, project_name="新项目")
    ProjectPatient.objects.filter(pk=older_pp.pk).update(
        enrolled_at=timezone.now() - timezone.timedelta(days=3)
    )
    ProjectPatient.objects.filter(pk=newer_pp.pk).update(enrolled_at=timezone.now())

    no_training_response = _client(doctor).get(
        f"/api/training/tracking/patients/{no_training_patient.id}/"
    )
    assert no_training_response.status_code == 200, no_training_response.data
    assert no_training_response.data["selected_project_patient"]["id"] == newer_pp.id


@pytest.mark.django_db
def test_tracking_detail_hides_inaccessible_patient_and_rejects_invalid_project_patient(
    doctor,
    project_patient,
):
    other_doctor = _doctor(phone="13800006666", name="其他医生")
    other_patient = _patient(other_doctor, name="其他患者", phone="13900006666")
    other_pp = _project_patient(other_doctor, other_patient, project_name="其他项目")

    inaccessible_response = _client(doctor).get(
        f"/api/training/tracking/patients/{other_patient.id}/"
    )
    assert inaccessible_response.status_code == 404

    mismatched_response = _client(doctor).get(
        f"/api/training/tracking/patients/{project_patient.patient_id}/",
        {"project_patient": other_pp.id},
    )
    assert mismatched_response.status_code == 404

    admin_response = _client(_admin()).get(
        f"/api/training/tracking/patients/{other_patient.id}/",
        {"project_patient": other_pp.id},
    )
    assert admin_response.status_code == 200, admin_response.data
    assert admin_response.data["selected_project_patient"]["id"] == other_pp.id


@pytest.mark.django_db
def test_tracking_detail_validates_range_and_returns_seven_day_trend(
    doctor,
    project_patient,
):
    invalid_response = _client(doctor).get(
        f"/api/training/tracking/patients/{project_patient.patient_id}/",
        {"range": "bad"},
    )
    assert invalid_response.status_code == 400

    response = _client(doctor).get(
        f"/api/training/tracking/patients/{project_patient.patient_id}/",
        {"range": "7d"},
    )

    assert response.status_code == 200, response.data
    assert len(response.data["trend"]["daily"]) == 7
    assert len(response.data["trend"]["moving_average"]) == 7


@pytest.mark.django_db
def test_tracking_detail_returns_empty_prescription_sections_without_active_prescription(
    doctor,
):
    patient = _patient(doctor, name="暂未开方患者", phone="13900007777")
    project_patient = _project_patient(doctor, patient, project_name="暂未开方项目")

    response = _client(doctor).get(f"/api/training/tracking/patients/{patient.id}/")

    assert response.status_code == 200, response.data
    assert response.data["selected_project_patient"]["id"] == project_patient.id
    assert response.data["current_prescription"] is None
    assert response.data["prescription_completion"] == []
    assert len(response.data["trend"]["daily"]) == 30
    assert response.data["game_summary"] == {
        "average_score": None,
        "average_accuracy_rate": None,
        "total_error_count": 0,
        "by_game": [],
    }
