import re

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.wearables.models import WearableBinding, WearableDevice


def _device_payload(**overrides):
    payload = {
        "provider": "miwitracker",
        "external_device_id": "dev-created-001",
        "identifier_type": "device_id",
        "model": "TEST-MODEL",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_device_crud_assigns_four_digit_short_code(api_client, doctor):
    api_client.force_authenticate(doctor)

    created = api_client.post("/api/wearables/devices/", _device_payload(), format="json")

    assert created.status_code == 201, created.data
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
def test_doctor_cannot_access_other_doctors_project_patient(api_client, project_patient, wearable_device):
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

    assert response.status_code == 404
    assert not WearableBinding.objects.exists()


@pytest.mark.django_db
def test_unauthenticated_user_cannot_manage_devices(api_client):
    response = api_client.get("/api/wearables/devices/")

    assert response.status_code == 403
