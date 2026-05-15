import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def forced_user(db):
    return User.objects.create_user(
        phone="13700001000",
        password="888888",
        name="默认密码医生",
        role=User.Role.DOCTOR,
        must_change_password=True,
    )


@pytest.fixture
def forced_client(forced_user):
    client = APIClient()
    client.force_authenticate(user=forced_user)
    return client


@pytest.mark.django_db
def test_forced_password_change_blocks_business_api(forced_client):
    response = forced_client.get("/api/patients/")

    assert response.status_code == 403
    assert response.json()["detail"] == "请先修改默认密码"


@pytest.mark.django_db
def test_forced_password_change_allows_me_endpoint(forced_client):
    response = forced_client.get("/api/me/")

    assert response.status_code == 200
    assert response.json()["must_change_password"] is True


@pytest.mark.django_db
def test_forced_password_change_rejects_default_password(forced_client):
    response = forced_client.post(
        "/api/accounts/users/me/change-password/",
        {
            "old_password": "888888",
            "new_password": "888888",
            "confirm_password": "888888",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "new_password" in response.json()


@pytest.mark.django_db
def test_forced_password_change_accepts_new_password(forced_client, forced_user):
    response = forced_client.post(
        "/api/accounts/users/me/change-password/",
        {
            "old_password": "888888",
            "new_password": "newpass123456",
            "confirm_password": "newpass123456",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    forced_user.refresh_from_db()
    assert forced_user.must_change_password is False
    assert forced_user.check_password("newpass123456")


@pytest.mark.django_db
def test_change_password_rejects_wrong_old_password(forced_client):
    response = forced_client.post(
        "/api/accounts/users/me/change-password/",
        {
            "old_password": "wrong-password",
            "new_password": "newpass123456",
            "confirm_password": "newpass123456",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "old_password" in response.json()


@pytest.mark.django_db
def test_explicit_patient_app_permission_blocks_force_authenticated_default_password_user(forced_user):
    client = APIClient()
    client.force_authenticate(user=forced_user)

    response = client.get("/api/patient-app/me/")

    assert response.status_code == 403
    assert response.json()["detail"] == "请先修改默认密码"
