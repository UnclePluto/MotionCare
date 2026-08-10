import uuid
from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem
from apps.training.models import TrainingRecord, TrainingVideo
from apps.training.video_services import SHOULDER_PRESS_SOURCE_KEY
from apps.wearables.models import (
    WearableBinding,
    WearableDevice,
    WearableMeasurement,
    WearableSyncRun,
)


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _video(
    project_patient,
    active_prescription,
    *,
    started_at,
    ended_at=None,
    expected_duration_seconds=180,
):
    item = ActionLibraryItem.objects.get(source_key=SHOULDER_PRESS_SOURCE_KEY)
    action = active_prescription.actions.filter(action_library_item=item).first()
    if action is None:
        action = active_prescription.add_action_snapshot(
            item,
            weekly_frequency="2 次/周",
            weekly_target_count=2,
            duration_minutes=10,
        )
    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=started_at.astimezone(timezone.get_fixed_timezone(480)).date(),
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=10,
    )
    return TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_record=record,
        training_date=record.training_date,
        training_started_at=started_at,
        training_ended_at=ended_at,
        expected_duration_seconds=expected_duration_seconds,
        object_key=f"training-videos/{project_patient.id}/{uuid.uuid4().hex}.mp4",
        status=TrainingVideo.Status.ATTACHED,
    )


def _bound_device(project_patient, doctor):
    device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="training-window-device",
        identifier_type="device_id",
        model="TEST",
        short_code="2608",
    )
    binding = WearableBinding.objects.create(
        patient=project_patient.patient,
        device=device,
        bound_at=datetime(2026, 8, 1, tzinfo=UTC),
        bound_by=doctor,
    )
    return device, binding


def _other_patient_binding(doctor):
    patient = Patient.objects.create(
        name="穿戴窗口其他患者",
        gender=Patient.Gender.UNKNOWN,
        age=68,
        phone="13900007777",
        primary_doctor=doctor,
    )
    device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="training-window-other-device",
        identifier_type="device_id",
        model="TEST",
        short_code="2609",
    )
    binding = WearableBinding.objects.create(
        patient=patient,
        device=device,
        bound_at=datetime(2026, 8, 1, tzinfo=UTC),
        bound_by=doctor,
    )
    return patient, device, binding


def _other_doctor():
    return User.objects.create_user(
        phone="13800007777",
        password="pass123456",
        name="无权限医生",
        role=User.Role.DOCTOR,
    )


def _measurement(*, patient, device, binding, metric_type, measured_at, **values):
    return WearableMeasurement.objects.create(
        provider="miwitracker",
        patient=patient,
        device=device,
        binding=binding,
        metric_type=metric_type,
        measured_at=measured_at,
        source_fingerprint=f"{metric_type}-{uuid.uuid4().hex}",
        attribution_status=WearableMeasurement.AttributionStatus.ATTRIBUTED,
        raw_payload={},
        **values,
    )


@pytest.mark.django_db
def test_wearable_window_returns_inclusive_raw_points_and_statistics(
    project_patient, doctor, active_prescription
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    expected_duration_seconds = 180
    window_ended_at = started_at + timedelta(seconds=480)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=60),
        expected_duration_seconds=expected_duration_seconds,
    )
    device, binding = _bound_device(project_patient, doctor)
    for second, value in [(0, 67), (60, 89), (120, 90), (180, 112)]:
        _measurement(
            patient=project_patient.patient,
            device=device,
            binding=binding,
            metric_type=WearableMeasurement.MetricType.HEART_RATE,
            measured_at=started_at + timedelta(seconds=second),
            heart_rate=value,
        )
    for second, systolic, diastolic in [
        (30, 121, 74),
        (90, 126, 78),
        (150, 132, 82),
    ]:
        _measurement(
            patient=project_patient.patient,
            device=device,
            binding=binding,
            metric_type=WearableMeasurement.MetricType.BLOOD_PRESSURE,
            measured_at=started_at + timedelta(seconds=second),
            systolic=systolic,
            diastolic=diastolic,
        )

    response = _client(doctor).get(f"/api/training/videos/{video.id}/wearable-window/")

    assert response.status_code == 200
    assert response.data["available"] is True
    assert response.data["window_started_at"] == started_at.isoformat()
    assert response.data["window_ended_at"] == window_ended_at.isoformat()
    assert response.data["expected_duration_seconds"] == 180
    assert response.data["buffer_seconds"] == 300
    assert "training_started_at" not in response.data
    assert "training_ended_at" not in response.data
    assert response.data["metrics"]["heart_rate"]["statistics"] == {
        "average": 89.5,
        "maximum": 112,
        "minimum": 67,
        "count": 4,
    }
    assert response.data["metrics"]["blood_pressure"]["statistics"] == {
        "systolic": {"average": 126.3, "maximum": 132, "minimum": 121},
        "diastolic": {"average": 78.0, "maximum": 82, "minimum": 74},
        "count": 3,
    }
    assert "steps" not in response.data["metrics"]

    _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.BLOOD_OXYGEN,
        measured_at=started_at,
        blood_oxygen=97,
    )
    _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.BLOOD_OXYGEN,
        measured_at=window_ended_at,
        blood_oxygen=96,
    )
    for measured_at in (
        started_at - timedelta(microseconds=1),
        window_ended_at + timedelta(microseconds=1),
    ):
        _measurement(
            patient=project_patient.patient,
            device=device,
            binding=binding,
            metric_type=WearableMeasurement.MetricType.BLOOD_OXYGEN,
            measured_at=measured_at,
            blood_oxygen=95,
        )

    boundary_response = _client(doctor).get(f"/api/training/videos/{video.id}/wearable-window/")

    assert boundary_response.data["metrics"]["blood_oxygen"]["points"] == [
        {"measured_at": started_at.isoformat(), "value": 97},
        {"measured_at": window_ended_at.isoformat(), "value": 96},
    ]
    assert "statistics" not in boundary_response.data["metrics"]["blood_oxygen"]


@pytest.mark.django_db
def test_wearable_window_uses_a_narrow_measurement_projection_without_changing_response(
    project_patient, doctor, active_prescription
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    window_ended_at = started_at + timedelta(seconds=480)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        expected_duration_seconds=180,
    )
    device, binding = _bound_device(project_patient, doctor)
    measurement = _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.HEART_RATE,
        measured_at=started_at + timedelta(seconds=30),
        heart_rate=78,
    )
    measurement.raw_payload = {"secret": "must-not-be-selected"}
    measurement.save(update_fields=["raw_payload", "updated_at"])

    with CaptureQueriesContext(connection) as queries:
        response = _client(doctor).get(
            f"/api/training/videos/{video.id}/wearable-window/"
        )

    measurement_queries = [
        query["sql"]
        for query in queries.captured_queries
        if "wearables_wearablemeasurement" in query["sql"].lower()
    ]
    assert measurement_queries
    assert all("raw_payload" not in query.lower() for query in measurement_queries)
    assert response.status_code == 200
    assert response.data == {
        "available": True,
        "window_started_at": started_at.isoformat(),
        "window_ended_at": window_ended_at.isoformat(),
        "expected_duration_seconds": 180,
        "buffer_seconds": 300,
        "metrics": {
            "heart_rate": {
                "points": [
                    {
                        "measured_at": (started_at + timedelta(seconds=30)).isoformat(),
                        "value": 78,
                    }
                ],
                "statistics": {
                    "average": 78.0,
                    "maximum": 78,
                    "minimum": 78,
                    "count": 1,
                },
            }
        },
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("missing_field", "missing_value"),
    [
        ("training_started_at", None),
        ("expected_duration_seconds", None),
        ("expected_duration_seconds", 0),
    ],
)
def test_wearable_window_is_unavailable_without_fixed_window_inputs(
    project_patient, doctor, active_prescription, missing_field, missing_value
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )
    setattr(video, missing_field, missing_value)
    video.save(update_fields=[missing_field, "updated_at"])

    response = _client(doctor).get(f"/api/training/videos/{video.id}/wearable-window/")

    assert response.status_code == 200
    assert response.data == {"available": False}


@pytest.mark.django_db
def test_wearable_window_ignores_actual_training_end(
    project_patient, doctor, active_prescription
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    expected_duration_seconds = 180
    video_without_end = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        expected_duration_seconds=expected_duration_seconds,
    )
    video_with_early_end = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=30),
        expected_duration_seconds=expected_duration_seconds,
    )
    device, binding = _bound_device(project_patient, doctor)
    _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.HEART_RATE,
        measured_at=started_at + timedelta(seconds=240),
        heart_rate=88,
    )

    response_without_end = _client(doctor).get(
        f"/api/training/videos/{video_without_end.id}/wearable-window/"
    )
    response_with_early_end = _client(doctor).get(
        f"/api/training/videos/{video_with_early_end.id}/wearable-window/"
    )

    assert response_without_end.status_code == 200
    assert response_with_early_end.status_code == 200
    for field in (
        "window_started_at",
        "window_ended_at",
        "expected_duration_seconds",
        "buffer_seconds",
        "metrics",
    ):
        assert response_without_end.data[field] == response_with_early_end.data[field]


@pytest.mark.django_db
def test_wearable_window_filters_invalid_attribution_and_other_patient(
    project_patient, doctor, active_prescription
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )
    device, binding = _bound_device(project_patient, doctor)
    outside = _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.HEART_RATE,
        measured_at=started_at,
        heart_rate=88,
    )
    outside.attribution_status = WearableMeasurement.AttributionStatus.OUTSIDE_BINDING
    outside.save(update_fields=["attribution_status", "updated_at"])
    other_patient, other_device, other_binding = _other_patient_binding(doctor)
    _measurement(
        patient=other_patient,
        device=other_device,
        binding=other_binding,
        metric_type=WearableMeasurement.MetricType.HEART_RATE,
        measured_at=started_at,
        heart_rate=99,
    )

    response = _client(doctor).get(f"/api/training/videos/{video.id}/wearable-window/")

    assert response.data == {"available": False}


@pytest.mark.django_db
@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=True)
def test_wearable_window_is_hidden_from_inaccessible_doctor(
    project_patient, doctor, active_prescription
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )

    response = _client(_other_doctor()).get(f"/api/training/videos/{video.id}/wearable-window/")

    assert response.status_code == 404
    assert response.headers["Content-Type"].startswith("application/json")


@pytest.mark.django_db
@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=False)
def test_wearable_window_is_visible_to_other_doctor_by_default(
    project_patient,
    active_prescription,
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )

    response = _client(_other_doctor()).get(
        f"/api/training/videos/{video.id}/wearable-window/"
    )

    assert response.status_code == 200
    assert response.data == {"available": False}


@pytest.mark.django_db
def test_wearable_window_does_not_enqueue_sync(project_patient, doctor, active_prescription):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )
    before = WearableSyncRun.objects.count()

    response = _client(doctor).get(f"/api/training/videos/{video.id}/wearable-window/")

    assert response.status_code == 200
    assert WearableSyncRun.objects.count() == before


@pytest.mark.django_db
def test_wearable_window_only_includes_nonempty_metrics(
    project_patient, doctor, active_prescription
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )
    device, binding = _bound_device(project_patient, doctor)
    _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.BLOOD_OXYGEN,
        measured_at=started_at,
        blood_oxygen=97,
    )

    response = _client(doctor).get(f"/api/training/videos/{video.id}/wearable-window/")

    assert response.status_code == 200
    assert set(response.data["metrics"]) == {"blood_oxygen"}


@pytest.mark.django_db
def test_wearable_window_is_unavailable_without_measurements(
    project_patient, doctor, active_prescription
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )

    response = _client(doctor).get(f"/api/training/videos/{video.id}/wearable-window/")

    assert response.status_code == 200
    assert response.data == {"available": False}


@pytest.mark.django_db
def test_wearable_window_orders_same_timestamp_points_by_id(
    project_patient, doctor, active_prescription
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )
    device, binding = _bound_device(project_patient, doctor)
    first = _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.HEART_RATE,
        measured_at=started_at + timedelta(seconds=1),
        heart_rate=80,
    )
    second = _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.HEART_RATE,
        measured_at=started_at + timedelta(seconds=1),
        heart_rate=81,
    )

    response = _client(doctor).get(f"/api/training/videos/{video.id}/wearable-window/")

    assert response.status_code == 200
    assert first.id < second.id
    assert [point["value"] for point in response.data["metrics"]["heart_rate"]["points"]] == [
        80,
        81,
    ]
