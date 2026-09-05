import logging
import stat

import httpx
import pytest
import qiniu
from motion_analysis_contract import DownloadGrant, UploadGrant

import pp_mcare.storage as storage
from pp_mcare.storage import StoragePermanentError, StorageTransientError


MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"video" * 50


def download_grant(
    url="https://cdn.example/input.mp4?token=download-secret",
    object_hash="FqiniuOriginalHash1234567890abc",
):
    return DownloadGrant(
        url=url,
        bucket="private",
        object_key="videos/original.mp4",
        object_hash=object_hash,
        expires_at="2026-09-05T11:00:00Z",
        size_bytes=len(MP4),
        content_type="video/mp4",
    )


def upload_grant():
    return UploadGrant(
        bucket="private",
        object_key="motion-analysis/41/skeleton.mp4",
        token="upload-secret-token",
        expires_at="2026-09-05T13:00:00Z",
    )


def test_download_streams_private_mp4_and_validates_qiniu_etag(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=MP4, headers={"Content-Type": "video/mp4"})

    monkeypatch.setattr(storage, "_DOWNLOAD_TRANSPORT", httpx.MockTransport(handler))
    target = tmp_path / "original.mp4"
    expected = qiniu.etag(str(_write_fixture(tmp_path / "expected.mp4", MP4)))

    result = storage.download_original(
        download_grant(object_hash=expected), target, len(MP4), expected
    )

    assert result.size_bytes == len(MP4)
    assert result.object_hash == expected
    assert target.read_bytes() == MP4
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert len(calls) == 1
    assert "download-secret" not in repr(result)


def _write_fixture(path, data):
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("case", ["too_large", "too_small", "hash", "content_type", "body"])
def test_download_data_failures_are_not_retried_and_leave_no_partial(tmp_path, monkeypatch, case):
    attempts = 0
    body = MP4
    expected_size = len(MP4)
    expected_hash = qiniu.etag(str(_write_fixture(tmp_path / "expected.mp4", MP4)))
    headers = {"Content-Type": "video/mp4"}
    if case == "too_large":
        body += b"x"
    elif case == "too_small":
        body = body[:-1]
    elif case == "hash":
        expected_hash = "wrong-hash"
    elif case == "content_type":
        headers = {"Content-Type": "text/plain"}
    else:
        body = b"not-an-mp4".ljust(expected_size, b"x")

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, content=body, headers=headers)

    monkeypatch.setattr(storage, "_DOWNLOAD_TRANSPORT", httpx.MockTransport(handler))
    target = tmp_path / "original.mp4"
    with pytest.raises(StoragePermanentError):
        storage.download_original(
            download_grant(object_hash=expected_hash), target, expected_size, expected_hash
        )

    assert attempts == 1
    assert not target.exists()


@pytest.mark.parametrize("status", [400, 401, 404, 416])
def test_download_4xx_and_redirect_are_not_retried(tmp_path, monkeypatch, status):
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(status, headers={"Location": "https://evil.example/steal"})

    monkeypatch.setattr(storage, "_DOWNLOAD_TRANSPORT", httpx.MockTransport(handler))
    with pytest.raises(StoragePermanentError):
        storage.download_original(
            download_grant(object_hash="hash"), tmp_path / "x.mp4", len(MP4), "hash"
        )
    assert attempts == 1


def test_download_retries_5xx_three_times_with_clean_files(tmp_path, monkeypatch):
    attempts = 0
    sleeps = []

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    monkeypatch.setattr(storage, "_DOWNLOAD_TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(storage, "_SLEEP", sleeps.append)
    target = tmp_path / "x.mp4"
    with pytest.raises(StorageTransientError):
        storage.download_original(download_grant(object_hash="hash"), target, len(MP4), "hash")
    assert attempts == 3
    assert sleeps == [1.0, 2.0]
    assert not target.exists()


def test_download_retries_interrupted_response_from_a_clean_file(tmp_path, monkeypatch):
    attempts = 0
    expected_path = _write_fixture(tmp_path / "expected.mp4", MP4)
    expected_hash = qiniu.etag(str(expected_path))

    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield MP4[:20]
            raise httpx.ReadError("token=secret /private/patient.mp4")

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(200, headers={"Content-Type": "video/mp4"}, stream=Interrupted())
        return httpx.Response(200, content=MP4, headers={"Content-Type": "video/mp4"})

    monkeypatch.setattr(storage, "_DOWNLOAD_TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(storage, "_SLEEP", lambda _: None)
    target = tmp_path / "original.mp4"
    result = storage.download_original(
        download_grant(object_hash=expected_hash), target, len(MP4), expected_hash
    )

    assert attempts == 3
    assert target.read_bytes() == MP4
    assert result.size_bytes == len(MP4)


def test_upload_validates_key_hash_and_size(tmp_path, monkeypatch):
    path = _write_fixture(tmp_path / "skeleton.mp4", MP4)
    local_hash = qiniu.etag(str(path))
    calls = []

    def put_file(token, key, file_path, **kwargs):
        calls.append((token, key, file_path, kwargs))
        return {"key": key, "hash": local_hash}, {"status_code": 200}

    monkeypatch.setattr(storage.qiniu, "put_file", put_file)
    result = storage.upload_skeleton(upload_grant(), path)

    assert result.object_hash == local_hash
    assert result.size_bytes == len(MP4)
    assert calls[0][0:2] == ("upload-secret-token", upload_grant().object_key)
    assert "upload-secret-token" not in repr(result)


def test_upload_retries_transient_but_not_4xx(tmp_path, monkeypatch):
    path = _write_fixture(tmp_path / "skeleton.mp4", MP4)
    attempts = 0

    def put_file(_token, _key, _path, **_kwargs):
        nonlocal attempts
        attempts += 1
        return None, {"status_code": 503, "exception": "token=secret /private/video"}

    monkeypatch.setattr(storage.qiniu, "put_file", put_file)
    monkeypatch.setattr(storage, "_SLEEP", lambda _: None)
    with pytest.raises(StorageTransientError):
        storage.upload_skeleton(upload_grant(), path)
    assert attempts == 3

    attempts = 0

    def bad_request(_token, _key, _path, **_kwargs):
        nonlocal attempts
        attempts += 1
        return None, {"status_code": 401}

    monkeypatch.setattr(storage.qiniu, "put_file", bad_request)
    with pytest.raises(StoragePermanentError):
        storage.upload_skeleton(upload_grant(), path)
    assert attempts == 1


@pytest.mark.parametrize("wrong_field", ["key", "hash"])
def test_upload_rejects_provider_identity_mismatch_without_retry(
    tmp_path, monkeypatch, wrong_field
):
    path = _write_fixture(tmp_path / "skeleton.mp4", MP4)
    local_hash = qiniu.etag(str(path))
    calls = 0

    def put_file(_token, key, _path, **_kwargs):
        nonlocal calls
        calls += 1
        result = {"key": key, "hash": local_hash}
        result[wrong_field] = "provider-mismatch"
        return result, {"status_code": 200}

    monkeypatch.setattr(storage.qiniu, "put_file", put_file)
    with pytest.raises(StoragePermanentError):
        storage.upload_skeleton(upload_grant(), path)
    assert calls == 1


def test_upload_only_accepts_614_after_an_ambiguous_attempt(tmp_path, monkeypatch):
    path = _write_fixture(tmp_path / "skeleton.mp4", MP4)
    outcomes = [OSError("response lost token=secret"), (None, {"status_code": 614})]

    def put_file(*_args, **_kwargs):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(storage.qiniu, "put_file", put_file)
    monkeypatch.setattr(storage, "_SLEEP", lambda _: None)
    assert storage.upload_skeleton(upload_grant(), path).object_hash == qiniu.etag(str(path))

    monkeypatch.setattr(
        storage.qiniu,
        "put_file",
        lambda *_a, **_kw: (None, {"status_code": 614}),
    )
    with pytest.raises(StoragePermanentError):
        storage.upload_skeleton(upload_grant(), path)


def test_third_party_loggers_do_not_propagate_credentials(caplog):
    storage.configure_storage_logging(("download-secret", "upload-secret-token"))
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("httpx").error("https://cdn/x?token=download-secret")
        logging.getLogger("httpcore").error("/private/patient.mp4")
        logging.getLogger("qiniu").error("token=upload-secret-token")
        logging.getLogger("qiniu.http.private").error("token=upload-secret-token")

    assert "download-secret" not in caplog.text
    assert "upload-secret-token" not in caplog.text
    assert "patient.mp4" not in caplog.text
