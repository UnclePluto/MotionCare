import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.patient_app.throttles import DemoMotionVideoRateThrottle
from apps.patient_app.services import bind_project_patient_with_code, create_binding_code
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.prescriptions.motion_videos import MotionVideoResolution
from apps.training.models import TrainingRecord


OFFICIAL_MOTION_SOURCE_KEYS = (
    "motion-aerobic-high-knee",
    "motion-balance-sit-stand",
    "motion-resistance-leg-kickback",
    "motion-resistance-row",
    "motion-resistance-shoulder-press",
)


class _IsolatedDemoManifestRedis:
    def __init__(self):
        self.count = 0

    def eval(self, *_args):
        self.count += 1
        return self.count


@pytest.fixture(autouse=True)
def isolate_demo_manifest_rate_limit(monkeypatch):
    redis = _IsolatedDemoManifestRedis()
    monkeypatch.setattr(
        DemoMotionVideoRateThrottle,
        "redis_client_factory",
        staticmethod(lambda _url: redis),
    )


def _auth_client(project_patient, doctor):
    code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    token, _ = bind_project_patient_with_code(code, wx_openid="openid-a")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _game_prescription_action(active_prescription):
    action = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    return active_prescription.add_action_snapshot(
        action,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=10,
        difficulty="简单",
    )


@pytest.mark.django_db
def test_bind_api_returns_token_and_bound_identity(project_patient, doctor):
    code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    client = APIClient()

    response = client.post(
        "/api/patient-app/bind/",
        {"code": code, "wx_openid": "openid-a"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["token"]
    assert response.data["project_patient_id"] == project_patient.id
    assert response.data["patient"]["name"] == project_patient.patient.name
    assert response.data["project"]["name"] == project_patient.project.name


@pytest.mark.parametrize(
    "payload",
    [
        {"code": "12AB", "wx_openid": "openid-a"},
        {"code": "１２３４", "wx_openid": "openid-a"},
        {"code": "", "wx_openid": "openid-a"},
        {"code": "123", "wx_openid": "openid-a"},
        {"code": "12345", "wx_openid": "openid-a"},
        {"code": " 1234 ", "wx_openid": "openid-a"},
        {"code": "\t1234\n", "wx_openid": "openid-a"},
        {"code": 1234, "wx_openid": "openid-a"},
        {"code": None, "wx_openid": "openid-a"},
        {"wx_openid": "openid-a"},
    ],
)
@pytest.mark.django_db
def test_bind_api_rejects_non_numeric_or_wrong_length_code(payload):
    client = APIClient()
    response = client.post(
        "/api/patient-app/bind/",
        payload,
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "4 位数字" in str(response.data)


@pytest.mark.django_db
def test_patient_app_me_uses_bearer_token(project_patient, doctor):
    client = _auth_client(project_patient, doctor)

    response = client.get("/api/patient-app/me/")

    assert response.status_code == 200, response.data
    assert response.data["project_patient_id"] == project_patient.id
    assert response.data["patient"]["id"] == project_patient.patient_id
    assert response.data["project"]["id"] == project_patient.project_id


@pytest.mark.django_db
def test_current_prescription_includes_weekly_progress_and_recent_record(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    prescription_action.weekly_target_count = 2
    prescription_action.save(update_fields=["weekly_target_count", "updated_at"])
    TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=12,
    )
    client = _auth_client(project_patient, doctor)

    response = client.get("/api/patient-app/current-prescription/")

    assert response.status_code == 200, response.data
    assert response.data["id"] == active_prescription.id
    action = response.data["actions"][0]
    assert action["id"] == prescription_action.id
    assert action["weekly_target_count"] == 2
    assert action["weekly_completed_count"] == 1
    assert action["recent_record"]["status"] == TrainingRecord.Status.COMPLETED


@pytest.mark.django_db
def test_current_prescription_includes_action_source_key(
    project_patient,
    doctor,
    active_prescription,
):
    game_action = _game_prescription_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.get("/api/patient-app/current-prescription/")

    assert response.status_code == 200, response.data
    action = next(item for item in response.data["actions"] if item["id"] == game_action.id)
    assert action["source_key"] == "game-memory-color-sequence"


@pytest.mark.django_db
def test_current_prescription_keeps_business_data_when_video_signing_fails(
    project_patient, doctor, prescription_action, monkeypatch
):
    client = _auth_client(project_patient, doctor)
    monkeypatch.setattr(
        "apps.patient_app.views.resolve_motion_video_url",
        lambda *args, **kwargs: MotionVideoResolution(url="", unavailable=True),
        raising=False,
    )

    response = client.get("/api/patient-app/current-prescription/")

    assert response.status_code == 200
    action = response.json()["actions"][0]
    assert action["video_url"] == ""
    assert action["video_unavailable"] is True


@pytest.mark.django_db
def test_current_prescription_keeps_other_actions_when_one_video_signing_raises(
    project_patient, doctor, active_prescription, prescription_action, monkeypatch
):
    prescription_action.video_object_key_snapshot = "failing-video-key"
    prescription_action.save(update_fields=["video_object_key_snapshot", "updated_at"])
    successful_action = _game_prescription_action(active_prescription)
    successful_action.video_object_key_snapshot = "working-video-key"
    successful_action.save(update_fields=["video_object_key_snapshot", "updated_at"])
    client = _auth_client(project_patient, doctor)

    def resolve_video(object_key, legacy_url):
        if object_key == "failing-video-key":
            raise RuntimeError("签名服务不可用")
        return MotionVideoResolution(
            url="https://signed.example.com/working.mp4", unavailable=False
        )

    monkeypatch.setattr(
        "apps.patient_app.views.resolve_motion_video_url", resolve_video
    )

    response = client.get("/api/patient-app/current-prescription/")

    assert response.status_code == 200
    actions = {action["id"]: action for action in response.json()["actions"]}
    failed_action = actions[prescription_action.id]
    assert failed_action["action_name"] == prescription_action.action_name_snapshot
    assert failed_action["weekly_target_count"] == prescription_action.weekly_target_count
    assert failed_action["video_url"] == ""
    assert failed_action["video_unavailable"] is True
    assert actions[successful_action.id]["video_url"] == "https://signed.example.com/working.mp4"
    assert actions[successful_action.id]["video_unavailable"] is False


@pytest.mark.django_db
def test_demo_motion_manifest_has_no_patient_queries(
    client, django_assert_num_queries, monkeypatch
):
    cache.clear()
    monkeypatch.setattr(
        "apps.patient_app.views.build_demo_motion_video_manifest",
        lambda: [
            {
                "source_key": "motion-resistance-row",
                "video_url": "https://signed.example.com/row.mp4",
            }
        ],
        raising=False,
    )

    with django_assert_num_queries(0):
        response = client.get("/api/patient-app/demo-motion-videos/")

    assert response.status_code == 200
    assert response.json() == {
        "videos": [
            {
                "source_key": "motion-resistance-row",
                "video_url": "https://signed.example.com/row.mp4",
            }
        ]
    }


@pytest.mark.django_db
def test_demo_motion_manifest_ignores_object_key_query_parameter(client, monkeypatch):
    cache.clear()
    monkeypatch.setattr(
        "apps.patient_app.views.build_demo_motion_video_manifest",
        lambda: [
            {
                "source_key": "motion-resistance-row",
                "video_url": "https://signed.example.com/row.mp4",
            }
        ],
        raising=False,
    )

    response = client.get(
        "/api/patient-app/demo-motion-videos/?object_key=training-videos/private.mp4"
    )

    assert response.status_code == 200
    assert response.json() == {
        "videos": [
            {
                "source_key": "motion-resistance-row",
                "video_url": "https://signed.example.com/row.mp4",
            }
        ]
    }


@pytest.mark.django_db
def test_demo_motion_manifest_hides_signing_failure_details(client, monkeypatch):
    cache.clear()
    monkeypatch.setattr(
        "apps.patient_app.views.build_demo_motion_video_manifest",
        lambda: (_ for _ in ()).throw(
            RuntimeError("token=secret-key-motion-action-videos/v1/row.mp4")
        ),
        raising=False,
    )

    response = client.get("/api/patient-app/demo-motion-videos/")

    assert response.status_code == 503
    assert response.json() == {"detail": "演示视频暂时不可用，请稍后重试"}
    assert "token" not in response.content.decode()
    assert "secret-key" not in response.content.decode()
    assert "motion-action-videos" not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("cache_method", ["get", "set"])
def test_demo_motion_manifest_hides_cache_failure_details(client, monkeypatch, cache_method):
    cache.clear()
    if cache_method == "set":
        monkeypatch.setattr(
            "apps.patient_app.views.build_demo_motion_video_manifest",
            lambda: [
                {
                    "source_key": "motion-resistance-row",
                    "video_url": "https://signed.example.com/row.mp4",
                }
            ],
        )

    def raise_cache_error(*args, **kwargs):
        if args[0] != "patient-app:demo-motion-videos:v1":
            return original_cache_method(*args, **kwargs)
        raise RuntimeError("cache token=secret")

    original_cache_method = getattr(cache, cache_method)
    monkeypatch.setattr(f"apps.patient_app.views.cache.{cache_method}", raise_cache_error)

    response = client.get("/api/patient-app/demo-motion-videos/")

    assert response.status_code == 503
    assert response.json() == {"detail": "演示视频暂时不可用，请稍后重试"}
    assert "token" not in response.content.decode()


@pytest.mark.django_db
def test_demo_motion_manifest_hides_throttle_cache_failure_details(client, monkeypatch):
    cache.clear()

    def raise_cache_error(*args, **kwargs):
        raise RuntimeError("cache token=secret")

    monkeypatch.setattr("apps.patient_app.views.cache.get", raise_cache_error)

    response = client.get("/api/patient-app/demo-motion-videos/")

    assert response.status_code == 503
    assert response.json() == {"detail": "演示视频暂时不可用，请稍后重试"}
    assert "token" not in response.content.decode()


@pytest.mark.django_db
def test_demo_motion_manifest_caches_full_response_for_60_seconds(client, monkeypatch):
    cache.clear()
    calls = 0

    def build_manifest():
        nonlocal calls
        calls += 1
        return [
            {
                "source_key": "motion-resistance-row",
                "video_url": "https://signed.example.com/row.mp4",
            }
        ]

    monkeypatch.setattr(
        "apps.patient_app.views.build_demo_motion_video_manifest",
        build_manifest,
        raising=False,
    )

    first = client.get("/api/patient-app/demo-motion-videos/")
    second = client.get("/api/patient-app/demo-motion-videos/")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert calls == 1


@pytest.mark.django_db
def test_training_record_api_allows_multiple_records_same_day(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    client = _auth_client(project_patient, doctor)
    payload = {
        "prescription_action": prescription_action.id,
        "training_date": str(timezone.localdate()),
        "status": TrainingRecord.Status.COMPLETED,
        "actual_duration_minutes": 10,
        "note": "完成",
    }

    first = client.post("/api/patient-app/training-records/", payload, format="json")
    second = client.post("/api/patient-app/training-records/", payload, format="json")

    assert first.status_code == 201, first.data
    assert second.status_code == 201, second.data
    assert TrainingRecord.objects.filter(project_patient=project_patient).count() == 2
    assert first.data["prescription"] == active_prescription.id
    assert second.data["prescription_action"] == prescription_action.id


@pytest.mark.django_db
@pytest.mark.parametrize("source_key", OFFICIAL_MOTION_SOURCE_KEYS)
def test_training_record_api_rejects_official_motion_action_without_video(
    source_key,
    project_patient,
    doctor,
    active_prescription,
):
    item = ActionLibraryItem.objects.get(source_key=source_key)
    action = active_prescription.add_action_snapshot(
        item,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=10,
    )
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-records/",
        {
            "prescription_action": action.id,
            "training_date": str(timezone.localdate()),
            "status": TrainingRecord.Status.COMPLETED,
            "actual_duration_minutes": 10,
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert response.data["detail"] == "运动动作必须完成录像上传"
    assert not TrainingRecord.objects.filter(prescription_action=action).exists()


def _activate_now_payload(action, duration_minutes):
    return {
        "expected_active_version": 1,
        "actions": [
            {
                "action_library_item": action.id,
                "weekly_frequency": "3 次/周",
                "weekly_target_count": 3,
                "duration_minutes": duration_minutes,
            }
        ],
    }


@pytest.mark.django_db
def test_activate_now_rejects_official_motion_action_over_30_minutes(
    project_patient,
    doctor,
    active_prescription,
):
    action = ActionLibraryItem.objects.get(source_key="motion-resistance-row")
    client = APIClient()
    client.force_authenticate(user=doctor)

    response = client.post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        _activate_now_payload(action, 31),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "运动动作时长不能超过 30 分钟" in str(response.data)
    assert Prescription.objects.filter(project_patient=project_patient).count() == 1


@pytest.mark.django_db
def test_activate_now_accepts_official_motion_action_at_30_minutes(
    project_patient,
    doctor,
    active_prescription,
):
    action = ActionLibraryItem.objects.get(source_key="motion-resistance-row")
    client = APIClient()
    client.force_authenticate(user=doctor)

    response = client.post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        _activate_now_payload(action, 30),
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["actions"][0]["duration_minutes"] == 30


@pytest.mark.django_db
def test_activate_now_does_not_apply_motion_duration_limit_to_game(
    project_patient,
    doctor,
    active_prescription,
):
    action = ActionLibraryItem.objects.get(source_key="game-memory-color-sequence")
    client = APIClient()
    client.force_authenticate(user=doctor)

    response = client.post(
        f"/api/studies/project-patients/{project_patient.id}/prescriptions/activate-now/",
        _activate_now_payload(action, 31),
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["actions"][0]["duration_minutes"] == 31


@pytest.mark.django_db
def test_patient_app_submits_game_result(
    project_patient,
    doctor,
    active_prescription,
):
    game_action = _game_prescription_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-records/",
        {
            "prescription_action": game_action.id,
            "training_date": str(timezone.localdate()),
            "status": TrainingRecord.Status.COMPLETED,
            "actual_duration_minutes": 8,
            "score": "86.50",
            "form_data": {
                "accuracy_rate": 92,
                "error_count": 3,
                "difficulty": "简单",
                "raw_detail": {"rounds": 6, "max_sequence": 5},
            },
            "note": "完成顺利",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    record = TrainingRecord.objects.get(pk=response.data["id"])
    assert record.prescription == active_prescription
    assert record.prescription_action == game_action
    assert str(record.score) == "86.50"
    assert record.form_data["accuracy_rate"] == 92
    assert record.form_data["error_count"] == 3
    assert record.form_data["difficulty"] == "简单"
    assert record.form_data["raw_detail"]["max_sequence"] == 5


@pytest.mark.django_db
@pytest.mark.parametrize(
    "form_data",
    [
        {
            "accuracy_rate": "",
            "error_count": "",
            "raw_detail": "",
        },
        {
            "accuracy_rate": None,
            "error_count": None,
            "raw_detail": None,
        },
    ],
)
def test_patient_app_submits_game_result_with_blank_optional_metrics(
    project_patient,
    doctor,
    active_prescription,
    form_data,
):
    game_action = _game_prescription_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-records/",
        {
            "prescription_action": game_action.id,
            "training_date": str(timezone.localdate()),
            "status": TrainingRecord.Status.COMPLETED,
            "actual_duration_minutes": 8,
            "form_data": {
                **form_data,
                "difficulty": "简单",
            },
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    record = TrainingRecord.objects.get(pk=response.data["id"])
    assert record.prescription_action == game_action
    assert record.form_data["accuracy_rate"] == form_data["accuracy_rate"]
    assert record.form_data["error_count"] == form_data["error_count"]
    assert record.form_data["raw_detail"] == form_data["raw_detail"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "form_data,error_text",
    [
        ([], "游戏结果明细必须是对象"),
        ({"accuracy_rate": 101}, "正确率必须在 0 到 100 之间"),
        ({"accuracy_rate": -1}, "正确率必须在 0 到 100 之间"),
        ({"accuracy_rate": True}, "正确率必须在 0 到 100 之间"),
        ({"error_count": -1}, "错误次数必须是非负整数"),
        ({"error_count": "很多"}, "错误次数必须是非负整数"),
        ({"error_count": True}, "错误次数必须是非负整数"),
        ({"difficulty": 1}, "游戏难度必须是文本"),
        ({"difficulty": []}, "游戏难度必须是文本"),
        ({"raw_detail": []}, "游戏原始明细必须是对象"),
        ({"raw_detail": "bad"}, "游戏原始明细必须是对象"),
    ],
)
def test_patient_app_rejects_invalid_game_result_metrics(
    project_patient,
    doctor,
    active_prescription,
    form_data,
    error_text,
):
    game_action = _game_prescription_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-records/",
        {
            "prescription_action": game_action.id,
            "training_date": str(timezone.localdate()),
            "status": TrainingRecord.Status.COMPLETED,
            "actual_duration_minutes": 8,
            "form_data": form_data,
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert error_text in str(response.data)
    assert not TrainingRecord.objects.filter(prescription_action=game_action).exists()


@pytest.mark.django_db
def test_patient_app_allows_game_metric_shape_for_non_game_action(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-records/",
        {
            "prescription_action": prescription_action.id,
            "training_date": str(timezone.localdate()),
            "status": TrainingRecord.Status.COMPLETED,
            "actual_duration_minutes": 8,
            "form_data": {
                "accuracy_rate": True,
                "raw_detail": [],
                "difficulty": 1,
            },
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    record = TrainingRecord.objects.get(pk=response.data["id"])
    assert record.prescription == active_prescription
    assert record.prescription_action == prescription_action
    assert record.form_data["accuracy_rate"] is True
    assert record.form_data["raw_detail"] == []
    assert record.form_data["difficulty"] == 1


@pytest.mark.django_db
def test_patient_app_rejects_stale_game_prescription_action(
    project_patient,
    doctor,
    active_prescription,
):
    old_game_action = _game_prescription_action(active_prescription)
    active_prescription.status = Prescription.Status.ARCHIVED
    active_prescription.archived_at = timezone.now()
    active_prescription.save(update_fields=["status", "archived_at", "updated_at"])
    Prescription.objects.create(
        project_patient=project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-records/",
        {
            "prescription_action": old_game_action.id,
            "training_date": str(timezone.localdate()),
            "status": TrainingRecord.Status.COMPLETED,
            "actual_duration_minutes": 8,
            "form_data": {"accuracy_rate": 90, "error_count": 1},
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert response.data["detail"] == "处方已更新，请返回当前处方重新进入"
    assert not TrainingRecord.objects.filter(prescription_action=old_game_action).exists()


@pytest.mark.django_db
def test_action_history_only_returns_current_action_records(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
    )
    client = _auth_client(project_patient, doctor)

    response = client.get(f"/api/patient-app/actions/{prescription_action.id}/history/")

    assert response.status_code == 200, response.data
    assert response.data["last_7_days_completed_count"] == 1
    assert response.data["last_30_days_completed_count"] == 1
    assert len(response.data["records"]) == 1
    assert response.data["records"][0]["prescription_action"] == prescription_action.id


@pytest.mark.django_db
def test_daily_health_today_endpoint_is_removed(project_patient, doctor):
    client = _auth_client(project_patient, doctor)

    response = client.put(
        "/api/patient-app/daily-health/today/",
        {"steps": 1000},
        format="json",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_patient_app_home_does_not_expose_manual_health_flag(project_patient, doctor):
    client = _auth_client(project_patient, doctor)

    response = client.get("/api/patient-app/home/")

    assert response.status_code == 200, response.data
    assert "has_daily_health_today" not in response.data
