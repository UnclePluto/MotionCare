import re

import pytest
from django.contrib.auth.models import User


@pytest.mark.django_db
def test_csrf_login_me_flow(client):
    User.objects.create_user(username="doc", password="pass1234")

    csrf = client.get("/api/auth/csrf")
    assert csrf.status_code == 200
    assert "csrftoken" in csrf.cookies
    token = csrf.cookies["csrftoken"].value
    assert re.fullmatch(r"[A-Za-z0-9]+", token) is not None

    resp = client.post(
        "/api/auth/login",
        data={"username": "doc", "password": "pass1234"},
        HTTP_X_CSRFTOKEN=token,
    )
    assert resp.status_code == 204
    assert "sessionid" in resp.cookies

    me = client.get("/api/me")
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == "doc"
    assert body["roles"] == ["doctor"]
    assert "permissions" in body

