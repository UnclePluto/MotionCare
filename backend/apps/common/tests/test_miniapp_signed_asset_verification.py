import json
import time
from io import BytesIO, StringIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.common import miniapp_signed_asset_verification as verification
from apps.common.miniapp_signed_asset_verification import (
    SignedAssetVerificationError,
    VerificationResponse,
    fetch_verification_response,
    verify_signed_static_assets,
)
from apps.common.tests.test_miniapp_static_assets import static_asset_fixture
from apps.training.qiniu import private_download_url


API_BASE = "https://api.example.com/api"


@pytest.fixture
def verification_fixture(tmp_path, settings, monkeypatch):
    root = static_asset_fixture(tmp_path).rename(tmp_path / "v-000000000001")
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["assetVersion"] = root.name
    for entry in manifest["entries"]:
        entry["relativePath"] = root.name + "/" + Path(entry["relativePath"]).name
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(
        "apps.common.miniapp_static_asset_registry.REGISTERED_STATIC_ASSET_MANIFESTS",
        {root.name: manifest_path},
    )
    settings.QINIU_ACCESS_KEY = "test-ak"
    settings.QINIU_SECRET_KEY = "test-sk"
    settings.MINIAPP_STATIC_ASSET_BASE_URL = "https://cdn.example.com/motioncare/static-assets"
    issued_at = int(time.time())
    payload = {
        "asset_version": root.name, "issued_at": issued_at,
        "expires_at": issued_at + 600, "assets": [],
    }
    bodies = {}
    for entry in manifest["entries"]:
        url = private_download_url(
            settings.MINIAPP_STATIC_ASSET_BASE_URL + "/" + entry["relativePath"],
            expires_at=issued_at + 600,
        )
        payload["assets"].append({
            "key": entry["key"], "relative_path": entry["relativePath"], "url": url,
            "content_type": entry["contentType"], "size_bytes": entry["sizeBytes"],
            "sha256": entry["sha256"],
        })
        bodies[url] = VerificationResponse(
            200, entry["contentType"], (root / Path(entry["relativePath"]).name).read_bytes(),
        )
    api_url = API_BASE + "/patient-app/static-assets/?" + urlencode({"version": root.name})
    bodies[api_url] = VerificationResponse(200, "application/json", json.dumps(payload).encode())

    def responses(url):
        return bodies.get(url, VerificationResponse(401, "application/json", b"{}"))

    return root, responses


def test_verifies_all_content_then_probes_same_warmed_object(verification_fixture):
    root, responses = verification_fixture
    calls = []

    def fetch(url):
        calls.append(url)
        return responses(url)

    results = verify_signed_static_assets(root, API_BASE, fetch=fetch)
    assert len(results) == 23
    assert all(result.size_bytes > 0 and len(result.sha256) == 64 for result in results)
    assert len(calls) == 27
    unsigned = calls[1].split("?")[0]
    assert calls[24] == unsigned
    assert calls[25].split("?")[0] == unsigned
    assert parse_qs(urlsplit(calls[25]).query)["token"] != parse_qs(urlsplit(calls[1]).query)["token"]
    expired_at = int(parse_qs(urlsplit(calls[26]).query)["e"][0])
    assert expired_at <= int(time.time()) - 60
    assert calls[26] == private_download_url(unsigned, expires_at=expired_at)


@pytest.mark.parametrize("failure", ["body", "size", "type", "redirect"])
def test_rejects_invalid_download(verification_fixture, failure):
    root, responses = verification_fixture

    def fetch(url):
        result = responses(url)
        if "cdn.example.com" in url and result.status == 200:
            return {
                "body": VerificationResponse(200, result.content_type, b"x" * len(result.body)),
                "size": VerificationResponse(200, result.content_type, result.body + b"x"),
                "type": VerificationResponse(200, "text/html", result.body),
                "redirect": VerificationResponse(302, result.content_type, result.body),
            }[failure]
        return result

    with pytest.raises(SignedAssetVerificationError, match="pattern_sun"):
        verify_signed_static_assets(root, API_BASE, fetch=fetch)


@pytest.mark.parametrize("failure", [
    "source", "userinfo", "path", "traversal", "fragment", "backslash", "whitespace",
    "missing", "duplicate", "unknown", "bad_key", "version", "relative_path", "content_type",
    "size_bytes", "sha256", "token", "invalid_signature", "expiry", "duplicate_query",
    "extra_query", "issued_at", "ttl_short", "ttl_long", "asset_shape", "payload_shape",
    "json", "huge", "status", "media_type",
])
def test_rejects_entire_manifest_before_any_download(verification_fixture, failure):
    root, responses = verification_fixture
    calls = []

    def fetch(url):
        calls.append(url)
        result = responses(url)
        payload = json.loads(result.body)
        asset = payload["assets"][-1]
        if failure == "source":
            asset["url"] = asset["url"].replace("cdn.example.com", "evil.example.com")
        elif failure == "userinfo":
            asset["url"] = asset["url"].replace("https://", "https://user@")
        elif failure == "path":
            asset["url"] = asset["url"].replace("/static-assets/", "/other/")
        elif failure == "traversal":
            asset["url"] = asset["url"].replace("/static-assets/", "/other/../static-assets/")
        elif failure == "fragment":
            asset["url"] += "#secret"
        elif failure == "backslash":
            asset["url"] = asset["url"].replace("/static-assets/", "/static-assets\\/")
        elif failure == "whitespace":
            asset["url"] += "\n"
        elif failure == "missing":
            payload["assets"].pop()
        elif failure == "duplicate":
            payload["assets"][-1] = payload["assets"][0]
        elif failure == "unknown":
            asset["key"] = "unknown"
        elif failure == "bad_key":
            asset["key"] = []
        elif failure == "version":
            payload["asset_version"] = "v-invalid"
        elif failure in {"relative_path", "content_type", "size_bytes", "sha256"}:
            asset[failure] = "invalid"
        elif failure in {"token", "invalid_signature"}:
            asset["url"] = asset["url"].split("&token=")[0] + "&token=" + (
                "bad" if failure == "token" else "test-ak:AAAAAAAAAAAAAAAAAAAAAAAAAAA="
            )
        elif failure == "expiry":
            asset["url"] = asset["url"].replace(str(payload["expires_at"]), "1")
        elif failure == "duplicate_query":
            asset["url"] += "&e=" + str(payload["expires_at"])
        elif failure == "extra_query":
            asset["url"] += "&other=1"
        elif failure == "issued_at":
            payload["issued_at"] = True
        elif failure == "ttl_short":
            payload["issued_at"] = payload["expires_at"] - 119
        elif failure == "ttl_long":
            payload["issued_at"] = payload["expires_at"] - 3601
        elif failure == "asset_shape":
            payload["assets"][-1] = []
        elif failure == "payload_shape":
            payload = []
        body = json.dumps(payload).encode()
        if failure == "json":
            body = b"\xff"
        elif failure == "huge":
            body += b" " * (256 * 1024)
        return VerificationResponse(
            302 if failure == "status" else 200,
            "text/html" if failure == "media_type" else "application/json", body,
        )

    with pytest.raises(SignedAssetVerificationError):
        verify_signed_static_assets(root, API_BASE, fetch=fetch)
    assert len(calls) == 1


@pytest.mark.parametrize("probe", ["anonymous", "tampered", "expired"])
@pytest.mark.parametrize("status", [200, 302, 404, 500])
def test_requires_auth_denial_for_each_existing_object_probe(verification_fixture, probe, status):
    root, responses = verification_fixture

    def fetch(url):
        result = responses(url)
        query = parse_qs(urlsplit(url).query)
        if "cdn.example.com" in url and result.status != 200:
            actual = (
                "anonymous" if not query else
                "expired" if int(query.get("e", [0])[0]) < time.time() else "tampered"
            )
            if actual == probe:
                return VerificationResponse(status, "text/plain", b"denied")
        return result

    with pytest.raises(SignedAssetVerificationError, match="pattern_sun"):
        verify_signed_static_assets(root, API_BASE, fetch=fetch)


@pytest.mark.parametrize("base", [
    "http://api.example.com/api", "/api", "https://user@api.example.com/api",
    "https://api.example.com/api?q=1", "https://api.example.com/api#fragment",
    "https://api.example.com/other", "https://api.example.com/api\n",
])
def test_invalid_api_base_never_fetches(verification_fixture, base):
    root, _ = verification_fixture
    fetch = Mock()
    with pytest.raises(SignedAssetVerificationError):
        verify_signed_static_assets(root, base, fetch=fetch)
    fetch.assert_not_called()


@pytest.mark.parametrize("failure", ["local_body", "unregistered", "registry_metadata"])
def test_local_and_registry_must_agree_before_network(verification_fixture, monkeypatch, failure):
    root, _ = verification_fixture
    manifest = json.loads((root / "manifest.json").read_text())
    if failure == "local_body":
        (root / Path(manifest["entries"][0]["relativePath"]).name).write_bytes(b"broken")
    elif failure == "unregistered":
        monkeypatch.setattr(
            "apps.common.miniapp_static_asset_registry.REGISTERED_STATIC_ASSET_MANIFESTS", {},
        )
    else:
        manifest["entries"][0]["sizeBytes"] += 1
        monkeypatch.setattr(verification, "load_registered_static_assets", lambda _: manifest)
    fetch = Mock()
    with pytest.raises(SignedAssetVerificationError):
        verify_signed_static_assets(root, API_BASE, fetch=fetch)
    fetch.assert_not_called()


def test_command_outputs_only_verified_keys_and_checks(verification_fixture, monkeypatch, caplog):
    root, responses = verification_fixture
    monkeypatch.setattr(
        "apps.common.management.commands.verify_miniapp_signed_assets.verify_signed_static_assets",
        lambda root, base: verify_signed_static_assets(root, base, fetch=responses),
    )
    out = StringIO()
    call_command("verify_miniapp_signed_assets", source_root=root, api_base_url=API_BASE, stdout=out)
    output = out.getvalue() + caplog.text
    assert "pattern_sun" in output and "SHA-256" in output
    assert "匿名" in output and "篡改" in output and "过期" in output
    assert "https://" not in output and "test-ak" not in output and "test-sk" not in output


def test_command_failure_does_not_leak_network_exception(
    verification_fixture, monkeypatch, capsys, caplog,
):
    root, _ = verification_fixture
    secret = "https://cdn.example.com/file?e=123&token=test-ak:secret"

    def fetch(url):
        raise URLError(secret)

    monkeypatch.setattr(
        "apps.common.management.commands.verify_miniapp_signed_assets.verify_signed_static_assets",
        lambda root, base: verify_signed_static_assets(root, base, fetch=fetch),
    )
    with pytest.raises(CommandError) as error:
        call_command("verify_miniapp_signed_assets", source_root=root, api_base_url=API_BASE)
    captured = capsys.readouterr()
    output = str(error.value) + captured.out + captured.err + caplog.text
    assert "https://" not in output and "token=" not in output and "secret" not in output
    assert error.value.__suppress_context__


@pytest.mark.parametrize("status", [200, 302, 401, 403])
def test_fetch_bounds_read_and_returns_http_status_without_redirect(monkeypatch, status):
    stream = BytesIO(b"response")
    response = Mock(wraps=stream)
    response.status = status
    response.headers = {"Content-Type": "text/plain"}
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    if status != 200:
        opener.open.side_effect = HTTPError("https://example.com/secret", status, "error", {}, stream)
    handlers = []

    def build(*items):
        handlers.extend(items)
        return opener

    monkeypatch.setattr(verification, "build_opener", build)
    result = fetch_verification_response("https://example.com/secret")
    assert result.status == status and result.body == b"response"
    assert opener.open.call_args.kwargs["timeout"] == 20
    assert any(handler.redirect_request(None, None, 302, "", {}, "https://evil.example.com") is None
               for handler in handlers)
    if status == 200:
        response.read.assert_called_once_with(32 * 1024 * 1024 + 1)


def test_fetch_rejects_oversized_body_and_redacts_transport_errors(monkeypatch):
    opener = Mock()
    response = opener.open.return_value
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = b"x" * (32 * 1024 * 1024 + 1)
    monkeypatch.setattr(verification, "build_opener", lambda *args: opener)
    with pytest.raises(SignedAssetVerificationError):
        fetch_verification_response("https://example.com/?token=secret")
    opener.open.side_effect = URLError("https://example.com/?token=secret")
    with pytest.raises(SignedAssetVerificationError) as error:
        fetch_verification_response("https://example.com/?token=secret")
    assert "secret" not in str(error.value) and error.value.__suppress_context__
