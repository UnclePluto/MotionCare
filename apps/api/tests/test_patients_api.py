import pytest
from django.contrib.auth.models import User


@pytest.mark.django_db
def test_patients_requires_auth(client):
    resp = client.get("/api/patients")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_patients_list_after_login(client):
    User.objects.create_user(username="doc", password="pass1234")
    client.get("/api/auth/csrf")
    token = client.cookies["csrftoken"].value
    client.post(
        "/api/auth/login",
        data={"username": "doc", "password": "pass1234"},
        HTTP_X_CSRFTOKEN=token,
    )

    resp = client.get("/api/patients")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}

