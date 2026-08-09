import re
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.wearables.models import WearableBinding, WearableDevice, WearableSyncRun


def _device_payload(**overrides):
    payload = {"imei": "860123456789012"}
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_device_create_from_imei_fills_identity_defaults_and_short_code(
    api_client, doctor
):
    api_client.force_authenticate(doctor)

    created = api_client.post("/api/wearables/devices/", _device_payload(), format="json")

    assert created.status_code == 201, created.data
    assert created.data["provider"] == "miwitracker"
    assert created.data["external_device_id"] == "860123456789012"
    assert created.data["identifier_type"] == "imei"
    assert created.data["model"] == ""
    assert created.data["enabled"] is True
    assert re.fullmatch(r"\d{4}", created.data["short_code"])
    device_id = created.data["id"]

    listed = api_client.get("/api/wearables/devices/")
    assert listed.status_code == 200, listed.data
    assert [device["id"] for device in listed.data] == [device_id]

    patched = api_client.patch(
        f"/api/wearables/devices/{device_id}/",
        {"enabled": False, "model": "UPDATED-MODEL"},
        format="json",
    )
    assert patched.status_code == 200, patched.data
    assert patched.data["enabled"] is False
    assert patched.data["model"] == "UPDATED-MODEL"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "imei",
    ["", "12345678901234", "1234567890123456", "12345678901234A", "１２３４５６７８９０１２３４５"],
)
def test_device_create_rejects_invalid_imei(api_client, doctor, imei):
    api_client.force_authenticate(doctor)

    response = api_client.post("/api/wearables/devices/", {"imei": imei}, format="json")

    assert response.status_code == 400, response.data
    assert "imei" in response.data


@pytest.mark.django_db
def test_device_list_returns_permission_safe_binding_and_successful_sync_contract_in_one_query(
    api_client,
    doctor,
    project,
    group,
    project_patient,
    other_project_patient,
    wearable_device,
    django_assert_num_queries,
):
    successful_at = datetime(2026, 7, 24, 2, 30, tzinfo=UTC)
    older_success = WearableSyncRun.objects.create(
        device=wearable_device,
        metric_type="heart_rate",
        status=WearableSyncRun.Status.SUCCEEDED,
    )
    latest_success = WearableSyncRun.objects.create(
        device=wearable_device,
        metric_type="steps",
        status=WearableSyncRun.Status.SUCCEEDED,
    )
    later_failure = WearableSyncRun.objects.create(
        device=wearable_device,
        metric_type="blood_oxygen",
        status=WearableSyncRun.Status.FAILED,
    )
    WearableSyncRun.objects.filter(pk=older_success.pk).update(
        updated_at=successful_at - timedelta(hours=1)
    )
    WearableSyncRun.objects.filter(pk=latest_success.pk).update(updated_at=successful_at)
    WearableSyncRun.objects.filter(pk=later_failure.pk).update(
        updated_at=successful_at + timedelta(hours=1)
    )
    WearableBinding.objects.create(
        patient=project_patient.patient,
        device=wearable_device,
        bound_at=successful_at - timedelta(days=1),
        bound_by=doctor,
    )

    previously_bound_device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-unbound",
        identifier_type="device_id",
        model="TEST-MODEL",
        short_code="1001",
    )
    WearableBinding.objects.create(
        patient=other_project_patient.patient,
        device=previously_bound_device,
        bound_at=successful_at - timedelta(days=2),
        unbound_at=successful_at - timedelta(days=1),
        bound_by=doctor,
        unbound_by=doctor,
    )
    historical_success = WearableSyncRun.objects.create(
        device=previously_bound_device,
        metric_type="steps",
        status=WearableSyncRun.Status.SUCCEEDED,
    )
    WearableSyncRun.objects.filter(pk=historical_success.pk).update(
        updated_at=successful_at - timedelta(days=1)
    )

    bound_without_sync = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-no-sync",
        identifier_type="device_id",
        model="TEST-MODEL",
        short_code="1002",
    )
    WearableBinding.objects.create(
        patient=other_project_patient.patient,
        device=bound_without_sync,
        bound_at=successful_at,
        bound_by=doctor,
    )

    disabled_patient = Patient.objects.create(
        name="王小明",
        gender=Patient.Gender.UNKNOWN,
        age=66,
        phone="13900004444",
        primary_doctor=doctor,
    )
    ProjectPatient.objects.create(
        project=project,
        patient=disabled_patient,
        group=group,
    )
    disabled_bound_device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-disabled",
        identifier_type="device_id",
        model="TEST-MODEL",
        short_code="1003",
        enabled=False,
    )
    WearableBinding.objects.create(
        patient=disabled_patient,
        device=disabled_bound_device,
        bound_at=successful_at,
        bound_by=doctor,
    )

    foreign_doctor = User.objects.create_user(
        phone="13800005555",
        password="pass123456",
        name="外部医生",
        role=User.Role.DOCTOR,
    )
    foreign_patient = Patient.objects.create(
        name="赵敏",
        gender=Patient.Gender.UNKNOWN,
        age=65,
        phone="13900005555",
        primary_doctor=foreign_doctor,
    )
    foreign_project = StudyProject.objects.create(name="外部研究", created_by=foreign_doctor)
    foreign_group = StudyGroup.objects.create(
        project=foreign_project,
        name="外部组",
        target_ratio=1,
    )
    ProjectPatient.objects.create(
        project=foreign_project,
        patient=foreign_patient,
        group=foreign_group,
    )
    inaccessible_bound_device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-inaccessible",
        identifier_type="device_id",
        model="TEST-MODEL",
        short_code="1004",
    )
    WearableBinding.objects.create(
        patient=foreign_patient,
        device=inaccessible_bound_device,
        bound_at=successful_at,
        bound_by=foreign_doctor,
    )

    api_client.force_authenticate(doctor)
    with django_assert_num_queries(1):
        response = api_client.get("/api/wearables/devices/")

    assert response.status_code == 200, response.data
    devices = {item["short_code"]: item for item in response.data}
    assert devices["0826"]["is_bound"] is True
    assert devices["0826"]["current_patient_name"] == "患*"
    assert devices["0826"]["last_sync_at"] == "2026-07-24T10:30:00+08:00"
    assert devices["1001"]["is_bound"] is False
    assert devices["1001"]["current_patient_name"] is None
    assert devices["1001"]["last_sync_at"] == "2026-07-23T10:30:00+08:00"
    assert devices["1002"]["is_bound"] is True
    assert devices["1002"]["current_patient_name"] == "患*"
    assert devices["1002"]["last_sync_at"] is None
    assert devices["1003"]["enabled"] is False
    assert devices["1003"]["is_bound"] is True
    assert devices["1003"]["current_patient_name"] == "王*"
    assert devices["1004"]["is_bound"] is True
    assert devices["1004"]["current_patient_name"] == "赵*"

    admin = User.objects.create_user(
        phone="13800006666",
        password="pass123456",
        name="管理员",
        role=User.Role.ADMIN,
    )
    api_client.force_authenticate(admin)
    admin_response = api_client.get("/api/wearables/devices/")
    admin_devices = {item["short_code"]: item for item in admin_response.data}
    assert admin_devices["1004"]["is_bound"] is True
    assert admin_devices["1004"]["current_patient_name"] == "赵*"


@pytest.mark.django_db
def test_device_create_rejects_client_supplied_short_code(api_client, doctor):
    api_client.force_authenticate(doctor)

    response = api_client.post(
        "/api/wearables/devices/",
        _device_payload(short_code="9999"),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "short_code" in response.data
    assert not WearableDevice.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "other-provider"),
        ("external_device_id", "new-device-id"),
        ("identifier_type", "serial"),
        ("short_code", "9999"),
    ],
)
def test_device_patch_rejects_identity_fields(api_client, doctor, wearable_device, field, value):
    api_client.force_authenticate(doctor)
    previous_value = getattr(wearable_device, field)

    response = api_client.patch(
        f"/api/wearables/devices/{wearable_device.id}/",
        {field: value},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert field in str(response.data)
    wearable_device.refresh_from_db()
    assert getattr(wearable_device, field) == previous_value


@pytest.mark.django_db
def test_device_create_reports_duplicate_imei(api_client, doctor):
    api_client.force_authenticate(doctor)
    first = api_client.post("/api/wearables/devices/", _device_payload(), format="json")

    duplicate = api_client.post("/api/wearables/devices/", _device_payload(), format="json")

    assert first.status_code == 201, first.data
    assert duplicate.status_code == 409, duplicate.data
    assert duplicate.data == {"detail": "该 IMEI 已存在。"}


@pytest.mark.django_db
def test_device_create_rejects_existing_imei_from_another_provider(api_client, doctor):
    WearableDevice.objects.create(
        provider="legacy-provider",
        external_device_id="860123456789012",
        identifier_type="imei",
        model="LEGACY-MODEL",
        short_code="4321",
    )
    api_client.force_authenticate(doctor)

    response = api_client.post("/api/wearables/devices/", _device_payload(), format="json")

    assert response.status_code == 409, response.data
    assert response.data == {"detail": "该 IMEI 已存在。"}
    assert WearableDevice.objects.filter(external_device_id="860123456789012").count() == 1


@pytest.mark.django_db
def test_device_create_retries_after_actual_short_code_unique_conflict_in_new_savepoint(
    api_client, doctor, wearable_device, monkeypatch
):
    api_client.force_authenticate(doctor)
    generated_codes = iter([wearable_device.short_code, "0008"])
    monkeypatch.setattr(
        "apps.wearables.serializers.generate_device_short_code",
        lambda: next(generated_codes),
    )

    response = api_client.post("/api/wearables/devices/", _device_payload(), format="json")

    assert response.status_code == 201, response.data
    assert response.data["short_code"] == "0008"
    assert WearableDevice.objects.filter(short_code=wearable_device.short_code).count() == 1


@pytest.mark.django_db
def test_device_short_code_keeps_leading_zeros(api_client, doctor, monkeypatch):
    api_client.force_authenticate(doctor)
    monkeypatch.setattr("apps.wearables.services.short_codes.secrets.randbelow", lambda _: 7)

    response = api_client.post("/api/wearables/devices/", _device_payload(), format="json")

    assert response.status_code == 201, response.data
    assert response.data["short_code"] == "0007"


@pytest.mark.django_db
def test_short_code_retries_random_collision_before_creating(api_client, doctor, wearable_device, monkeypatch):
    api_client.force_authenticate(doctor)
    values = iter([826, 9])
    monkeypatch.setattr(
        "apps.wearables.services.short_codes.secrets.randbelow", lambda _: next(values)
    )

    response = api_client.post("/api/wearables/devices/", _device_payload(), format="json")

    assert response.status_code == 201, response.data
    assert response.data["short_code"] == "0009"


@pytest.mark.django_db
def test_short_code_uses_sequential_fallback_after_random_space_is_exhausted(monkeypatch):
    from apps.wearables.services.short_codes import generate_device_short_code

    WearableDevice.objects.bulk_create(
        [
            WearableDevice(
                provider="provider",
                external_device_id=f"device-{value}",
                identifier_type="device_id",
                short_code=f"{value:04d}",
            )
            for value in range(1, 33)
        ]
    )
    monkeypatch.setattr("apps.wearables.services.short_codes.secrets.randbelow", lambda _: 1)

    assert generate_device_short_code() == "0000"


@pytest.mark.django_db
def test_short_code_raises_when_all_four_digit_codes_are_used():
    from apps.wearables.services.short_codes import ShortCodeExhausted, generate_device_short_code

    WearableDevice.objects.bulk_create(
        [
            WearableDevice(
                provider="provider",
                external_device_id=f"device-{value}",
                identifier_type="device_id",
                short_code=f"{value:04d}",
            )
            for value in range(10_000)
        ],
        batch_size=500,
    )

    with pytest.raises(ShortCodeExhausted, match="四位设备简码已用尽"):
        generate_device_short_code()


@pytest.mark.django_db
def test_bind_project_patient_resolves_global_patient(
    api_client, doctor, project_patient, wearable_device
):
    api_client.force_authenticate(doctor)

    response = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["patient_id"] == project_patient.patient_id
    assert response.data["device_id"] == wearable_device.id
    assert WearableBinding.objects.get(id=response.data["id"]).patient_id == project_patient.patient_id


@pytest.mark.django_db
def test_repeated_bind_for_same_patient_and_device_returns_existing_binding(
    api_client, doctor, project_patient, wearable_device
):
    api_client.force_authenticate(doctor)
    first = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )

    response = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )

    assert first.status_code == 201, first.data
    assert response.status_code == 200, response.data
    assert response.data["id"] == first.data["id"]
    assert WearableBinding.objects.filter(patient_id=project_patient.patient_id).count() == 1


@pytest.mark.django_db
def test_patient_with_another_active_device_returns_conflict(
    api_client, doctor, project_patient, wearable_device
):
    other_device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-002",
        identifier_type="device_id",
        short_code="0202",
    )
    api_client.force_authenticate(doctor)
    api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )

    response = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": other_device.short_code},
        format="json",
    )

    assert response.status_code == 409, response.data
    assert "患者" in str(response.data)


@pytest.mark.django_db
def test_rebound_device_does_not_overlap_previous_patient(
    api_client, doctor, project_patient, other_project_patient, wearable_device
):
    api_client.force_authenticate(doctor)
    first = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )

    response = api_client.post(
        f"/api/wearables/project-patients/{other_project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )

    assert first.status_code == 201, first.data
    assert response.status_code == 409, response.data
    assert "设备" in str(response.data)


@pytest.mark.django_db
def test_device_binding_conflict_includes_masked_name_for_any_enrolled_patient(
    api_client,
    doctor,
    project,
    group,
    project_patient,
    wearable_device,
):
    visible_patient = Patient.objects.create(
        name="王小明",
        gender=Patient.Gender.UNKNOWN,
        age=67,
        phone="13900006666",
        primary_doctor=doctor,
    )
    visible_project_patient = ProjectPatient.objects.create(
        project=project,
        patient=visible_patient,
        group=group,
    )
    WearableBinding.objects.create(
        patient=visible_patient,
        device=wearable_device,
        bound_at=timezone.now(),
        bound_by=doctor,
    )
    api_client.force_authenticate(doctor)

    visible_response = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )

    assert visible_project_patient.patient_id == visible_patient.id
    assert visible_response.status_code == 409, visible_response.data
    assert visible_response.data == {"detail": "设备已绑定患者王*。"}

    WearableBinding.objects.filter(device=wearable_device).delete()
    foreign_doctor = User.objects.create_user(
        phone="13800007778",
        password="pass123456",
        name="外部医生",
        role=User.Role.DOCTOR,
    )
    foreign_patient = Patient.objects.create(
        name="赵敏",
        gender=Patient.Gender.UNKNOWN,
        age=65,
        phone="13900007778",
        primary_doctor=foreign_doctor,
    )
    foreign_project = StudyProject.objects.create(name="外部项目", created_by=foreign_doctor)
    foreign_group = StudyGroup.objects.create(
        project=foreign_project,
        name="外部组",
        target_ratio=1,
    )
    ProjectPatient.objects.create(
        project=foreign_project,
        patient=foreign_patient,
        group=foreign_group,
    )
    WearableBinding.objects.create(
        patient=foreign_patient,
        device=wearable_device,
        bound_at=timezone.now(),
        bound_by=foreign_doctor,
    )

    foreign_response = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )

    assert foreign_response.status_code == 409, foreign_response.data
    assert foreign_response.data == {"detail": "设备已绑定患者赵*。"}


@pytest.mark.django_db
def test_binding_status_and_unbind_preserve_history_then_allow_rebind(
    api_client, doctor, project_patient, other_project_patient, wearable_device
):
    api_client.force_authenticate(doctor)
    created = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )
    binding_id = created.data["id"]

    status_before = api_client.get(
        f"/api/wearables/project-patients/{project_patient.id}/binding/"
    )
    unbound = api_client.post(
        f"/api/wearables/bindings/{binding_id}/unbind/",
        {"reason": "设备更换"},
        format="json",
    )

    assert status_before.status_code == 200, status_before.data
    assert status_before.data["binding"]["id"] == binding_id
    assert unbound.status_code == 200, unbound.data
    assert unbound.data["historical_data_preserved"] is True
    first_binding = WearableBinding.objects.get(id=binding_id)
    assert first_binding.unbound_at is not None
    assert first_binding.unbound_by == doctor
    assert first_binding.unbind_reason == "设备更换"

    rebound = api_client.post(
        f"/api/wearables/project-patients/{other_project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )
    assert rebound.status_code == 201, rebound.data
    assert timezone.datetime.fromisoformat(rebound.data["bound_at"]) >= first_binding.unbound_at


@pytest.mark.django_db
def test_repeated_unbind_is_rejected(api_client, doctor, project_patient, wearable_device):
    api_client.force_authenticate(doctor)
    created = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )
    url = f"/api/wearables/bindings/{created.data['id']}/unbind/"
    first = api_client.post(url, format="json")
    second = api_client.post(url, format="json")

    assert first.status_code == 200, first.data
    assert second.status_code == 409, second.data


@pytest.mark.django_db
def test_unbind_api_rejects_client_supplied_unbound_at_and_keeps_binding_active(
    api_client, doctor, project_patient, wearable_device
):
    api_client.force_authenticate(doctor)
    created = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )

    response = api_client.post(
        f"/api/wearables/bindings/{created.data['id']}/unbind/",
        {"unbound_at": timezone.now().isoformat()},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "unbound_at" in response.data
    binding = WearableBinding.objects.get(id=created.data["id"])
    assert binding.unbound_at is None


@pytest.mark.django_db
@pytest.mark.parametrize("offset", [timezone.timedelta(), -timezone.timedelta(seconds=1)])
def test_unbind_service_rejects_non_positive_binding_interval(
    doctor, patient, wearable_device, offset
):
    from apps.wearables.services.bindings import unbind_device

    bound_at = timezone.now()
    binding = WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=bound_at,
        bound_by=doctor,
    )

    with pytest.raises(ValueError, match="解绑时间必须晚于绑定时间"):
        unbind_device(
            binding=binding,
            actor=doctor,
            unbound_at=bound_at + offset,
        )

    binding.refresh_from_db()
    assert binding.unbound_at is None


@pytest.mark.django_db
def test_doctor_can_unbind_other_doctors_enrolled_patient_binding(
    api_client, doctor, project_patient, wearable_device
):
    api_client.force_authenticate(doctor)
    created = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )
    another_doctor = User.objects.create_user(
        phone="13800007777",
        password="pass123456",
        name="无权医生",
        role=User.Role.DOCTOR,
    )
    api_client.force_authenticate(another_doctor)

    response = api_client.post(f"/api/wearables/bindings/{created.data['id']}/unbind/")

    assert response.status_code == 200, response.data
    binding = WearableBinding.objects.get(id=created.data["id"])
    assert binding.unbound_at is not None


@pytest.mark.django_db
def test_doctor_can_bind_other_doctors_enrolled_patient(api_client, project_patient, wearable_device):
    another_doctor = User.objects.create_user(
        phone="13800009999",
        password="pass123456",
        name="另一位医生",
        role=User.Role.DOCTOR,
    )
    api_client.force_authenticate(another_doctor)

    response = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert WearableBinding.objects.filter(patient=project_patient.patient).exists()


@pytest.mark.django_db
def test_any_doctor_can_manage_wearable_for_enrolled_patient(
    api_client, doctor, wearable_device, monkeypatch
):
    owner = User.objects.create_user(
        phone="13800008888",
        password="pass123456",
        name="项目医生",
        role=User.Role.DOCTOR,
    )
    patient = Patient.objects.create(
        name="跨医生患者",
        gender=Patient.Gender.UNKNOWN,
        age=66,
        phone="13900008888",
        primary_doctor=owner,
    )
    project = StudyProject.objects.create(name="跨医生项目", created_by=owner)
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    project_patient = ProjectPatient.objects.create(
        project=project,
        patient=patient,
        group=group,
        created_by=owner,
    )
    monkeypatch.setattr(
        "apps.wearables.views.check_device_status",
        lambda device: {
            "device_id": device.id,
            "model": device.model,
            "online": True,
            "battery_level": 80,
            "last_communication_at": None,
            "capabilities": {"ring": False},
        },
    )
    api_client.force_authenticate(doctor)

    status_response = api_client.get(
        f"/api/wearables/project-patients/{project_patient.id}/binding/"
    )
    assert status_response.status_code == 200, status_response.data

    bind_response = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )
    assert bind_response.status_code == 201, bind_response.data

    check_response = api_client.post(
        f"/api/wearables/devices/{wearable_device.id}/check-status/",
        format="json",
    )
    assert check_response.status_code == 200, check_response.data

    unbind_response = api_client.post(
        f"/api/wearables/bindings/{bind_response.data['id']}/unbind/",
        format="json",
    )
    assert unbind_response.status_code == 200, unbind_response.data


@pytest.mark.django_db
def test_wearable_binding_status_rejects_missing_project_patient(api_client, doctor):
    api_client.force_authenticate(doctor)

    response = api_client.get("/api/wearables/project-patients/999999/binding/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_unauthenticated_user_cannot_manage_devices(api_client):
    response = api_client.get("/api/wearables/devices/")

    assert response.status_code == 403
