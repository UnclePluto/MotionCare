from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.wearables.capabilities import CapabilityProfile, MODEL_CAPABILITIES
from apps.wearables.models import WearableBinding, WearableCommandLog, WearableMeasurement
from apps.wearables.providers import (
    ProviderCommandResult,
    ProviderDeviceStatus,
    ProviderError,
    ProviderMeasurement,
)
from apps.wearables.services.commands import (
    ActiveBindingRequired,
    DisabledDevice,
    UnsupportedCapability,
    check_device_status,
    send_device_command,
)
from apps.wearables.tasks import poll_queued_measurement


TEST_PROFILE = CapabilityProfile(
    ring="9018",
    measure_heart_rate="9012",
    measure_blood_pressure="9510",
    measure_blood_oxygen="9511",
    configure_heart_rate_interval="9013",
    configure_blood_pressure_interval="9512",
    configure_blood_oxygen_interval="9513",
    configure_step_switch="9014",
)


class StubProvider:
    def __init__(self, *, status=None, command_result=None, points=None, error=None):
        self.status = status
        self.command_result = command_result or ProviderCommandResult(0, "ok", {})
        self.points = points or []
        self.error = error
        self.commands = []
        self.closed = False

    def get_device_status(self, external_device_id):
        if self.error:
            raise self.error
        return self.status

    def send_command(self, external_device_id, command_code, command_value="", request_id=None):
        if self.error:
            raise self.error
        self.commands.append((external_device_id, command_code, command_value, request_id))
        return self.command_result

    def get_heart_rates(self, external_device_id, begin_at, end_at):
        if self.error:
            raise self.error
        return self.points

    def get_blood_pressures(self, external_device_id, begin_at, end_at):
        if self.error:
            raise self.error
        return self.points

    def get_blood_oxygen(self, external_device_id, begin_at, end_at):
        if self.error:
            raise self.error
        return self.points

    def close(self):
        self.closed = True


@pytest.fixture
def verified_capability(monkeypatch):
    monkeypatch.setitem(MODEL_CAPABILITIES, ("miwitracker", "TEST-MODEL"), TEST_PROFILE)


@pytest.fixture
def active_binding(db, wearable_device, patient, doctor):
    return WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=timezone.now() - timedelta(minutes=1),
        bound_by=doctor,
    )


def test_unknown_model_cannot_send_measurement_command(wearable_device):
    wearable_device.model = "UNKNOWN"

    with pytest.raises(UnsupportedCapability):
        send_device_command(
            device=wearable_device,
            command_type="measure_heart_rate",
            actor=None,
        )


@pytest.mark.django_db
def test_unknown_model_can_check_safe_status_without_returning_location(wearable_device, monkeypatch):
    wearable_device.model = "UNKNOWN"
    provider = StubProvider(
        status=ProviderDeviceStatus(
            external_device_id=wearable_device.external_device_id,
            model="UNKNOWN",
            status="online",
            battery_level=82,
            last_communication_at=datetime(2026, 7, 24, 2, tzinfo=UTC),
            raw_payload={"Latitude": 31.2, "Longitude": 121.5, "Imei": "dev-001"},
        )
    )
    monkeypatch.setattr("apps.wearables.services.commands._get_provider", lambda _: provider)

    result = check_device_status(wearable_device)

    assert result == {
        "device_id": wearable_device.id,
        "model": "UNKNOWN",
        "online": True,
        "battery_level": 82,
        "last_communication_at": "2026-07-24T02:00:00+00:00",
    }
    wearable_device.refresh_from_db()
    assert wearable_device.last_device_status == "online"
    assert provider.closed is True


@pytest.mark.django_db
def test_status_api_returns_only_the_safe_status_summary(api_client, doctor, wearable_device, monkeypatch):
    api_client.force_authenticate(doctor)
    monkeypatch.setattr(
        "apps.wearables.views.check_device_status",
        lambda _: {
            "device_id": wearable_device.id,
            "model": wearable_device.model,
            "online": False,
            "battery_level": 12,
            "last_communication_at": None,
        },
    )

    response = api_client.post(f"/api/wearables/devices/{wearable_device.id}/check-status/")

    assert response.status_code == 200
    assert set(response.data) == {
        "device_id",
        "model",
        "online",
        "battery_level",
        "last_communication_at",
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "command_type",
    [
        "ring",
        "measure_heart_rate",
        "configure_heart_rate_interval",
        "configure_step_switch",
    ],
)
def test_unverified_model_rejects_all_remote_commands(wearable_device, command_type):
    wearable_device.model = "UNKNOWN"

    with pytest.raises(UnsupportedCapability):
        send_device_command(wearable_device, command_type, actor=None)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("command_type", "expected_code"),
    [
        ("ring", "9018"),
        ("measure_heart_rate", "9012"),
        ("measure_blood_pressure", "9510"),
        ("measure_blood_oxygen", "9511"),
    ],
)
def test_verified_capability_sends_expected_command_code(
    wearable_device, verified_capability, command_type, expected_code, monkeypatch
):
    provider = StubProvider()
    monkeypatch.setattr("apps.wearables.services.commands._get_provider", lambda _: provider)

    command = send_device_command(wearable_device, command_type, actor=None)

    assert provider.commands[0][0:2] == (wearable_device.external_device_id, expected_code)
    assert command.command_code == expected_code
    assert command.status == WearableCommandLog.Status.SUCCEEDED


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("provider_code", "expected_status"),
    [
        (0, WearableCommandLog.Status.SUCCEEDED),
        (1803, WearableCommandLog.Status.QUEUED),
        (1800, WearableCommandLog.Status.OFFLINE),
        (1801, WearableCommandLog.Status.TIMEOUT),
        (1802, WearableCommandLog.Status.FAILED),
    ],
)
def test_vendor_command_codes_map_to_audited_status(
    wearable_device, verified_capability, provider_code, expected_status, monkeypatch
):
    provider = StubProvider(command_result=ProviderCommandResult(provider_code, "result", {}))
    monkeypatch.setattr("apps.wearables.services.commands._get_provider", lambda _: provider)

    command = send_device_command(wearable_device, "ring", actor=None)

    assert command.status == expected_status
    assert command.provider_code == str(provider_code)
    assert (command.completed_at is not None) is (expected_status != WearableCommandLog.Status.QUEUED)


@pytest.mark.django_db
def test_command_log_keeps_only_safe_parameter_summary(wearable_device, verified_capability, monkeypatch):
    provider = StubProvider()
    monkeypatch.setattr("apps.wearables.services.commands._get_provider", lambda _: provider)

    command = send_device_command(
        wearable_device,
        "configure_heart_rate_interval",
        actor=None,
        parameters={"interval_minutes": 15, "AccessToken": "secret", "Password": "secret", "KEY": "secret"},
    )

    assert command.request_payload == {"interval_minutes": 15}
    assert "secret" not in str(command.request_payload)
    assert provider.commands[0][2] == "15"


@pytest.mark.django_db
def test_unknown_command_and_disabled_device_never_call_provider(
    wearable_device, verified_capability, monkeypatch
):
    provider = StubProvider()
    monkeypatch.setattr("apps.wearables.services.commands._get_provider", lambda _: provider)

    with pytest.raises(UnsupportedCapability):
        send_device_command(wearable_device, "restart", actor=None)
    wearable_device.enabled = False
    with pytest.raises(DisabledDevice):
        send_device_command(wearable_device, "ring", actor=None)

    assert provider.commands == []
    assert WearableCommandLog.objects.count() == 0


@pytest.mark.django_db
def test_provider_error_is_recorded_without_sensitive_parameters(
    wearable_device, verified_capability, monkeypatch
):
    provider = StubProvider(error=RuntimeError("network down"))
    monkeypatch.setattr("apps.wearables.services.commands._get_provider", lambda _: provider)

    command = send_device_command(
        wearable_device,
        "ring",
        actor=None,
        parameters={"AccessToken": "secret"},
    )

    assert command.status == WearableCommandLog.Status.FAILED
    assert command.provider_code == ""
    assert command.request_payload == {}
    assert command.completed_at is not None


@pytest.mark.django_db
def test_each_repeated_command_creates_an_independent_log(
    wearable_device, verified_capability, monkeypatch
):
    provider = StubProvider()
    monkeypatch.setattr("apps.wearables.services.commands._get_provider", lambda _: provider)

    first = send_device_command(wearable_device, "ring", actor=None)
    second = send_device_command(wearable_device, "ring", actor=None)

    assert first.id != second.id
    assert WearableCommandLog.objects.filter(command_type="ring").count() == 2


@pytest.mark.django_db
def test_measurement_requires_an_active_binding(wearable_device, verified_capability):
    with pytest.raises(ActiveBindingRequired):
        send_device_command(wearable_device, "measure_heart_rate", actor=None, require_binding=True)


@pytest.mark.django_db
def test_queued_measurement_finds_only_a_new_real_point(
    wearable_device, verified_capability, active_binding, monkeypatch
):
    provider = StubProvider(command_result=ProviderCommandResult(1803, "queued", {}))
    monkeypatch.setattr("apps.wearables.services.commands._get_provider", lambda _: provider)
    monkeypatch.setattr("apps.wearables.tasks.poll_queued_measurement.apply_async", Mock())
    command = send_device_command(
        wearable_device,
        "measure_heart_rate",
        actor=None,
        require_binding=True,
    )
    command.created_at = timezone.now() - timedelta(seconds=10)
    command.save(update_fields=["created_at"])
    provider.points = [
        ProviderMeasurement(
            metric_type="heart_rate",
            measured_at=command.created_at,
            values={"heart_rate": 67},
            raw_payload={},
        ),
        ProviderMeasurement(
            metric_type="heart_rate",
            measured_at=command.created_at + timedelta(microseconds=1),
            values={"heart_rate": 68},
            raw_payload={},
        ),
    ]
    monkeypatch.setattr("apps.wearables.tasks._get_command_provider", lambda _: provider)

    poll_queued_measurement.run(command.id, attempt=0)

    command.refresh_from_db()
    assert command.status == WearableCommandLog.Status.SUCCEEDED
    assert WearableMeasurement.objects.get(device=wearable_device).heart_rate == 68


@pytest.mark.django_db
def test_queued_measurement_marks_timeout_at_sixth_poll_without_fabricating_data(
    wearable_device, verified_capability, active_binding, monkeypatch
):
    provider = StubProvider(command_result=ProviderCommandResult(1803, "queued", {}))
    monkeypatch.setattr("apps.wearables.services.commands._get_provider", lambda _: provider)
    monkeypatch.setattr("apps.wearables.tasks.poll_queued_measurement.apply_async", Mock())
    command = send_device_command(
        wearable_device,
        "measure_heart_rate",
        actor=None,
        require_binding=True,
    )
    monkeypatch.setattr("apps.wearables.tasks._get_command_provider", lambda _: provider)
    retry = Mock()
    monkeypatch.setattr("apps.wearables.tasks.poll_queued_measurement.apply_async", retry)

    poll_queued_measurement.run(command.id, attempt=6)

    command.refresh_from_db()
    assert command.status == WearableCommandLog.Status.TIMEOUT
    assert WearableMeasurement.objects.count() == 0
    retry.assert_not_called()


@pytest.mark.django_db
def test_queued_measurement_retries_once_before_the_sixth_poll(
    wearable_device, verified_capability, active_binding, monkeypatch
):
    provider = StubProvider(command_result=ProviderCommandResult(1803, "queued", {}))
    monkeypatch.setattr("apps.wearables.services.commands._get_provider", lambda _: provider)
    monkeypatch.setattr("apps.wearables.tasks.poll_queued_measurement.apply_async", Mock())
    command = send_device_command(
        wearable_device,
        "measure_heart_rate",
        actor=None,
        require_binding=True,
    )
    monkeypatch.setattr("apps.wearables.tasks._get_command_provider", lambda _: provider)
    retry = Mock()
    monkeypatch.setattr("apps.wearables.tasks.poll_queued_measurement.apply_async", retry)

    poll_queued_measurement.run(command.id, attempt=5)

    command.refresh_from_db()
    assert command.status == WearableCommandLog.Status.QUEUED
    retry.assert_called_once_with(args=[command.id], kwargs={"attempt": 6}, countdown=10)


@pytest.mark.django_db
def test_queued_measurement_marks_offline_when_history_request_reports_offline(
    wearable_device, verified_capability, active_binding, monkeypatch
):
    provider = StubProvider(command_result=ProviderCommandResult(1803, "queued", {}))
    monkeypatch.setattr("apps.wearables.services.commands._get_provider", lambda _: provider)
    monkeypatch.setattr("apps.wearables.tasks.poll_queued_measurement.apply_async", Mock())
    command = send_device_command(
        wearable_device,
        "measure_heart_rate",
        actor=None,
        require_binding=True,
    )
    provider.error = ProviderError("设备离线", code=1800)
    monkeypatch.setattr("apps.wearables.tasks._get_command_provider", lambda _: provider)

    poll_queued_measurement.run(command.id, attempt=1)

    command.refresh_from_db()
    assert command.status == WearableCommandLog.Status.OFFLINE
    assert command.completed_at is not None


@pytest.mark.django_db
def test_patient_actions_require_row_level_access_and_active_binding(
    api_client, doctor, wearable_device, monkeypatch
):
    api_client.force_authenticate(doctor)
    foreign_doctor = User.objects.create_user(
        phone="13800002222",
        password="pass123456",
        name="外部医生",
        role=User.Role.DOCTOR,
    )
    foreign_patient = Patient.objects.create(
        name="外部患者",
        gender=Patient.Gender.UNKNOWN,
        age=70,
        phone="13900003333",
        primary_doctor=foreign_doctor,
    )
    foreign_project = StudyProject.objects.create(name="外部研究", created_by=foreign_doctor)
    foreign_group = StudyGroup.objects.create(project=foreign_project, name="对照组", target_ratio=1)
    ProjectPatient.objects.create(
        project=foreign_project,
        patient=foreign_patient,
        group=foreign_group,
    )
    WearableBinding.objects.create(
        patient=foreign_patient,
        device=wearable_device,
        bound_at=timezone.now(),
        bound_by=doctor,
    )
    monkeypatch.setitem(MODEL_CAPABILITIES, ("miwitracker", "TEST-MODEL"), TEST_PROFILE)

    response = api_client.post(
        f"/api/wearables/patients/{foreign_patient.id}/measure/",
        {"metric_type": "heart_rate"},
        format="json",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_sync_endpoint_only_dispatches_whitelisted_metrics(
    api_client, doctor, project_patient, wearable_device, active_binding, monkeypatch
):
    api_client.force_authenticate(doctor)
    dispatched = Mock()
    monkeypatch.setattr("apps.wearables.views.sync_device_metric.delay", dispatched)

    rejected = api_client.post(
        f"/api/wearables/patients/{project_patient.patient_id}/sync/",
        {"metric_type": "location", "AccessToken": "secret"},
        format="json",
    )
    accepted = api_client.post(
        f"/api/wearables/patients/{project_patient.patient_id}/sync/",
        {"metric_type": "heart_rate"},
        format="json",
    )

    assert rejected.status_code == 400
    assert accepted.status_code == 202
    assert accepted.data == {"metric_types": ["heart_rate"], "status": "queued"}
    dispatched.assert_called_once_with(wearable_device.id, "heart_rate")
