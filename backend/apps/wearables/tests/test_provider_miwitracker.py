import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest
from django.core.cache import cache

from apps.wearables.providers.miwitracker import (
    MiwitrackerClient,
    ProviderError,
    build_token_password,
)


@pytest.fixture(autouse=True)
def clear_provider_cache():
    cache.clear()


@pytest.fixture
def client_factory(settings):
    settings.MIWITRACKER_BASE_URL = "https://miwi.example"
    settings.MIWITRACKER_APP_ID = "188"
    settings.MIWITRACKER_KEY = "abc"

    def factory(handler):
        return MiwitrackerClient(transport=httpx.MockTransport(handler))

    return factory


def response(request, payload, status_code=200):
    return httpx.Response(status_code, json=payload, request=request)


def test_token_password_is_md5_key_appid_timestamp(settings):
    settings.MIWITRACKER_APP_ID = "188"
    settings.MIWITRACKER_KEY = "abc"

    assert build_token_password("abc", "188", 1619582437) == "d70429870da4c12b70e195638ebe1a07"


def test_token_request_uses_documented_path_and_password(client_factory, monkeypatch):
    captured = {}
    monkeypatch.setattr("apps.wearables.providers.miwitracker.time.time", lambda: 1619582437)

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return response(request, {"Code": 0, "Result": {"AccessToken": "token-1"}})

    client_factory(handler).get_access_token()

    assert captured == {
        "path": "/api/token/get_token",
        "body": {
            "AppId": "188",
            "Timestamp": 1619582437,
            "Password": "d70429870da4c12b70e195638ebe1a07",
        },
    }


def test_business_request_sends_access_token_in_header_and_body(client_factory):
    captured = {}

    def handler(request):
        if request.url.path == MiwitrackerClient.TOKEN_PATH:
            return response(request, {"Code": 0, "Result": {"AccessToken": "token-1"}})
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return response(request, {"Code": 0, "Result": []})

    client_factory(handler).get_heart_rates(
        "8675309",
        datetime(2026, 7, 22, tzinfo=timezone.utc),
        datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    assert captured["authorization"] == "token-1"
    assert captured["body"] == {
        "AccessToken": "token-1",
        "Imei": "8675309",
        "BeginTime": "2026-07-22 00:00:00",
        "EndTime": "2026-07-23 00:00:00",
    }


def test_heart_rate_parser_treats_begin_and_end_as_utc_zero(client_factory):
    points = client_factory(lambda request: None).parse_heart_rates(
        [{"HeartRate": 72, "HrTime": "2026-07-22 01:15:00"}]
    )

    assert points[0].metric_type == "heart_rate"
    assert points[0].measured_at.isoformat() == "2026-07-22T01:15:00+00:00"
    assert points[0].values == {"heart_rate": 72}


def test_blood_pressure_parser_uses_systolic_diastolic_and_utc_zero(client_factory):
    points = client_factory(lambda request: None).parse_blood_pressures(
        [{"Systolic": 121, "Diastolic": 79, "BpTime": "2026-07-22 01:16:00"}]
    )

    assert points[0].metric_type == "blood_pressure"
    assert points[0].measured_at == datetime(2026, 7, 22, 1, 16, tzinfo=timezone.utc)
    assert points[0].values == {"systolic": 121, "diastolic": 79}


def test_blood_oxygen_parser_uses_documented_fields_and_utc_zero(client_factory):
    points = client_factory(lambda request: None).parse_blood_oxygen(
        [{"BloodOxygen": 97, "BloodOxygenTime": "2026-07-22 01:17:00"}]
    )

    assert points[0].metric_type == "blood_oxygen"
    assert points[0].measured_at == datetime(2026, 7, 22, 1, 17, tzinfo=timezone.utc)
    assert points[0].values == {"blood_oxygen": 97}


def test_daily_steps_parser_uses_documented_item_fields(client_factory):
    points = client_factory(lambda request: None).parse_daily_steps(
        [{"Date": "2026-07-22", "Steps": 1234, "Distance": "851.25", "Calorie": "90.5"}]
    )

    assert points[0].record_date == date(2026, 7, 22)
    assert points[0].steps == 1234
    assert points[0].distance == Decimal("851.25")
    assert points[0].calorie == Decimal("90.5")


@pytest.mark.parametrize(
    ("parser_name", "items"),
    [
        ("parse_heart_rates", []),
        ("parse_blood_pressures", []),
        ("parse_blood_oxygen", []),
        ("parse_daily_steps", []),
    ],
)
def test_data_parsers_return_empty_list_for_empty_vendor_arrays(client_factory, parser_name, items):
    parser = getattr(client_factory(lambda request: None), parser_name)

    assert parser(items) == []


def test_nonzero_vendor_code_raises_provider_error_with_code(client_factory):
    def handler(request):
        if request.url.path == MiwitrackerClient.TOKEN_PATH:
            return response(request, {"Code": 0, "Result": {"AccessToken": "token-1"}})
        return response(request, {"Code": 1042, "Message": "device not found"})

    with pytest.raises(ProviderError, match="1042") as exc_info:
        client_factory(handler).get_heart_rates(
            "8675309", datetime(2026, 7, 22), datetime(2026, 7, 23)
        )

    assert exc_info.value.code == 1042


def test_command_nonzero_vendor_code_raises_provider_error_with_code(client_factory):
    def handler(request):
        if request.url.path == MiwitrackerClient.TOKEN_PATH:
            return response(request, {"Code": 0, "Result": {"AccessToken": "token-1"}})
        return response(request, {"Code": 1802, "Message": "command failed"})

    with pytest.raises(ProviderError, match="1802") as exc_info:
        client_factory(handler).send_command("8675309", "9018")

    assert exc_info.value.code == 1802


def test_access_token_is_cached_for_fifty_minutes(client_factory):
    calls = {"token": 0, "business": 0}

    def handler(request):
        if request.url.path == MiwitrackerClient.TOKEN_PATH:
            calls["token"] += 1
            return response(request, {"Code": 0, "Result": {"AccessToken": "token-1"}})
        calls["business"] += 1
        return response(request, {"Code": 0, "Result": []})

    client = client_factory(handler)
    for _ in range(2):
        client.get_heart_rates("8675309", datetime(2026, 7, 22), datetime(2026, 7, 23))

    assert calls == {"token": 1, "business": 2}


def test_unauthorized_response_refreshes_token_and_retries_once(client_factory):
    calls = {"token": 0, "business": 0}

    def handler(request):
        if request.url.path == MiwitrackerClient.TOKEN_PATH:
            calls["token"] += 1
            return response(
                request,
                {"Code": 0, "Result": {"AccessToken": f"token-{calls['token']}"}},
            )
        calls["business"] += 1
        if calls["business"] == 1:
            return response(request, {"Code": 401, "Message": "unauthorized"})
        assert request.headers["Authorization"] == "token-2"
        return response(request, {"Code": 0, "Result": []})

    client_factory(handler).get_heart_rates(
        "8675309", datetime(2026, 7, 22), datetime(2026, 7, 23)
    )

    assert calls == {"token": 2, "business": 2}


def test_http_401_response_refreshes_token_and_retries_once(client_factory):
    calls = {"token": 0, "business": 0}

    def handler(request):
        if request.url.path == MiwitrackerClient.TOKEN_PATH:
            calls["token"] += 1
            return response(
                request,
                {"Code": 0, "Result": {"AccessToken": f"token-{calls['token']}"}},
            )
        calls["business"] += 1
        if calls["business"] == 1:
            return response(request, {"Code": 401, "Message": "unauthorized"}, status_code=401)
        assert request.headers["Authorization"] == "token-2"
        return response(request, {"Code": 0, "Result": []})

    client_factory(handler).get_heart_rates(
        "8675309", datetime(2026, 7, 22), datetime(2026, 7, 23)
    )

    assert calls == {"token": 2, "business": 2}


def test_second_http_401_response_is_not_retried_again(client_factory):
    calls = {"token": 0, "business": 0}

    def handler(request):
        if request.url.path == MiwitrackerClient.TOKEN_PATH:
            calls["token"] += 1
            return response(
                request,
                {"Code": 0, "Result": {"AccessToken": f"token-{calls['token']}"}},
            )
        calls["business"] += 1
        return response(request, {"Code": 401, "Message": "unauthorized"}, status_code=401)

    with pytest.raises(ProviderError, match="401") as exc_info:
        client_factory(handler).get_heart_rates(
            "8675309", datetime(2026, 7, 22), datetime(2026, 7, 23)
        )

    assert exc_info.value.code == 401
    assert calls == {"token": 2, "business": 2}


@pytest.mark.parametrize("message", ["unauthorized", "无权限", "没有权限", "权限不足"])
def test_permission_denied_response_refreshes_token_and_retries_once(client_factory, message):
    calls = {"token": 0, "business": 0}

    def handler(request):
        if request.url.path == MiwitrackerClient.TOKEN_PATH:
            calls["token"] += 1
            return response(
                request,
                {"Code": 0, "Result": {"AccessToken": f"token-{calls['token']}"}},
            )
        calls["business"] += 1
        if calls["business"] == 1:
            return response(request, {"Code": 1001, "Message": message})
        assert request.headers["Authorization"] == "token-2"
        return response(request, {"Code": 0, "Result": []})

    client_factory(handler).get_heart_rates(
        "8675309", datetime(2026, 7, 22), datetime(2026, 7, 23)
    )

    assert calls == {"token": 2, "business": 2}


def test_non_permission_vendor_error_does_not_refresh_token(client_factory):
    calls = {"token": 0, "business": 0}

    def handler(request):
        if request.url.path == MiwitrackerClient.TOKEN_PATH:
            calls["token"] += 1
            return response(request, {"Code": 0, "Result": {"AccessToken": "token-1"}})
        calls["business"] += 1
        return response(request, {"Code": 1042, "Message": "device not found"})

    with pytest.raises(ProviderError, match="1042"):
        client_factory(handler).get_heart_rates(
            "8675309", datetime(2026, 7, 22), datetime(2026, 7, 23)
        )

    assert calls == {"token": 1, "business": 1}


def test_token_cache_key_is_scoped_to_normalized_base_url_and_app_id():
    same_environment = MiwitrackerClient(
        base_url="https://MIWI.EXAMPLE/",
        app_id="188",
        key="key-a",
        transport=httpx.MockTransport(lambda request: None),
    )
    normalized_environment = MiwitrackerClient(
        base_url="https://miwi.example",
        app_id="188",
        key="key-b",
        transport=httpx.MockTransport(lambda request: None),
    )
    other_environment = MiwitrackerClient(
        base_url="https://other-miwitracker.example",
        app_id="188",
        key="key-c",
        transport=httpx.MockTransport(lambda request: None),
    )

    assert same_environment._token_cache_key == normalized_environment._token_cache_key
    assert same_environment._token_cache_key != other_environment._token_cache_key
    assert "MIWI.EXAMPLE" not in same_environment._token_cache_key
    assert "188" not in same_environment._token_cache_key


def test_second_unauthorized_response_is_not_retried_again(client_factory):
    calls = {"token": 0, "business": 0}

    def handler(request):
        if request.url.path == MiwitrackerClient.TOKEN_PATH:
            calls["token"] += 1
            return response(
                request,
                {"Code": 0, "Result": {"AccessToken": f"token-{calls['token']}"}},
            )
        calls["business"] += 1
        return response(request, {"Code": 401, "Message": "unauthorized"})

    with pytest.raises(ProviderError, match="401"):
        client_factory(handler).get_heart_rates(
            "8675309", datetime(2026, 7, 22), datetime(2026, 7, 23)
        )

    assert calls == {"token": 2, "business": 2}


def test_client_uses_five_second_connect_and_twenty_second_read_timeout(client_factory):
    client = client_factory(lambda request: None)

    assert client.timeout.connect == 5
    assert client.timeout.read == 20


def test_provider_errors_do_not_log_key_password_or_access_token(client_factory, caplog):
    secret_key = "very-secret-key"
    token = "very-secret-token"

    def handler(request):
        if request.url.path == MiwitrackerClient.TOKEN_PATH:
            return response(request, {"Code": 0, "Result": {"AccessToken": token}})
        return response(request, {"Code": 1042, "Message": "device not found"})

    with caplog.at_level(logging.INFO):
        with pytest.raises(ProviderError):
            client = MiwitrackerClient(
                base_url="https://miwi.example",
                app_id="188",
                key=secret_key,
                transport=httpx.MockTransport(handler),
            )
            client.get_heart_rates("8675309", datetime(2026, 7, 22), datetime(2026, 7, 23))

    assert secret_key not in caplog.text
    assert token not in caplog.text
    assert build_token_password(secret_key, "188", 0) not in caplog.text
