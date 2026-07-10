import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import override_settings
from django.utils import timezone
from qiniu import BucketManager
from rest_framework.test import APIClient

from apps.patient_app.services import bind_project_patient_with_code, create_binding_code
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient
from apps.training.models import TrainingRecord, TrainingVideo


def _stat_response(*, status_code=200, error=None):
    return SimpleNamespace(status_code=status_code, error=error)


@pytest.fixture(autouse=True)
def qiniu_stat(monkeypatch):
    def trusted_metadata(bucket, key):
        video = TrainingVideo.objects.get(bucket=bucket, object_key=key)
        return (
            {
                "hash": "qiniu-hash",
                "fsize": video.size_bytes,
                "mimeType": video.content_type,
            },
            _stat_response(),
        )

    stat = Mock(side_effect=trusted_metadata)
    monkeypatch.setattr(BucketManager, "stat", stat)
    return stat


def _auth_client(project_patient, doctor, *, wx_openid="openid-video"):
    code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    token, _ = bind_project_patient_with_code(code, wx_openid=wx_openid)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _shoulder_press_action(active_prescription):
    item = ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press")
    return active_prescription.add_action_snapshot(
        item,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=10,
    )


def _upload_payload(action, **overrides):
    return {
        "prescription_action": action.id,
        "content_type": "video/mp4",
        "size_bytes": 1024,
        "duration_seconds": 60,
        **overrides,
    }


def _complete_payload(intent, **overrides):
    return {
        "key": intent.data["key"],
        "hash": "qiniu-hash",
        "training_date": str(timezone.localdate()),
        "actual_duration_minutes": 2,
        "note": "完成肩部推举",
        **overrides,
    }


def _other_project_patient(project_patient, doctor):
    patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900001112",
        primary_doctor=doctor,
    )
    return ProjectPatient.objects.create(
        project=project_patient.project,
        patient=patient,
        group=project_patient.group,
    )


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_creates_shoulder_press_upload_intent(project_patient, doctor, active_prescription):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        _upload_payload(action),
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["upload_token"].startswith("ak-test:")
    assert response.data["upload_host"] == "https://upload.qiniup.com"
    video = TrainingVideo.objects.get(pk=response.data["video_id"])
    assert video.project_patient == project_patient
    assert video.prescription_action == action
    assert video.status == TrainingVideo.Status.UPLOADING
    assert video.object_key == response.data["key"]


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_ignores_frontend_project_patient_identity(
    project_patient,
    doctor,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    other_project_patient = _other_project_patient(project_patient, doctor)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        _upload_payload(
            action,
            project_patient=other_project_patient.id,
            patient=other_project_patient.patient_id,
            project=other_project_patient.project_id,
        ),
        format="json",
    )

    assert response.status_code == 201, response.data
    assert TrainingVideo.objects.get(pk=response.data["video_id"]).project_patient == project_patient


@pytest.mark.django_db
def test_patient_app_rejects_upload_intent_for_non_shoulder_action(
    project_patient,
    doctor,
    active_prescription,
    prescription_action,
):
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        _upload_payload(prescription_action),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "肩部推举" in str(response.data)


@pytest.mark.django_db
def test_patient_app_rejects_upload_intent_for_another_patients_action(
    project_patient,
    doctor,
    active_prescription,
):
    _shoulder_press_action(active_prescription)
    other_project_patient = _other_project_patient(project_patient, doctor)
    other_prescription = Prescription.objects.create(
        project_patient=other_project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    other_action = _shoulder_press_action(other_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        _upload_payload(other_action),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert TrainingVideo.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value", "expected_detail"),
    [
        ("size_bytes", 2_000, "文件过大"),
        ("duration_seconds", 121, "时长超过限制"),
    ],
)
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
    TRAINING_VIDEO_MAX_SIZE_BYTES=1_999,
    TRAINING_VIDEO_MAX_DURATION_SECONDS=120,
)
def test_patient_app_rejects_upload_intent_outside_video_limits(
    project_patient,
    doctor,
    active_prescription,
    field,
    value,
    expected_detail,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        _upload_payload(action, **{field: value}),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert expected_detail in str(response.data)
    assert TrainingVideo.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "setting_name",
    [
        "QINIU_ACCESS_KEY",
        "QINIU_SECRET_KEY",
        "QINIU_BUCKET",
        "QINIU_UPLOAD_HOST",
    ],
)
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_rejects_upload_intent_when_qiniu_configuration_is_missing(
    project_patient,
    doctor,
    active_prescription,
    settings,
    setting_name,
):
    setattr(settings, setting_name, "")
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        _upload_payload(action),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "七牛配置" in str(response.data)
    assert TrainingVideo.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_complete_upload_creates_training_record_once(
    project_patient,
    doctor,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    intent = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        _upload_payload(action, size_bytes=2048, duration_seconds=120),
        format="json",
    )

    first = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        _complete_payload(intent),
        format="json",
    )
    second = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        _complete_payload(intent),
        format="json",
    )

    assert first.status_code == 201, first.data
    assert second.status_code == 200, second.data
    assert TrainingRecord.objects.filter(project_patient=project_patient).count() == 1
    video = TrainingVideo.objects.get(pk=intent.data["video_id"])
    assert video.status == TrainingVideo.Status.ATTACHED
    assert video.object_hash == "qiniu-hash"
    assert video.training_record_id == first.data["training_record"]["id"]


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_complete_retry_remains_idempotent_after_prescription_changes(
    project_patient,
    doctor,
    active_prescription,
    qiniu_stat,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    intent = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        _upload_payload(action),
        format="json",
    )
    payload = _complete_payload(intent)
    first = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        payload,
        format="json",
    )
    active_prescription.status = Prescription.Status.ARCHIVED
    active_prescription.save(update_fields=["status", "updated_at"])
    replacement = Prescription.objects.create(
        project_patient=project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    _shoulder_press_action(replacement)

    retry = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        payload,
        format="json",
    )

    assert first.status_code == 201, first.data
    assert retry.status_code == 200, retry.data
    assert retry.data["training_record"]["id"] == first.data["training_record"]["id"]
    assert TrainingRecord.objects.filter(project_patient=project_patient).count() == 1
    assert qiniu_stat.call_count == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("key", "training-videos/other.mp4"),
        ("hash", "different-hash"),
        ("training_date", "2026-07-09"),
        ("actual_duration_minutes", 3),
        ("note", "不同备注"),
    ],
)
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_rejects_attached_retry_with_conflicting_payload(
    project_patient,
    doctor,
    active_prescription,
    field,
    value,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    intent = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        _upload_payload(action),
        format="json",
    )
    payload = _complete_payload(intent)
    first = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        payload,
        format="json",
    )

    retry = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        {**payload, field: value},
        format="json",
    )

    assert first.status_code == 201, first.data
    assert retry.status_code == 400, retry.data
    assert "冲突" in str(retry.data)
    record = TrainingRecord.objects.get(project_patient=project_patient)
    assert record.training_date == timezone.localdate()
    assert record.actual_duration_minutes == 2
    assert record.note == "完成肩部推举"
    assert TrainingVideo.objects.get(pk=intent.data["video_id"]).object_hash == "qiniu-hash"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("remote_metadata", "expected_detail"),
    [
        (None, "对象不存在"),
        (
            {"hash": "random-hash", "fsize": 1024, "mimeType": "video/mp4"},
            "Hash 不匹配",
        ),
        (
            {"hash": "qiniu-hash", "fsize": 2048, "mimeType": "video/mp4"},
            "大小不匹配",
        ),
        (
            {"hash": "qiniu-hash", "fsize": 1024, "mimeType": "image/png"},
            "类型不匹配",
        ),
    ],
)
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_rejects_complete_when_qiniu_metadata_is_untrusted(
    project_patient,
    doctor,
    active_prescription,
    qiniu_stat,
    remote_metadata,
    expected_detail,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    intent = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        _upload_payload(action),
        format="json",
    )
    status_code = 200 if remote_metadata is not None else 612
    qiniu_stat.side_effect = None
    qiniu_stat.return_value = (
        remote_metadata,
        _stat_response(status_code=status_code, error="no such file"),
    )

    response = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        _complete_payload(intent),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert expected_detail in str(response.data)
    assert TrainingRecord.objects.count() == 0
    video = TrainingVideo.objects.get(pk=intent.data["video_id"])
    assert video.status == TrainingVideo.Status.UPLOADING
    assert video.object_hash == ""


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_complete_stats_before_project_patient_and_video_locks(
    project_patient,
    doctor,
    active_prescription,
    qiniu_stat,
    monkeypatch,
):
    from django.db.models.query import QuerySet

    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    intent = client.post(
        "/api/patient-app/training-videos/upload-intent/",
        _upload_payload(action),
        format="json",
    )
    events = []
    original_select_for_update = QuerySet.select_for_update
    original_stat_side_effect = qiniu_stat.side_effect

    def record_lock(queryset, *args, **kwargs):
        if queryset.model in {ProjectPatient, TrainingVideo}:
            events.append(queryset.model.__name__)
        return original_select_for_update(queryset, *args, **kwargs)

    def record_stat(bucket, key):
        events.append("qiniu_stat")
        return original_stat_side_effect(bucket, key)

    monkeypatch.setattr(QuerySet, "select_for_update", record_lock)
    qiniu_stat.side_effect = record_stat

    response = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        _complete_payload(intent),
        format="json",
    )

    assert response.status_code == 201, response.data
    assert events[:3] == ["qiniu_stat", "ProjectPatient", "TrainingVideo"]


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_rejects_complete_for_another_patients_video(
    project_patient,
    doctor,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    owner_client = _auth_client(project_patient, doctor)
    intent = owner_client.post(
        "/api/patient-app/training-videos/upload-intent/", _upload_payload(action), format="json"
    )
    other_project_patient = _other_project_patient(project_patient, doctor)
    other_client = _auth_client(other_project_patient, doctor, wx_openid="openid-other-video")

    response = other_client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        _complete_payload(intent),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert TrainingRecord.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_rejects_complete_with_wrong_key_or_empty_hash(
    project_patient,
    doctor,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    intent = client.post(
        "/api/patient-app/training-videos/upload-intent/", _upload_payload(action), format="json"
    )

    wrong_key = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        _complete_payload(intent, key="training-videos/other.mp4"),
        format="json",
    )
    blank_hash = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        _complete_payload(intent, hash=""),
        format="json",
    )

    assert wrong_key.status_code == 400, wrong_key.data
    assert blank_hash.status_code == 400, blank_hash.data
    assert TrainingRecord.objects.count() == 0
    assert TrainingVideo.objects.get(pk=intent.data["video_id"]).status == TrainingVideo.Status.UPLOADING


@pytest.mark.django_db
@override_settings(
    QINIU_ACCESS_KEY="ak-test",
    QINIU_SECRET_KEY="sk-test",
    QINIU_BUCKET="motioncare-training",
    QINIU_UPLOAD_HOST="https://upload.qiniup.com",
)
def test_patient_app_rejects_complete_after_prescription_changes(
    project_patient,
    doctor,
    active_prescription,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    intent = client.post(
        "/api/patient-app/training-videos/upload-intent/", _upload_payload(action), format="json"
    )
    active_prescription.status = Prescription.Status.ARCHIVED
    active_prescription.save(update_fields=["status", "updated_at"])
    replacement = Prescription.objects.create(
        project_patient=project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    _shoulder_press_action(replacement)

    response = client.post(
        f"/api/patient-app/training-videos/{intent.data['video_id']}/complete/",
        _complete_payload(intent),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "处方已更新" in str(response.data)
    assert TrainingRecord.objects.count() == 0
    assert TrainingVideo.objects.get(pk=intent.data["video_id"]).status == TrainingVideo.Status.UPLOADING
