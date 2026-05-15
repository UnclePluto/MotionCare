import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.mark.django_db
def test_csrf_cookie_sets_token():
    client = APIClient(enforce_csrf_checks=True)
    resp = client.get("/api/auth/csrf/")
    assert resp.status_code == 200
    assert "csrftoken" in resp.cookies


@pytest.mark.django_db
def test_login_me_flow(doctor):
    client = APIClient(enforce_csrf_checks=True)
    csrf = client.get("/api/auth/csrf/")
    assert csrf.status_code == 200
    token = csrf.cookies["csrftoken"].value

    login_resp = client.post(
        "/api/auth/login/",
        {"phone": doctor.phone, "password": "pass123456"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert login_resp.status_code == 204

    me = client.get("/api/me/")
    assert me.status_code == 200
    body = me.json()
    assert body["phone"] == doctor.phone
    assert body["name"] == doctor.name
    assert body["gender"] == doctor.gender
    assert body["role"] == doctor.role
    assert doctor.role in body["roles"]
    assert body["must_change_password"] == doctor.must_change_password
    assert "patient.read" in body["permissions"]
    assert "user.manage" in body["permissions"]


@pytest.mark.django_db
def test_me_requires_authentication():
    client = APIClient()
    resp = client.get("/api/me/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_patients_list_after_session_login(doctor):
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/auth/csrf/")
    token = client.cookies["csrftoken"].value
    client.post(
        "/api/auth/login/",
        {"phone": doctor.phone, "password": "pass123456"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )

    resp = client.get("/api/patients/")
    assert resp.status_code == 200
    assert "results" in resp.json() or isinstance(resp.json(), list)


@pytest.mark.django_db
def test_change_password_keeps_session_authenticated():
    user = User.objects.create_user(
        phone="13700000015",
        password="888888",
        name="默认密码医生",
        role=User.Role.DOCTOR,
        must_change_password=True,
    )
    client = APIClient(enforce_csrf_checks=True)
    csrf = client.get("/api/auth/csrf/")
    assert csrf.status_code == 200
    token = csrf.cookies["csrftoken"].value

    login_resp = client.post(
        "/api/auth/login/",
        {"phone": user.phone, "password": "888888"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert login_resp.status_code == 204
    token = client.cookies["csrftoken"].value

    change_resp = client.post(
        "/api/accounts/users/me/change-password/",
        {
            "old_password": "888888",
            "new_password": "newpass123456",
            "confirm_password": "newpass123456",
        },
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert change_resp.status_code == 200, change_resp.content

    me = client.get("/api/me/")
    assert me.status_code == 200
    assert me.json()["must_change_password"] is False
