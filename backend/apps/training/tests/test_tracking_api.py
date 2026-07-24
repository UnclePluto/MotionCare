from decimal import Decimal
from datetime import UTC, datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.training.models import TrainingRecord
from apps.training.tracking import list_patient_tracking_summaries, serialize_project_patient
from apps.wearables.models import (
    WearableBinding,
    WearableDailySummary,
    WearableDevice,
    WearableSyncRun,
)


def _sql_datetime_param_matches(value, expected):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return False
    if not isinstance(value, datetime):
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    if expected.tzinfo is None:
        expected = expected.replace(tzinfo=UTC)
    return value.astimezone(UTC) == expected.astimezone(UTC)


@pytest.mark.parametrize(
    "value",
    [
        "2026-07-01 00:00:00",
        datetime(2026, 7, 1, tzinfo=UTC),
    ],
)
def test_sql_datetime_param_matcher_accepts_sqlite_and_psycopg_shapes(value):
    assert _sql_datetime_param_matches(
        value,
        datetime(2026, 7, 1, tzinfo=UTC),
    )


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


@pytest.mark.django_db
def test_tracking_project_patient_includes_authoritative_project_completed_at(doctor):
    patient = _patient(doctor)
    project_patient = _project_patient(doctor, patient)
    completed_at = datetime(2026, 7, 23, 4, tzinfo=UTC)
    project_patient.project.completed_at = completed_at
    project_patient.project.save(update_fields=["completed_at"])

    assert serialize_project_patient(project_patient)["project_completed_at"] == completed_at.isoformat()


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
def test_tracking_recent_record_includes_video_analysis_summary(
    doctor, project_patient, active_prescription, prescription_action
):
    from apps.training.models import MotionAnalysisJob, TrainingVideo

    record = _record(
        project_patient,
        active_prescription,
        prescription_action,
        training_date=timezone.localdate(),
    )
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_record=record,
        bucket="motioncare",
        object_key="tracking/video.mp4",
        object_hash="final-hash",
        content_type="video/mp4",
        size_bytes=10,
        duration_seconds=30,
        status=TrainingVideo.Status.ATTACHED,
    )
    MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=record,
        project_patient=project_patient,
        prescription_action=prescription_action,
        status=MotionAnalysisJob.Status.SUCCEEDED,
        total_count=8,
        standard_count=6,
        nonstandard_count=2,
    )

    response = _client(doctor).get(
        f"/api/training/tracking/patients/{project_patient.patient_id}/"
    )
    recent = response.data["recent_records"][0]
    assert recent["video_id"] == video.id
    assert recent["latest_analysis_status"] == "succeeded"
    assert (recent["analysis_total_count"], recent["analysis_standard_count"]) == (8, 6)


@pytest.mark.django_db
def test_tracking_hides_video_until_server_cleanup_is_complete(
    doctor, project_patient, active_prescription, prescription_action
):
    from apps.training.models import TrainingVideo

    record = _record(
        project_patient,
        active_prescription,
        prescription_action,
        training_date=timezone.localdate(),
    )
    TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_record=record,
        bucket="motioncare",
        object_key="tracking/cleaning.mp4",
        object_hash="final-hash",
        content_type="video/mp4",
        size_bytes=10,
        duration_seconds=30,
        status=TrainingVideo.Status.CLEANING,
    )

    response = _client(doctor).get(
        f"/api/training/tracking/patients/{project_patient.patient_id}/"
    )

    recent = response.data["recent_records"][0]
    assert recent["video_id"] is None
    assert recent["video_status"] == TrainingVideo.Status.CLEANING


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
def test_tracking_summary_includes_global_wearable_binding_and_completed_day_completeness(
    doctor, project_patient
):
    device = WearableDevice.objects.create(
        provider="miwitracker", external_device_id="tracking-device", identifier_type="device_id", model="TEST", short_code="1288"
    )
    WearableBinding.objects.create(
        patient=project_patient.patient,
        device=device,
        bound_at=datetime(2026, 6, 24, 16, tzinfo=UTC),  # 上海 6 月 25 日零点
        bound_by=doctor,
    )
    WearableDailySummary.objects.create(
        patient=project_patient.patient,
        record_date=timezone.datetime(2026, 7, 23).date(),
        heart_rate_count=1,
    )

    rows = list_patient_tracking_summaries(doctor, today=timezone.datetime(2026, 7, 24).date())
    row = next(item for item in rows if item["patient"]["id"] == project_patient.patient_id)

    assert row["wearable"] == {
        "is_bound": True,
        "device_short_code": "1288",
        "last_sync_at": None,
        "last_30_days_data_completeness": 3.45,
    }


@pytest.mark.django_db
def test_tracking_completeness_uses_only_full_bound_days_and_never_duplicates_multi_project_patient(
    doctor, project_patient
):
    today = timezone.datetime(2026, 7, 24).date()
    patient = project_patient.patient
    second_project = StudyProject.objects.create(name="第二研究", created_by=doctor)
    second_group = StudyGroup.objects.create(project=second_project, name="对照组", target_ratio=1)
    ProjectPatient.objects.create(project=second_project, patient=patient, group=second_group)
    full_device = WearableDevice.objects.create(
        provider="miwitracker", external_device_id="complete-device", identifier_type="device_id", model="TEST", short_code="1289"
    )
    WearableBinding.objects.create(
        patient=patient, device=full_device, bound_at=datetime(2026, 6, 23, 16, tzinfo=UTC), bound_by=doctor
    )
    WearableDailySummary.objects.create(patient=patient, record_date=timezone.datetime(2026, 7, 23).date(), steps=100, steps_attribution_status="attributed")

    no_data_patient = _patient(doctor, name="无数据", phone="13900008881")
    no_data_pp = _project_patient(doctor, no_data_patient, project_name="无数据项目")
    no_data_device = WearableDevice.objects.create(
        provider="miwitracker", external_device_id="no-data-device", identifier_type="device_id", model="TEST", short_code="1290"
    )
    WearableBinding.objects.create(patient=no_data_patient, device=no_data_device, bound_at=datetime(2026, 6, 23, 16, tzinfo=UTC), bound_by=doctor)

    half_day_patient = _patient(doctor, name="半日", phone="13900008882")
    half_day_pp = _project_patient(doctor, half_day_patient, project_name="半日项目")
    half_day_device = WearableDevice.objects.create(
        provider="miwitracker", external_device_id="half-day-device", identifier_type="device_id", model="TEST", short_code="1291"
    )
    WearableBinding.objects.create(patient=half_day_patient, device=half_day_device, bound_at=datetime(2026, 7, 23, 4, tzinfo=UTC), bound_by=doctor)

    rows = list_patient_tracking_summaries(doctor, today=today)
    by_patient = {item["patient"]["id"]: item for item in rows}

    assert len([item for item in rows if item["patient"]["id"] == patient.id]) == 1
    assert by_patient[patient.id]["wearable"]["last_30_days_data_completeness"] == 3.33
    assert by_patient[no_data_pp.patient_id]["wearable"]["last_30_days_data_completeness"] == 0.0
    assert by_patient[half_day_pp.patient_id]["wearable"]["last_30_days_data_completeness"] is None


@pytest.mark.django_db
def test_tracking_summary_isolates_last_sync_when_device_switches_from_patient_a_to_b(
    doctor, project_patient
):
    today = datetime(2026, 7, 24).date()
    switch_at = datetime(2026, 7, 20, tzinfo=UTC)
    patient_b = _patient(
        doctor,
        name="换绑患者乙",
        phone="13900008883",
    )
    project_patient_b = _project_patient(
        doctor,
        patient_b,
        project_name="换绑患者乙研究",
    )
    shared_device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="tracking-shared-device",
        identifier_type="device_id",
        model="TEST",
        short_code="1292",
    )
    WearableBinding.objects.create(
        patient=project_patient.patient,
        device=shared_device,
        bound_at=datetime(2026, 6, 20, tzinfo=UTC),
        unbound_at=switch_at,
        bound_by=doctor,
        unbound_by=doctor,
    )
    old_run = WearableSyncRun.objects.create(
        device=shared_device,
        metric_type="heart_rate",
        status=WearableSyncRun.Status.SUCCEEDED,
    )
    WearableSyncRun.objects.filter(pk=old_run.pk).update(
        created_at=datetime(2026, 7, 19, 23, tzinfo=UTC)
    )
    WearableBinding.objects.create(
        patient=patient_b,
        device=shared_device,
        bound_at=switch_at,
        bound_by=doctor,
    )

    before_new_run = list_patient_tracking_summaries(doctor, today=today)
    before_by_patient = {row["patient"]["id"]: row["wearable"] for row in before_new_run}

    new_run_at = datetime(2026, 7, 20, 1, tzinfo=UTC)
    new_run = WearableSyncRun.objects.create(
        device=shared_device,
        metric_type="heart_rate",
        status=WearableSyncRun.Status.SUCCEEDED,
    )
    WearableSyncRun.objects.filter(pk=new_run.pk).update(created_at=new_run_at)
    after_new_run = list_patient_tracking_summaries(doctor, today=today)
    after_by_patient = {row["patient"]["id"]: row["wearable"] for row in after_new_run}

    assert before_by_patient[project_patient.patient_id]["is_bound"] is False
    assert before_by_patient[project_patient_b.patient_id]["device_short_code"] == "1292"
    assert before_by_patient[project_patient_b.patient_id]["last_sync_at"] is None
    assert after_by_patient[project_patient_b.patient_id]["last_sync_at"] == new_run_at.astimezone(
        timezone.get_fixed_timezone(480)
    ).isoformat()


@pytest.mark.django_db
def test_tracking_list_query_count_is_constant_and_excludes_hidden_patient(
    doctor, project_patient
):
    today = datetime(2026, 7, 24).date()
    first_device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="query-count-device-0",
        identifier_type="device_id",
        model="TEST",
        short_code="1300",
    )
    WearableBinding.objects.create(
        patient=project_patient.patient,
        device=first_device,
        bound_at=datetime(2026, 6, 20, tzinfo=UTC),
        bound_by=doctor,
    )

    with CaptureQueriesContext(connection) as one_patient_queries:
        one_patient_rows = list_patient_tracking_summaries(doctor, today=today)

    visible_patient_ids = {project_patient.patient_id}
    for index in range(1, 6):
        patient = _patient(
            doctor,
            name=f"可见患者{index}",
            phone=f"13900009{index:03d}",
        )
        _project_patient(doctor, patient, project_name=f"可见研究{index}")
        device = WearableDevice.objects.create(
            provider="miwitracker",
            external_device_id=f"query-count-device-{index}",
            identifier_type="device_id",
            model="TEST",
            short_code=f"{1300 + index:04d}",
        )
        WearableBinding.objects.create(
            patient=patient,
            device=device,
            bound_at=datetime(2026, 6, 20, tzinfo=UTC),
            bound_by=doctor,
        )
        visible_patient_ids.add(patient.id)

    second_project = StudyProject.objects.create(name="同患者第二研究", created_by=doctor)
    second_group = StudyGroup.objects.create(
        project=second_project,
        name="同患者第二组",
        target_ratio=1,
    )
    ProjectPatient.objects.create(
        project=second_project,
        patient=project_patient.patient,
        group=second_group,
    )

    other_doctor = _doctor(phone="13800009999", name="不可见医生")
    hidden_patient = _patient(
        other_doctor,
        name="不可见患者",
        phone="13900009999",
    )
    _project_patient(other_doctor, hidden_patient, project_name="不可见研究")
    hidden_device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="query-count-hidden-device",
        identifier_type="device_id",
        model="TEST",
        short_code="1399",
    )
    WearableBinding.objects.create(
        patient=hidden_patient,
        device=hidden_device,
        bound_at=datetime(2026, 6, 20, tzinfo=UTC),
        bound_by=other_doctor,
    )

    with CaptureQueriesContext(connection) as many_patient_queries:
        many_patient_rows = list_patient_tracking_summaries(doctor, today=today)

    assert [row["patient"]["id"] for row in one_patient_rows] == [project_patient.patient_id]
    returned_ids = [row["patient"]["id"] for row in many_patient_rows]
    assert set(returned_ids) == visible_patient_ids
    assert len(returned_ids) == len(visible_patient_ids)
    assert hidden_patient.id not in returned_ids
    assert len(one_patient_queries) == len(many_patient_queries)
    assert len(many_patient_queries) <= 5


@pytest.mark.django_db
def test_tracking_batch_queries_limit_binding_history_runs_and_summaries_to_needed_windows(
    doctor, project_patient
):
    today = datetime(2026, 7, 24).date()
    stale_device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="query-shape-stale-device",
        identifier_type="device_id",
        model="TEST",
        short_code="1400",
    )
    active_device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="query-shape-active-device",
        identifier_type="device_id",
        model="TEST",
        short_code="1401",
    )
    WearableBinding.objects.create(
        patient=project_patient.patient,
        device=stale_device,
        bound_at=datetime(2025, 1, 1, tzinfo=UTC),
        unbound_at=datetime(2025, 2, 1, tzinfo=UTC),
        bound_by=doctor,
        unbound_by=doctor,
    )
    active_bound_at = datetime(2026, 7, 1, tzinfo=UTC)
    WearableBinding.objects.create(
        patient=project_patient.patient,
        device=active_device,
        bound_at=active_bound_at,
        bound_by=doctor,
    )

    executed = []

    def capture_queries(execute, sql, params, many, context):
        executed.append((sql, params))
        return execute(sql, params, many, context)

    with connection.execute_wrapper(capture_queries):
        list_patient_tracking_summaries(doctor, today=today)

    binding_queries = [
        (sql, params)
        for sql, params in executed
        if "wearables_wearablebinding" in sql.lower()
    ]
    run_queries = [
        (sql, params) for sql, params in executed if "wearables_wearablesyncrun" in sql.lower()
    ]
    summary_queries = [
        (sql, params)
        for sql, params in executed
        if "wearables_wearabledailysummary" in sql.lower()
    ]

    assert len(binding_queries) == 2
    assert any('"unbound_at" IS NULL' in sql for sql, _ in binding_queries)
    assert any(
        '"bound_at" <' in sql and '"unbound_at" >' in sql
        for sql, _ in binding_queries
    )
    assert len(run_queries) == 1
    run_sql, run_params = run_queries[0]
    assert '"created_at" >=' in run_sql
    assert active_device.id in run_params
    assert stale_device.id not in run_params
    assert any(
        _sql_datetime_param_matches(param, active_bound_at)
        for param in run_params
    )
    assert len(summary_queries) == 1
    assert '"record_date" >=' in summary_queries[0][0]
    assert '"record_date" <=' in summary_queries[0][0]


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
        form_data={
            "raw_detail": {
                "ended_early": True,
                "difficulty_adjust_reason": "不应展示",
                "upload_mode": "retry",
                "retry_count": 9,
                "total_retry_count": 99,
            },
        },
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
            "accuracy_rate": 95,
            "error_count": 1,
            "difficulty": "简单",
            "raw_detail": {
                "ended_early": True,
                "difficulty_adjust_reason": "今天状态不佳",
                "upload_mode": "retry",
                "retry_count": 2,
                "total_retry_count": 12,
            },
        },
        note="游戏顺利",
    )
    _record(
        project_patient,
        active_prescription,
        game_action,
        training_date=today,
        status=TrainingRecord.Status.PARTIAL,
        duration=7,
        score=Decimal("70.00"),
        form_data={
            "accuracy_rate": 70,
            "error_count": 4,
            "difficulty": "普通",
        },
        note="部分完成游戏",
    )
    _record(
        project_patient,
        active_prescription,
        game_action,
        training_date=today,
        status=TrainingRecord.Status.PARTIAL,
        duration=5,
        form_data={
            "accuracy_rate": True,
            "error_count": True,
            "difficulty": "布尔指标",
        },
        note="部分完成布尔指标",
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
    _record(
        project_patient,
        active_prescription,
        game_action,
        training_date=today - timezone.timedelta(days=20),
        status=TrainingRecord.Status.COMPLETED,
        duration=6,
        form_data={
            "accuracy_rate": True,
            "error_count": True,
            "difficulty": "布尔指标",
        },
        note="完成布尔指标",
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
            "project_completed_at": None,
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
    assert completion_by_action[prescription_action.id]["completion_rate"] == 100.0
    assert completion_by_action[game_action.id]["completed_count"] == 1
    assert completion_by_action[game_action.id]["completion_rate"] == 50.0
    assert completion_by_action[game_action.id]["internal_type"] == "game"

    trend = response.data["trend"]
    assert len(trend["daily"]) == 30
    assert len(trend["moving_average"]) == 30
    assert trend["daily"][-1] == {
        "date": today.isoformat(),
        "completed_count": 3,
        "duration_minutes": 55,
        "game_average_score": 80.0,
    }
    assert trend["moving_average"][-1]["date"] == today.isoformat()
    assert trend["moving_average"][-1]["completed_count_avg"] > 0
    assert trend["weekly"]
    assert {"week_start", "week_end", "completed_count", "duration_minutes", "game_average_score"} <= set(
        trend["weekly"][0]
    )
    this_week = next(
        item
        for item in trend["weekly"]
        if item["week_start"]
        <= today.isoformat()
        <= item["week_end"]
    )
    assert this_week["completed_count"] == 3
    assert this_week["duration_minutes"] == 55
    assert this_week["game_average_score"] == 80.0

    game_summary = response.data["game_summary"]
    assert game_summary["average_score"] == 80.0
    assert game_summary["average_accuracy_rate"] == 81.67
    assert game_summary["total_error_count"] == 7
    assert game_summary["by_game"] == [
        {
            "prescription_action": game_action.id,
            "action_name": "颜色记忆",
            "record_count": 5,
            "average_score": 80.0,
            "average_accuracy_rate": 81.67,
            "recent_record_at": today.isoformat(),
        }
    ]

    recent = response.data["recent_records"]
    assert len(recent) == 7
    completed_game = next(item for item in recent if item["note"] == "游戏顺利")
    assert completed_game["score"] == 90.0
    assert completed_game["game_accuracy_rate"] == 95.0
    assert completed_game["game_error_count"] == 1
    assert completed_game["game_difficulty"] == "简单"
    assert completed_game["game_ended_early"] is True
    assert completed_game["game_difficulty_adjust_reason"] == "今天状态不佳"
    assert completed_game["game_upload_mode"] == "retry"
    assert completed_game["game_retry_count"] == 2
    assert completed_game["game_total_retry_count"] == 12
    completed_motion = next(item for item in recent if item["note"] == "第一次运动")
    assert completed_motion["game_ended_early"] is None
    assert completed_motion["game_difficulty_adjust_reason"] is None
    assert completed_motion["game_upload_mode"] is None
    assert completed_motion["game_retry_count"] is None
    assert completed_motion["game_total_retry_count"] is None
    bool_metric_game = next(item for item in recent if item["note"] == "部分完成布尔指标")
    assert bool_metric_game["game_accuracy_rate"] is None
    assert bool_metric_game["game_error_count"] is None
    assert bool_metric_game["game_difficulty"] == "布尔指标"


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
def test_tracking_allows_project_patient_creator_to_access_patient(doctor):
    owner_doctor = _doctor(phone="13800007771", name="主管医生")
    enrolling_doctor = _doctor(phone="13800007772", name="入组医生")
    patient = _patient(owner_doctor, name="入组可见患者", phone="13900007771")
    project = StudyProject.objects.create(name="主管项目", created_by=owner_doctor)
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    project_patient = ProjectPatient.objects.create(
        project=project,
        patient=patient,
        group=group,
        created_by=enrolling_doctor,
    )

    list_response = _client(enrolling_doctor).get(
        "/api/training/tracking/patients/",
        {"q": "入组可见患者"},
    )
    assert list_response.status_code == 200, list_response.data
    assert [item["patient"]["id"] for item in list_response.data] == [patient.id]

    detail_response = _client(enrolling_doctor).get(
        f"/api/training/tracking/patients/{patient.id}/"
    )
    assert detail_response.status_code == 200, detail_response.data
    assert detail_response.data["selected_project_patient"]["id"] == project_patient.id

    hidden_response = _client(doctor).get(f"/api/training/tracking/patients/{patient.id}/")
    assert hidden_response.status_code == 404


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

    invalid_project_patient_response = _client(doctor).get(
        f"/api/training/tracking/patients/{project_patient.patient_id}/",
        {"project_patient": "abc"},
    )
    assert invalid_project_patient_response.status_code == 400
    assert invalid_project_patient_response.data["detail"] == "project_patient 必须是数字"

    response = _client(doctor).get(
        f"/api/training/tracking/patients/{project_patient.patient_id}/",
        {"range": "7d"},
    )

    assert response.status_code == 200, response.data
    assert len(response.data["trend"]["daily"]) == 7
    assert len(response.data["trend"]["moving_average"]) == 7

    weekly_response = _client(doctor).get(
        f"/api/training/tracking/patients/{project_patient.patient_id}/",
        {"range": "weekly"},
    )
    assert weekly_response.status_code == 200, weekly_response.data
    assert len(weekly_response.data["trend"]["daily"]) == 30
    assert len(weekly_response.data["trend"]["moving_average"]) == 30
    assert weekly_response.data["trend"]["weekly"]


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
