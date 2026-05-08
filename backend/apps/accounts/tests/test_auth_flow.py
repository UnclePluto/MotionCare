import pytest
from rest_framework.test import APIClient


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
    assert body["role"] == doctor.role
    assert doctor.role in body["roles"]
    assert "patient.read" in body["permissions"]


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
