import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.wearables.models import (
    WearableBinding,
    WearableDailySummary,
    WearableMeasurement,
    WearableSyncRun,
)


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _measurement(*, patient, device, metric_type, measured_at, **values):
    return WearableMeasurement.objects.create(
        provider=device.provider,
        device=device,
        patient=patient,
        metric_type=metric_type,
        measured_at=measured_at,
        attribution_status=WearableMeasurement.AttributionStatus.ATTRIBUTED,
        source_fingerprint=hashlib.sha256(
            f"{metric_type}-{measured_at.isoformat()}-{values}".encode()
        ).hexdigest(),
        raw_payload={"secret": "must-not-leak"},
        **values,
    )


@pytest.mark.django_db
def test_measurements_require_accessible_patient_and_matching_project_patient(
    doctor, project_patient, other_project_patient, wearable_device
):
    other_doctor = User.objects.create_user(
        phone="13800009999", password="pass123456", name="其他医生", role=User.Role.DOCTOR
    )
    hidden_patient = Patient.objects.create(
        name="不可见", gender=Patient.Gender.UNKNOWN, age=70, phone="13900009999", primary_doctor=other_doctor
    )
    hidden_project = StudyProject.objects.create(name="不可见研究", created_by=other_doctor)
    hidden_group = StudyGroup.objects.create(project=hidden_project, name="组", target_ratio=1)
    hidden_pp = ProjectPatient.objects.create(
        project=hidden_project, patient=hidden_patient, group=hidden_group
    )

    hidden = _client(doctor).get(
        f"/api/wearables/patients/{hidden_patient.id}/measurements/",
        {"project_patient": hidden_pp.id, "metric_type": "heart_rate", "start": "2026-07-01", "end": "2026-07-02"},
    )
    mismatched = _client(doctor).get(
        f"/api/wearables/patients/{project_patient.patient_id}/measurements/",
        {"project_patient": other_project_patient.id, "metric_type": "heart_rate", "start": "2026-07-01", "end": "2026-07-02"},
    )

    assert hidden.status_code == 404
    assert mismatched.status_code == 404


@pytest.mark.django_db
def test_measurement_buckets_use_shanghai_boundaries_and_hide_raw_payload(
    doctor, project_patient, patient, wearable_device
):
    ProjectPatient.objects.filter(pk=project_patient.pk).update(
        enrolled_at=datetime(2026, 7, 1, tzinfo=UTC)
    )
    measured = datetime(2026, 7, 21, 16, 1, tzinfo=UTC)  # 上海 00:01
    _measurement(patient=patient, device=wearable_device, metric_type="heart_rate", measured_at=measured, heart_rate=60)
    _measurement(patient=patient, device=wearable_device, metric_type="heart_rate", measured_at=datetime(2026, 7, 21, 16, 4, tzinfo=UTC), heart_rate=80)
    _measurement(patient=patient, device=wearable_device, metric_type="blood_pressure", measured_at=measured, systolic=120, diastolic=80)
    _measurement(patient=patient, device=wearable_device, metric_type="blood_pressure", measured_at=datetime(2026, 7, 21, 16, 4, tzinfo=UTC), systolic=130, diastolic=90)
    params = {"project_patient": project_patient.id, "start": "2026-07-22", "end": "2026-07-22"}

    raw = _client(doctor).get(
        f"/api/wearables/patients/{patient.id}/measurements/", {**params, "metric_type": "heart_rate", "bucket": "raw"}
    )
    five_minutes = _client(doctor).get(
        f"/api/wearables/patients/{patient.id}/measurements/", {**params, "metric_type": "heart_rate", "bucket": "5m"}
    )
    larger_buckets = [
        _client(doctor).get(
            f"/api/wearables/patients/{patient.id}/measurements/",
            {**params, "metric_type": "heart_rate", "bucket": bucket},
        )
        for bucket in ("15m", "30m", "1h")
    ]
    bp = _client(doctor).get(
        f"/api/wearables/patients/{patient.id}/measurements/", {**params, "metric_type": "blood_pressure", "bucket": "5m"}
    )

    assert raw.status_code == five_minutes.status_code == bp.status_code == 200
    assert all(response.status_code == 200 for response in larger_buckets)
    assert [item["heart_rate"] for item in raw.data["items"]] == [60, 80]
    assert "raw_payload" not in raw.data["items"][0]
    assert five_minutes.data["items"] == [{"start": "2026-07-22T00:00:00+08:00", "end": "2026-07-22T00:05:00+08:00", "count": 2, "heart_rate_avg": 70.0}]
    assert [response.data["items"][0]["heart_rate_avg"] for response in larger_buckets] == [70.0, 70.0, 70.0]
    assert bp.data["items"] == [{"start": "2026-07-22T00:00:00+08:00", "end": "2026-07-22T00:05:00+08:00", "count": 2, "systolic_avg": 125.0, "diastolic_avg": 85.0}]

    invalid_page = _client(doctor).get(
        f"/api/wearables/patients/{patient.id}/measurements/",
        {**params, "metric_type": "heart_rate", "page": 2, "page_size": 2},
    )
    oversized_page = _client(doctor).get(
        f"/api/wearables/patients/{patient.id}/measurements/",
        {**params, "metric_type": "heart_rate", "page_size": 501},
    )
    too_long = _client(doctor).get(
        f"/api/wearables/patients/{patient.id}/measurements/",
        {"project_patient": project_patient.id, "metric_type": "heart_rate", "start": "2026-06-01", "end": "2026-07-02"},
    )
    assert invalid_page.status_code == oversized_page.status_code == too_long.status_code == 400


@pytest.mark.django_db
def test_project_window_clips_raw_points_and_excludes_partial_summary_days(
    doctor, project_patient, patient, wearable_device
):
    ProjectPatient.objects.filter(pk=project_patient.pk).update(enrolled_at=datetime(2026, 7, 21, 16, tzinfo=UTC))
    project_patient.refresh_from_db()
    project_patient.project.completed_at = datetime(2026, 7, 23, 4, tzinfo=UTC)
    project_patient.project.save(update_fields=["completed_at"])
    _measurement(patient=patient, device=wearable_device, metric_type="heart_rate", measured_at=datetime(2026, 7, 21, 15, 59, tzinfo=UTC), heart_rate=55)
    _measurement(patient=patient, device=wearable_device, metric_type="heart_rate", measured_at=datetime(2026, 7, 21, 17, tzinfo=UTC), heart_rate=65)
    _measurement(patient=patient, device=wearable_device, metric_type="heart_rate", measured_at=datetime(2026, 7, 23, 4, tzinfo=UTC), heart_rate=75)
    WearableDailySummary.objects.create(patient=patient, record_date=date(2026, 7, 22), heart_rate_avg=Decimal("65"), heart_rate_count=1)
    WearableDailySummary.objects.create(patient=patient, record_date=date(2026, 7, 23), heart_rate_avg=Decimal("75"), heart_rate_count=1)

    raw = _client(doctor).get(f"/api/wearables/patients/{patient.id}/measurements/", {"project_patient": project_patient.id, "metric_type": "heart_rate", "start": "2026-07-22", "end": "2026-07-23"})
    daily = _client(doctor).get(f"/api/wearables/patients/{patient.id}/daily-summaries/", {"project_patient": project_patient.id, "start": "2026-07-22", "end": "2026-07-23"})

    assert [item["heart_rate"] for item in raw.data["items"]] == [65]
    assert [item["record_date"] for item in daily.data["items"]] == ["2026-07-22"]


@pytest.mark.django_db
def test_project_summary_excludes_raw_points_from_partial_enrollment_and_completion_days(
    doctor, project_patient, patient, wearable_device
):
    ProjectPatient.objects.filter(pk=project_patient.pk).update(enrolled_at=datetime(2026, 7, 21, 20, tzinfo=UTC))
    project_patient.project.completed_at = datetime(2026, 7, 23, 4, tzinfo=UTC)
    project_patient.project.save(update_fields=["completed_at"])
    _measurement(patient=patient, device=wearable_device, metric_type="heart_rate", measured_at=datetime(2026, 7, 21, 21, tzinfo=UTC), heart_rate=60)
    _measurement(patient=patient, device=wearable_device, metric_type="heart_rate", measured_at=datetime(2026, 7, 23, 3, tzinfo=UTC), heart_rate=80)

    response = _client(doctor).get(
        f"/api/wearables/projects/{project_patient.project_id}/summary/",
        {"metric_type": "heart_rate", "start": "2026-07-22", "end": "2026-07-23"},
    )
    group = response.data["groups"][0]
    assert (group["eligible_days"], group["valid_data_days"], group["mean"], group["measurement_count"]) == (0, 0, None, 0)


@pytest.mark.django_db
def test_daily_steps_are_only_daily_and_project_summary_is_group_scoped(
    doctor, project_patient, patient, wearable_device
):
    ProjectPatient.objects.filter(pk=project_patient.pk).update(
        enrolled_at=datetime(2026, 7, 1, tzinfo=UTC)
    )
    WearableDailySummary.objects.create(
        patient=patient, record_date=date(2026, 7, 22), steps=5000, heart_rate_avg=Decimal("70"), heart_rate_min=60, heart_rate_max=80, heart_rate_count=2
    )
    _measurement(patient=patient, device=wearable_device, metric_type="heart_rate", measured_at=datetime(2026, 7, 21, 16, tzinfo=UTC), heart_rate=60)
    _measurement(patient=patient, device=wearable_device, metric_type="heart_rate", measured_at=datetime(2026, 7, 21, 17, tzinfo=UTC), heart_rate=80)
    invalid_steps = _client(doctor).get(
        f"/api/wearables/patients/{patient.id}/daily-summaries/",
        {"project_patient": project_patient.id, "start": "2026-07-22", "end": "2026-07-22", "bucket": "15m"},
    )
    summary = _client(doctor).get(
        f"/api/wearables/projects/{project_patient.project_id}/summary/",
        {"metric_type": "heart_rate", "start": "2026-07-22", "end": "2026-07-22"},
    )

    assert invalid_steps.status_code == 400
    assert summary.status_code == 200, summary.data
    group = summary.data["groups"][0]
    assert group["patient_count"] == 1
    assert group["valid_data_days"] == 1
    assert group["mean"] == 70.0
    assert group["min"] == 60
    assert group["max"] == 80
    assert group["measurement_count"] == 2
    assert group["missing_rate"] == 0.0


@pytest.mark.django_db
def test_sync_status_does_not_expose_previous_patients_sync_runs_after_device_rebinding(
    doctor, project_patient, other_project_patient, wearable_device
):
    old_bound_at = datetime(2026, 7, 20, tzinfo=UTC)
    switch_at = datetime(2026, 7, 21, tzinfo=UTC)
    first = WearableBinding.objects.create(
        patient=project_patient.patient,
        device=wearable_device,
        bound_at=old_bound_at,
        unbound_at=switch_at,
        bound_by=doctor,
        unbound_by=doctor,
    )
    old_run = WearableSyncRun.objects.create(
        device=wearable_device, metric_type="heart_rate", status=WearableSyncRun.Status.SUCCEEDED
    )
    WearableSyncRun.objects.filter(pk=old_run.pk).update(created_at=datetime(2026, 7, 20, 1, tzinfo=UTC))
    second = WearableBinding.objects.create(
        patient=other_project_patient.patient,
        device=wearable_device,
        bound_at=switch_at,
        bound_by=doctor,
    )

    before_new_run = _client(doctor).get(
        f"/api/wearables/patients/{other_project_patient.patient_id}/sync-status/"
    )
    new_run = WearableSyncRun.objects.create(
        device=wearable_device, metric_type="heart_rate", status=WearableSyncRun.Status.FAILED
    )
    WearableSyncRun.objects.filter(pk=new_run.pk).update(created_at=datetime(2026, 7, 21, 1, tzinfo=UTC))
    after_new_run = _client(doctor).get(
        f"/api/wearables/patients/{other_project_patient.patient_id}/sync-status/"
    )

    assert first.id != second.id
    assert before_new_run.data["last_sync_at"] is None
    assert before_new_run.data["metrics"][0]["status"] is None
    assert after_new_run.data["metrics"][0]["status"] == "failed"
    assert after_new_run.data["metrics"][0]["last_success_at"] is None


@pytest.mark.django_db
def test_sync_status_exposes_safe_bound_device_capabilities_without_contacting_provider(
    doctor, project_patient, wearable_device, monkeypatch
):
    from apps.wearables.capabilities import CapabilityProfile

    monkeypatch.setattr(
        "apps.wearables.services.queries.get_capability_profile",
        lambda provider, model: CapabilityProfile(
            measure_heart_rate="safe-code",
            measure_blood_pressure="safe-code",
        ),
    )
    binding = WearableBinding.objects.create(
        patient=project_patient.patient,
        device=wearable_device,
        bound_at=datetime.now(UTC),
        bound_by=doctor,
    )
    wearable_device.last_device_status = "offline"
    wearable_device.last_battery_level = 37
    wearable_device.last_communication_at = datetime(2026, 7, 24, 16, 30, tzinfo=UTC)
    wearable_device.save(
        update_fields=[
            "last_device_status",
            "last_battery_level",
            "last_communication_at",
        ]
    )

    response = _client(doctor).get(
        f"/api/wearables/patients/{project_patient.patient_id}/sync-status/"
    )

    assert response.status_code == 200
    assert response.data["binding_id"] == binding.id
    assert response.data["device_id"] == wearable_device.id
    assert response.data["model"] == wearable_device.model
    assert response.data["last_device_status"] == "offline"
    assert response.data["last_battery_level"] == 37
    assert response.data["last_communication_at"] == "2026-07-25T00:30:00+08:00"
    assert response.data["capabilities"] == {
        "ring": False,
        "measure_heart_rate": True,
        "measure_blood_pressure": True,
        "measure_blood_oxygen": False,
        "configure_heart_rate_interval": False,
        "configure_blood_pressure_interval": False,
        "configure_blood_oxygen_interval": False,
        "configure_step_switch": False,
    }
    assert "safe-code" not in str(response.data)
