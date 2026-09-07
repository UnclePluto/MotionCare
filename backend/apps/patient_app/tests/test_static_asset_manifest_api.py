from urllib.parse import parse_qs, urlsplit

import pytest


@pytest.fixture(autouse=True)
def static_asset_settings(settings, monkeypatch):
    settings.QINIU_ACCESS_KEY = "test-access-key"
    settings.QINIU_SECRET_KEY = "test-secret-key"
    settings.MINIAPP_STATIC_ASSET_BASE_URL = (
        "https://cdn.example.com/motioncare/static-assets"
    )
    settings.MINIAPP_STATIC_ASSET_URL_TTL_SECONDS = 600
    monkeypatch.setattr(
        "apps.patient_app.throttles.MiniappStaticAssetRateThrottle.allow_request",
        lambda self, request, view: True,
    )


def test_anonymous_manifest_contains_exact_signed_objects(client, monkeypatch):
    monkeypatch.setattr("apps.common.miniapp_signed_assets.time.time", lambda: 1_800_000_000)

    response = client.get(
        "/api/patient-app/static-assets/", {"version": "v-3aafe09211fd"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["asset_version"] == "v-3aafe09211fd"
    assert data["issued_at"] == 1_800_000_000
    assert data["expires_at"] == 1_800_000_600
    assert len(data["assets"]) == 23
    assert response["Cache-Control"] == "no-store"
    for asset in data["assets"]:
        url = urlsplit(asset["url"])
        params = parse_qs(url.query)
        assert url.scheme == "https"
        assert url.netloc == "cdn.example.com"
        assert url.path == "/motioncare/static-assets/" + asset["relative_path"]
        assert params["e"] == ["1800000600"]
        assert len(params["token"]) == 1
        assert set(asset) == {
            "key",
            "relative_path",
            "url",
            "content_type",
            "size_bytes",
            "sha256",
        }


@pytest.mark.parametrize(
    "query",
    [
        "",
        "version=v-3aafe09211fd&version=v-3aafe09211fd",
        "version=v-3aafe09211fd&key=training/video.mp4",
        "version=../private",
        "url=https://example.com/private",
    ],
)
def test_rejects_noncanonical_queries(client, query):
    response = client.get("/api/patient-app/static-assets/?" + query)

    assert response.status_code == 400
    assert response["Cache-Control"] == "no-store"


def test_unknown_version_returns_404(client):
    response = client.get(
        "/api/patient-app/static-assets/", {"version": "v-000000000000"}
    )

    assert response.status_code == 404
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("method", ["post", "head", "options"])
def test_only_get_is_allowed(client, method):
    response = getattr(client, method)(
        "/api/patient-app/static-assets/?version=v-3aafe09211fd"
    )

    assert response.status_code == 405
    assert response["Cache-Control"] == "no-store"


def test_signing_failure_is_redacted_from_response_and_logs(client, monkeypatch, caplog):
    secret = "secret-key-and-signed-token"

    def fail(_version):
        raise RuntimeError(secret)

    monkeypatch.setattr(
        "apps.patient_app.static_asset_views.build_signed_static_asset_manifest",
        fail,
    )

    response = client.get(
        "/api/patient-app/static-assets/", {"version": "v-3aafe09211fd"}
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "训练素材暂时不可用，请稍后重试"}
    assert secret not in response.content.decode()
    assert secret not in caplog.text
    failure_records = [
        record
        for record in caplog.records
        if record.getMessage() == "miniapp_static_asset_manifest_build_failed"
    ]
    assert len(failure_records) == 1
    assert failure_records[0].asset_version == "v-3aafe09211fd"


@pytest.mark.django_db
def test_authenticated_and_anonymous_requests_receive_same_keys(client, doctor):
    anonymous = client.get(
        "/api/patient-app/static-assets/", {"version": "v-3aafe09211fd"}
    )
    client.force_login(doctor)
    authenticated = client.get(
        "/api/patient-app/static-assets/", {"version": "v-3aafe09211fd"}
    )

    assert authenticated.status_code == 200
    assert {asset["key"] for asset in authenticated.json()["assets"]} == {
        asset["key"] for asset in anonymous.json()["assets"]
    }


def test_me_endpoint_still_requires_authentication(client):
    assert client.get("/api/patient-app/me/").status_code == 403
