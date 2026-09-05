import logging
import os
import stat
import threading

import httpx
import pytest
import qiniu
import requests
from qiniu.http import ResponseInfo
from motion_analysis_contract import DownloadGrant, UploadGrant

import pp_mcare.storage as storage
from pp_mcare.storage import StoragePermanentError, StorageTransientError
from pp_mcare.workspace import TaskWorkspace


MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"video" * 50


@pytest.fixture
def task_workspace(tmp_path):
    with TaskWorkspace.create(tmp_path / "jobs", 41) as workspace:
        yield workspace


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
        object_key=("motion-analysis/41/2026/09/11111111-1111-4111-8111-111111111111/skeleton.mp4"),
        token="upload-secret-token",
        expires_at="2026-09-05T13:00:00Z",
    )


def test_download_streams_private_mp4_and_validates_qiniu_etag(
    tmp_path, task_workspace, monkeypatch
):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=MP4, headers={"Content-Type": "video/mp4"})

    monkeypatch.setattr(storage, "_DOWNLOAD_TRANSPORT", httpx.MockTransport(handler))
    target = task_workspace.input_path
    expected = qiniu.etag(str(_write_fixture(tmp_path / "expected.mp4", MP4)))

    result = storage.download_original(
        download_grant(object_hash=expected), task_workspace, len(MP4), expected
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
def test_download_data_failures_are_not_retried_and_leave_no_partial(
    tmp_path, task_workspace, monkeypatch, case
):
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
    target = task_workspace.input_path
    with pytest.raises(StoragePermanentError):
        storage.download_original(
            download_grant(object_hash=expected_hash),
            task_workspace,
            expected_size,
            expected_hash,
        )

    assert attempts == 1
    assert not target.exists()


@pytest.mark.parametrize("status", [400, 401, 404, 416])
def test_download_4xx_and_redirect_are_not_retried(tmp_path, task_workspace, monkeypatch, status):
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(status, headers={"Location": "https://evil.example/steal"})

    monkeypatch.setattr(storage, "_DOWNLOAD_TRANSPORT", httpx.MockTransport(handler))
    with pytest.raises(StoragePermanentError):
        storage.download_original(
            download_grant(object_hash="hash"), task_workspace, len(MP4), "hash"
        )
    assert attempts == 1


def test_download_retries_5xx_three_times_with_clean_files(task_workspace, monkeypatch):
    attempts = 0
    sleeps = []

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    monkeypatch.setattr(storage, "_DOWNLOAD_TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(storage, "_SLEEP", sleeps.append)
    target = task_workspace.input_path
    with pytest.raises(StorageTransientError):
        storage.download_original(
            download_grant(object_hash="hash"), task_workspace, len(MP4), "hash"
        )
    assert attempts == 3
    assert sleeps == [1.0, 2.0]
    assert not target.exists()


def test_download_retries_interrupted_response_from_a_clean_file(
    tmp_path, task_workspace, monkeypatch
):
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
    target = task_workspace.input_path
    result = storage.download_original(
        download_grant(object_hash=expected_hash), task_workspace, len(MP4), expected_hash
    )

    assert attempts == 3
    assert target.read_bytes() == MP4
    assert result.size_bytes == len(MP4)


def test_upload_validates_key_hash_and_size(task_workspace, monkeypatch):
    path = _write_fixture(task_workspace.output_path, MP4)
    local_hash = qiniu.etag(str(path))
    calls = []

    def put_file(token, key, file_path, **kwargs):
        calls.append((token, key, file_path, kwargs))
        return {"key": key, "hash": local_hash}, {"status_code": 200}

    monkeypatch.setattr(storage.qiniu, "put_file", put_file)
    result = storage.upload_skeleton(upload_grant(), task_workspace)

    assert result.object_hash == local_hash
    assert result.size_bytes == len(MP4)
    assert calls[0][0:2] == ("upload-secret-token", upload_grant().object_key)
    assert "upload-secret-token" not in repr(result)


def test_upload_retries_transient_but_not_4xx(task_workspace, monkeypatch):
    _write_fixture(task_workspace.output_path, MP4)
    attempts = 0

    def put_file(_token, _key, _path, **_kwargs):
        nonlocal attempts
        attempts += 1
        return None, {"status_code": 503, "exception": "token=secret /private/video"}

    monkeypatch.setattr(storage.qiniu, "put_file", put_file)
    monkeypatch.setattr(storage, "_SLEEP", lambda _: None)
    with pytest.raises(StorageTransientError):
        storage.upload_skeleton(upload_grant(), task_workspace)
    assert attempts == 3

    attempts = 0

    def bad_request(_token, _key, _path, **_kwargs):
        nonlocal attempts
        attempts += 1
        return None, {"status_code": 401}

    monkeypatch.setattr(storage.qiniu, "put_file", bad_request)
    with pytest.raises(StoragePermanentError):
        storage.upload_skeleton(upload_grant(), task_workspace)
    assert attempts == 1


@pytest.mark.parametrize("wrong_field", ["key", "hash"])
def test_upload_rejects_provider_identity_mismatch_without_retry(
    task_workspace, monkeypatch, wrong_field
):
    path = _write_fixture(task_workspace.output_path, MP4)
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
        storage.upload_skeleton(upload_grant(), task_workspace)
    assert calls == 1


def test_upload_only_accepts_614_after_an_ambiguous_attempt(task_workspace, monkeypatch):
    path = _write_fixture(task_workspace.output_path, MP4)
    outcomes = [OSError("response lost token=secret"), (None, {"status_code": 614})]

    def put_file(*_args, **_kwargs):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(storage.qiniu, "put_file", put_file)
    monkeypatch.setattr(storage, "_SLEEP", lambda _: None)
    assert storage.upload_skeleton(upload_grant(), task_workspace).object_hash == qiniu.etag(
        str(path)
    )

    monkeypatch.setattr(
        storage.qiniu,
        "put_file",
        lambda *_a, **_kw: (None, {"status_code": 614}),
    )
    with pytest.raises(StoragePermanentError):
        storage.upload_skeleton(upload_grant(), task_workspace)


def test_upload_real_response_info_transport_failure_is_ambiguous_and_bounded(
    task_workspace, monkeypatch
):
    path = _write_fixture(task_workspace.output_path, MP4)
    outcomes = [
        (None, ResponseInfo(None, OSError("https://secret.example?token=leak"))),
        (None, {"status_code": 614}),
    ]
    calls = []

    def put_file(*args, **kwargs):
        calls.append((args, kwargs))
        return outcomes.pop(0)

    monkeypatch.setattr(storage.qiniu, "put_file", put_file)
    monkeypatch.setattr(storage, "_SLEEP", lambda _: None)

    result = storage.upload_skeleton(upload_grant(), task_workspace)

    assert result.object_hash == qiniu.etag(str(path))
    assert len(calls) == 2

    calls.clear()
    monkeypatch.setattr(
        storage.qiniu,
        "put_file",
        lambda *_a, **_kw: (
            calls.append(1) or None,
            ResponseInfo(None, ConnectionError("connection lost")),
        ),
    )
    with pytest.raises(StorageTransientError):
        storage.upload_skeleton(upload_grant(), task_workspace)
    assert len(calls) == 3


@pytest.mark.parametrize("kind", ["negative", "exception", "connect_failed"])
def test_real_qiniu_response_info_ambiguous_shapes_each_retry_three_times(
    task_workspace, monkeypatch, kind
):
    _write_fixture(task_workspace.output_path, MP4)
    calls = 0

    def response_info():
        if kind == "negative":
            return ResponseInfo(None)
        response = requests.Response()
        response.status_code = 400
        response.url = "https://upload.qiniup.com"
        response._content = b'{"error":"safe"}'
        if kind == "exception":
            response.headers["X-Reqid"] = "request-id"
            return ResponseInfo(response, ConnectionError("response interrupted"))
        return ResponseInfo(response)

    def put_file(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return None, response_info()

    monkeypatch.setattr(storage.qiniu, "put_file", put_file)
    monkeypatch.setattr(storage, "_SLEEP", lambda _: None)

    with pytest.raises(StorageTransientError):
        storage.upload_skeleton(upload_grant(), task_workspace)
    assert calls == 3
    assert qiniu.config.get_default("connection_retries") == 1


def test_upload_rejects_malformed_provider_response_without_retry(task_workspace, monkeypatch):
    _write_fixture(task_workspace.output_path, MP4)
    calls = 0

    def malformed(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return "not-a-result", object()

    monkeypatch.setattr(storage.qiniu, "put_file", malformed)
    with pytest.raises(StoragePermanentError):
        storage.upload_skeleton(upload_grant(), task_workspace)
    assert calls == 1


def test_qiniu_root_logging_boundary_drops_sdk_secret_without_mutating_host_records():
    root = logging.getLogger()
    original_level = root.level
    original_filters = tuple(root.filters)
    original_factory = logging.getLogRecordFactory()
    received = [[], []]

    class Capture(logging.Handler):
        def __init__(self, sink):
            super().__init__()
            self.sink = sink

        def emit(self, record):
            self.sink.append(record)

    handlers = [Capture(sink) for sink in received]
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    def forge_record_source(*args, **kwargs):
        record = original_factory(*args, **kwargs)
        if record.msg == "host event %s":
            record.pathname = str(storage._QINIU_PACKAGE_ROOT / "forged-host.py")
            record.module = "qiniu"
        elif isinstance(record.msg, str) and record.msg.startswith("response body decode error"):
            record.pathname = "/outside/forged-qiniu.py"
            record.module = "host"
        return record

    logging.setLogRecordFactory(forge_record_source)
    try:
        storage.configure_storage_logging(("upload-secret-token",))
        error = RuntimeError("ordinary host exception")
        try:
            raise error
        except RuntimeError:
            exc_info = __import__("sys").exc_info()
        with storage._qiniu_root_logging_boundary():
            logging.info("host event %s", "kept", extra={"tenant_id": 17}, exc_info=exc_info)
            response = requests.Response()
            response.status_code = 200
            response.url = "https://upload.example?token=upload-secret-token"
            response.headers["X-Reqid"] = "request-id"
            response._content = (
                b"https://cdn.example?token=upload-secret-token "
                b"motion-analysis/private /patient/path body=PHI"
            )
            qiniu.http.__dict__["__return_wrapper"](response)

        assert tuple(root.filters) == original_filters
        assert [len(sink) for sink in received] == [1, 1]
        for record in (received[0][0], received[1][0]):
            assert record.msg == "host event %s"
            assert record.args == ("kept",)
            assert record.exc_info == exc_info
            assert record.tenant_id == 17
        assert received[0][0] is received[1][0]
    finally:
        logging.setLogRecordFactory(original_factory)
        root.setLevel(original_level)
        for handler in handlers:
            root.removeHandler(handler)


def test_qiniu_root_boundary_preserves_malformed_and_concurrent_host_records():
    root = logging.getLogger()
    original_level = root.level
    original_filters = tuple(root.filters)
    original_handlers = tuple(root.handlers)
    received = []

    class Capture(logging.Handler):
        def emit(self, record):
            received.append(record)

    handler = Capture()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    malformed = logging.LogRecord("host", logging.INFO, "host.py", 1, "malformed", (), None)
    malformed.pathname = None
    malformed.module = None
    try:
        with storage._qiniu_root_logging_boundary():
            thread = threading.Thread(target=logging.info, args=("thread event %s", "kept"))
            thread.start()
            thread.join(5)
            assert not thread.is_alive()
            root.handle(malformed)

        assert len(received) == 2
        assert received[0].msg == "thread event %s"
        assert received[0].args == ("kept",)
        assert received[1] is malformed
        assert malformed.msg == "malformed"
        assert tuple(root.filters) == original_filters
    finally:
        root.setLevel(original_level)
        root.removeHandler(handler)
    assert tuple(root.handlers) == original_handlers


def test_qiniu_root_boundary_restores_root_state_after_exception():
    root = logging.getLogger()
    original_filters = tuple(root.filters)
    original_handlers = tuple(root.handlers)

    with pytest.raises(RuntimeError, match="sdk call failed"):
        with storage._qiniu_root_logging_boundary():
            raise RuntimeError("sdk call failed")

    assert tuple(root.filters) == original_filters
    assert tuple(root.handlers) == original_handlers


def test_linux_fd_path_never_falls_back_to_dev_fd(monkeypatch):
    monkeypatch.setattr(storage.sys, "platform", "linux")
    monkeypatch.setattr(storage.os.path, "exists", lambda path: path.startswith("/dev/fd/"))

    with pytest.raises(StoragePermanentError, match="不支持"):
        storage._fd_path(9)


def test_upload_uses_anchored_fd_when_leaf_is_replaced(tmp_path, monkeypatch):
    with TaskWorkspace.create(tmp_path / "jobs", 41) as workspace:
        fd = workspace.create_file("skeleton.mp4")
        os.write(fd, MP4)
        os.fsync(fd)
        os.close(fd)
        outside = tmp_path / "outside.mp4"
        outside.write_bytes(b"outside")
        expected = qiniu.etag(str(workspace.output_path))

        def put_file(_token, key, fd_path, **_kwargs):
            workspace.output_path.unlink()
            workspace.output_path.symlink_to(outside)
            with open(fd_path, "rb") as uploaded:
                assert uploaded.read() == MP4
            return {"key": key, "hash": expected}, {"status_code": 200}

        monkeypatch.setattr(storage.qiniu, "put_file", put_file)
        result = storage.upload_skeleton(upload_grant(), workspace)

        assert result.object_hash == expected
        assert outside.read_bytes() == b"outside"


def test_download_hashes_open_fd_and_rejects_leaf_replacement(tmp_path, monkeypatch):
    root = tmp_path / "jobs"
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(MP4.replace(b"video", b"other"))

    with TaskWorkspace.create(root, 42) as workspace:
        expected_path = _write_fixture(tmp_path / "expected.mp4", MP4)
        expected_hash = qiniu.etag(str(expected_path))

        class ReplacingBody(httpx.SyncByteStream):
            def __iter__(self):
                yield MP4[:20]
                workspace.input_path.rename(workspace.path / "saved-original.mp4")
                workspace.input_path.symlink_to(outside)
                yield MP4[20:]

        def handler(request):
            return httpx.Response(
                200,
                headers={"Content-Type": "video/mp4"},
                stream=ReplacingBody(),
            )

        monkeypatch.setattr(storage, "_DOWNLOAD_TRANSPORT", httpx.MockTransport(handler))
        with pytest.raises(StoragePermanentError, match="发生变化"):
            storage.download_original(
                download_grant(object_hash=expected_hash), workspace, len(MP4), expected_hash
            )

        assert outside.read_bytes() != MP4


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
