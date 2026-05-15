import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def auth_client(doctor):
    client = APIClient()
    client.force_authenticate(user=doctor)
    return client


@pytest.mark.django_db
def test_doctor_list_only_returns_doctor_accounts(auth_client):
    doctor = User.objects.create_user(
        phone="13700000001",
        password="pass123456",
        name="列表医生",
        role=User.Role.DOCTOR,
    )
    User.objects.create_user(
        phone="13700000002",
        password="pass123456",
        name="管理员",
        role=User.Role.ADMIN,
    )

    response = auth_client.get("/api/accounts/users/")

    assert response.status_code == 200, response.content
    rows = response.json()
    names = {row["name"] for row in rows}
    assert "列表医生" in names
    assert "管理员" not in names
    row = next(item for item in rows if item["id"] == doctor.id)
    assert row["gender"] == User.Gender.UNKNOWN
    assert row["role"] == User.Role.DOCTOR
    assert row["must_change_password"] is False
    assert row["date_joined"]


@pytest.mark.django_db
def test_create_doctor_uses_default_password_and_requires_change(auth_client):
    response = auth_client.post(
        "/api/accounts/users/",
        {
            "name": "新医生",
            "gender": User.Gender.FEMALE,
            "phone": "13700000003",
            "role": User.Role.SUPER_ADMIN,
            "must_change_password": False,
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    created = User.objects.get(phone="13700000003")
    assert created.name == "新医生"
    assert created.gender == User.Gender.FEMALE
    assert created.role == User.Role.DOCTOR
    assert created.must_change_password is True
    assert created.check_password("888888")
    assert response.json()["must_change_password"] is True


@pytest.mark.django_db
def test_create_doctor_rejects_invalid_phone(auth_client):
    response = auth_client.post(
        "/api/accounts/users/",
        {"name": "错误医生", "gender": User.Gender.MALE, "phone": "12345"},
        format="json",
    )

    assert response.status_code == 400
    assert "phone" in response.json()


@pytest.mark.django_db
def test_create_doctor_rejects_duplicate_phone(auth_client):
    User.objects.create_user(
        phone="13700000004",
        password="pass123456",
        name="已存在医生",
        role=User.Role.DOCTOR,
    )

    response = auth_client.post(
        "/api/accounts/users/",
        {"name": "重复医生", "gender": User.Gender.MALE, "phone": "13700000004"},
        format="json",
    )

    assert response.status_code == 400
    assert "phone" in response.json()


@pytest.mark.django_db
def test_update_doctor_basic_profile_does_not_change_password_or_role(auth_client):
    target = User.objects.create_user(
        phone="13700000005",
        password="pass123456",
        name="待编辑医生",
        role=User.Role.DOCTOR,
    )

    response = auth_client.patch(
        f"/api/accounts/users/{target.id}/",
        {
            "name": "已编辑医生",
            "gender": User.Gender.MALE,
            "phone": "13700000006",
            "role": User.Role.SUPER_ADMIN,
            "password": "hacked-password",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    target.refresh_from_db()
    assert target.name == "已编辑医生"
    assert target.gender == User.Gender.MALE
    assert target.phone == "13700000006"
    assert target.username == "13700000006"
    assert target.role == User.Role.DOCTOR
    assert target.check_password("pass123456")
