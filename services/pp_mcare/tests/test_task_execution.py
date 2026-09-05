import json
import io
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from motion_analysis_contract import ClaimedJob, MotionCounts, PROTOCOL_VERSION

import pp_mcare.config as config_module
import pp_mcare.worker as worker
from pp_mcare.config import Settings
from pp_mcare.media import VideoMetadata
from pp_mcare.media import SourceVideoMetadata
from pp_mcare.pipeline import LocalAnalysisResult
from pp_mcare.safe_logging import configure_safe_logging


TEST_DIRECTORY = tempfile.TemporaryDirectory(prefix="pp-mcare-task11-")
TEST_ROOT = Path(TEST_DIRECTORY.name)


def make_job(job_id=41, heartbeat_interval_seconds=60):
    return ClaimedJob.from_dict(
        {
            "protocol_version": PROTOCOL_VERSION,
            "job_id": job_id,
            "action_source_key": "motion-resistance-shoulder-press",
            "algorithm_version": "PP-TinyPose_128x96",
            "rule_version": "shoulder-press-v2",
            "parameter_version": "shoulder-press-v2-defaults",
            "subject_tracker_version": "primary-subject-v1",
            "lease_token": "l" * 43,
            "lease_expires_at": "2026-09-05T10:00:00Z",
            "heartbeat_interval_seconds": heartbeat_interval_seconds,
            "download": {
                "url": "https://cdn.example/input.mp4?token=download-secret",
                "bucket": "private",
                "object_key": "training/original.mp4",
                "object_hash": "FqiniuOriginalHash1234567890abc",
                "expires_at": "2026-09-05T11:00:00Z",
                "size_bytes": 128,
                "content_type": "video/mp4",
            },
            "upload": {
                "bucket": "private",
                "object_key": (
                    f"motion-analysis/{job_id}/2026/09/"
                    "11111111-1111-4111-8111-111111111111/skeleton.mp4"
                ),
                "token": "upload-secret-token",
                "expires_at": "2026-09-05T13:00:00Z",
            },
        }
    )


def make_settings(root):
    with patch.object(config_module, "_TRUSTED_PATH_BASE", root):
        return Settings(
            api_base_url="https://motioncare.example",
            service_token="service-token",
            worker_id="worker-1",
            work_root=root / "jobs",
            model_cache=root / "models",
        )


def local_result():
    return LocalAnalysisResult(
        counts=MotionCounts(90, 80, 10),
        quality_summary={"confidence_level": "high", "quality_flags": []},
        result_payload={"total_count": 90, "standard_count": 80, "nonstandard_count": 10},
        tracking_summary={"subject_coverage_ratio": 0.99, "observation_fingerprint": "private"},
        decoded_frame_count=8929,
        inferred_frame_count=8929,
        encoded_frame_count=8929,
        inference_seconds=100.0,
        encoding_seconds=50.0,
        media_metadata=VideoMetadata(1920, 1080, 30.0, 8929, 297.6, "h264", "yuv420p", False, True),
    )


@pytest.fixture(autouse=True)
def source_probe(monkeypatch):
    monkeypatch.setattr(
        worker,
        "_workspace_tool_paths",
        lambda workspace: (workspace.input_path, workspace.output_path),
    )
    monkeypatch.setattr(
        worker,
        "probe_source_video",
        lambda _path: SourceVideoMetadata(1920, 1080, 30.0, 8929, 297.6, "h264"),
        raising=False,
    )


class FakeClient:
    def __init__(self):
        self.heartbeat_calls = []
        self.complete_calls = []
        self.fail_calls = []

    def heartbeat(self, job_id, lease_token, stage):
        self.heartbeat_calls.append((job_id, lease_token, stage))

    def complete(self, job_id, payload):
        self.complete_calls.append((job_id, payload))

    def fail(self, job_id, **payload):
        self.fail_calls.append((job_id, payload))


def test_process_uploads_completes_once_reuses_pipeline_and_cleans(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    client = FakeClient()
    pipeline_calls = []

    def download(_grant, workspace, _size, _hash):
        workspace.input_path.write_bytes(b"input")

    def pipeline(job, _input, output, heartbeat, **_kwargs):
        pipeline_calls.append(job.job_id)
        heartbeat("inference")
        output.write_bytes(b"skeleton")
        return local_result()

    monkeypatch.setattr(worker, "download_original", download)
    monkeypatch.setattr(worker, "run_local_pipeline", pipeline)
    monkeypatch.setattr(
        worker,
        "upload_skeleton",
        lambda grant, workspace: worker.UploadedObject(
            grant.bucket, grant.object_key, "etag", workspace.output_path.stat().st_size
        ),
    )

    worker.process_claimed_job(make_job(), client, settings)

    assert pipeline_calls == [41]
    assert len(client.complete_calls) == 1
    assert client.complete_calls[0][1].counts == MotionCounts(90, 80, 10)
    assert client.fail_calls == []
    assert list(settings.work_root.iterdir()) == []


def test_process_logs_only_safe_resource_and_cleanup_metrics(tmp_path, monkeypatch):
    output = io.StringIO()
    configure_safe_logging(stream=output)
    settings = make_settings(tmp_path)
    client = FakeClient()
    monkeypatch.setattr(
        worker, "download_original", lambda _g, w, _s, _h: w.input_path.write_bytes(b"x")
    )

    def pipeline(_job, _input, output_path, _heartbeat, **_kwargs):
        output_path.write_bytes(b"skeleton")
        return local_result()

    monkeypatch.setattr(worker, "run_local_pipeline", pipeline)
    monkeypatch.setattr(
        worker,
        "upload_skeleton",
        lambda g, w: worker.UploadedObject(
            g.bucket, g.object_key, "etag", w.output_path.stat().st_size
        ),
    )

    worker.process_claimed_job(make_job(), client, settings)

    rendered = output.getvalue()
    for field in (
        "peak_rss_bytes=",
        "system_available_memory_bytes=",
        "swap_used_bytes=",
        "disk_free_bytes=",
    ):
        assert field in rendered
    assert "event=motion_analysis_workspace_cleanup" in rendered
    assert "outcome=removed" in rendered
    assert "download-secret" not in rendered
    assert "upload-secret-token" not in rendered
    assert "observation_fingerprint" not in rendered
    assert "stage=inference" in rendered
    assert "stage=encoding" in rendered
    assert "stage=analyze" not in rendered


def test_complete_response_loss_reuses_same_idempotency_without_pipeline_retry(
    tmp_path, monkeypatch
):
    settings = make_settings(tmp_path)
    bodies = []
    pipeline_calls = 0

    def pipeline(_job, _input, output, _heartbeat, **_kwargs):
        nonlocal pipeline_calls
        pipeline_calls += 1
        output.write_bytes(b"skeleton")
        return local_result()

    def handler(request):
        bodies.append(bytes(request.content))
        if len(bodies) < 3:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            json={
                "protocol_version": PROTOCOL_VERSION,
                "job_id": 41,
                "status": "succeeded",
                "finished_at": "2026-09-05T10:10:00Z",
                "total_count": 90,
                "standard_count": 80,
                "nonstandard_count": 10,
            },
            request=request,
        )

    client = worker.MotionCareClient(
        settings,
        transport=httpx.MockTransport(handler),
        sleeper=lambda _seconds: None,
    )
    monkeypatch.setattr(
        worker, "download_original", lambda _g, w, _s, _h: w.input_path.write_bytes(b"x")
    )
    monkeypatch.setattr(worker, "run_local_pipeline", pipeline)
    monkeypatch.setattr(
        worker,
        "upload_skeleton",
        lambda g, w: worker.UploadedObject(
            g.bucket, g.object_key, "etag", w.output_path.stat().st_size
        ),
    )

    try:
        worker.process_claimed_job(make_job(), client, settings)
    finally:
        client.close()

    assert pipeline_calls == 1
    assert len(bodies) == 3
    assert bodies[0] == bodies[1] == bodies[2]
    assert len({json.loads(body)["idempotency_key"] for body in bodies}) == 1


def test_pipeline_failure_reports_once_with_fixed_redacted_payload_and_cleans(
    tmp_path, monkeypatch
):
    settings = make_settings(tmp_path)
    client = FakeClient()
    monkeypatch.setattr(
        worker, "download_original", lambda _g, w, _s, _h: w.input_path.write_bytes(b"x")
    )
    monkeypatch.setattr(
        worker,
        "run_local_pipeline",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("https://secret /private/patient")),
    )

    worker.process_claimed_job(make_job(), client, settings)

    assert len(client.fail_calls) == 1
    payload = client.fail_calls[0][1]
    assert payload["failure_code"] == "analysis_failed"
    assert payload["summary"] == "动作分析失败"
    assert "secret" not in repr(payload)
    assert list(settings.work_root.iterdir()) == []


def test_complete_exhaustion_after_upload_fails_once_and_still_cleans(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    client = FakeClient()
    complete_calls = 0

    def complete(_job_id, _payload):
        nonlocal complete_calls
        complete_calls += 1
        raise worker.MotionCareUnavailableError("provider secret")

    client.complete = complete
    monkeypatch.setattr(
        worker, "download_original", lambda _g, w, _s, _h: w.input_path.write_bytes(b"x")
    )

    def pipeline(_job, _input, output, _heartbeat, **_kwargs):
        output.write_bytes(b"skeleton")
        return local_result()

    monkeypatch.setattr(worker, "run_local_pipeline", pipeline)
    monkeypatch.setattr(
        worker,
        "upload_skeleton",
        lambda g, w: worker.UploadedObject(
            g.bucket, g.object_key, "etag", w.output_path.stat().st_size
        ),
    )

    worker.process_claimed_job(make_job(), client, settings)

    assert complete_calls == 1
    assert len(client.fail_calls) == 1
    assert list(settings.work_root.iterdir()) == []


def test_failure_report_error_is_attempted_once_without_leaking_or_residue(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    client = FakeClient()
    fail_calls = 0

    def fail(*_args, **_kwargs):
        nonlocal fail_calls
        fail_calls += 1
        raise RuntimeError("https://secret.example token=upload-secret-token /private/patient")

    client.fail = fail
    monkeypatch.setattr(
        worker, "download_original", lambda *_a: (_ for _ in ()).throw(RuntimeError("bad"))
    )

    worker.process_claimed_job(make_job(), client, settings)

    assert fail_calls == 1
    assert list(settings.work_root.iterdir()) == []


def test_sigterm_control_exception_cleans_published_output(tmp_path):
    from pp_mcare.__main__ import GracefulShutdown, _handle_shutdown_signal
    from pp_mcare.workspace import TaskWorkspace

    with pytest.raises(GracefulShutdown):
        with TaskWorkspace.create(tmp_path, 77) as workspace:
            workspace.output_path.write_bytes(b"published")
            _handle_shutdown_signal(15, None)

    assert list(tmp_path.iterdir()) == []


def test_heartbeat_background_failure_stops_main_path_and_joins(tmp_path):
    client = FakeClient()
    started = threading.Event()

    def broken(*_args):
        started.set()
        raise worker.MotionCareConflictError("lease lost")

    client.heartbeat = broken
    lease = worker.HeartbeatLease(
        client, make_job(heartbeat_interval_seconds=1), wait=lambda _n: started.wait(0.01)
    )
    with lease:
        assert started.wait(1)
        with pytest.raises(worker.LeaseLostError):
            lease.raise_if_lost()
    assert not lease.is_alive


def test_worker_does_not_double_fail_processor_that_owns_failure_reporting(tmp_path):
    settings = make_settings(tmp_path)
    job = make_job()

    class ClaimClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.claims = iter([job, None])

        def claim(self):
            return next(self.claims)

    client = ClaimClient()

    def processor(_job):
        client.fail(_job.job_id, failure_code="analysis_failed")
        raise worker.JobAlreadyFinalized()

    worker.run_worker(
        client=client,
        processor=processor,
        sleeper=lambda _n: None,
        settings=settings,
        max_claims=2,
    )
    assert len(client.fail_calls) == 1


def test_video_over_60_minutes_fails_before_pipeline_or_upload(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    client = FakeClient()
    pipeline_calls = []
    upload_calls = []
    monkeypatch.setattr(
        worker, "download_original", lambda _g, w, _s, _h: w.input_path.write_bytes(b"x")
    )
    monkeypatch.setattr(
        worker,
        "probe_source_video",
        lambda _path: SourceVideoMetadata(1920, 1080, 30.0, 108001, 3600.001, "h264"),
    )
    monkeypatch.setattr(worker, "run_local_pipeline", lambda *_a, **_k: pipeline_calls.append(1))
    monkeypatch.setattr(worker, "upload_skeleton", lambda *_a, **_k: upload_calls.append(1))

    worker.process_claimed_job(make_job(), client, settings)

    assert pipeline_calls == []
    assert upload_calls == []
    assert client.fail_calls[0][1]["failure_code"] == "video_too_long"


def test_exactly_60_minutes_is_allowed(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    client = FakeClient()
    monkeypatch.setattr(
        worker, "download_original", lambda _g, w, _s, _h: w.input_path.write_bytes(b"x")
    )
    monkeypatch.setattr(
        worker,
        "probe_source_video",
        lambda _path: SourceVideoMetadata(1920, 1080, 30.0, 108000, 3600.0, "h264"),
    )

    def pipeline(_job, _input, output, _heartbeat, **_kwargs):
        output.write_bytes(b"skeleton")
        return local_result()

    monkeypatch.setattr(worker, "run_local_pipeline", pipeline)
    monkeypatch.setattr(
        worker,
        "upload_skeleton",
        lambda g, w: worker.UploadedObject(
            g.bucket, g.object_key, "etag", w.output_path.stat().st_size
        ),
    )

    worker.process_claimed_job(make_job(), client, settings)

    assert len(client.complete_calls) == 1
    assert client.fail_calls == []


def test_heartbeat_join_timeout_is_process_fatal_and_stops_next_claim(tmp_path):
    settings = make_settings(tmp_path)
    job = make_job()

    class ClaimClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.claim_count = 0

        def claim(self):
            self.claim_count += 1
            return job

    client = ClaimClient()
    entered = threading.Event()
    release = threading.Event()
    original_join_timeout = worker._HEARTBEAT_JOIN_SECONDS
    worker._HEARTBEAT_JOIN_SECONDS = 0.01

    def fatal(_job):
        client.heartbeat = lambda *_args: (entered.set(), release.wait(2))
        with worker.HeartbeatLease(client, _job, wait=lambda _seconds: False):
            assert entered.wait(1)

    try:
        with pytest.raises(worker.HeartbeatFatalError):
            worker.run_worker(
                client=client,
                processor=fatal,
                sleeper=lambda _n: None,
                settings=settings,
            )
    finally:
        release.set()
        worker._HEARTBEAT_JOIN_SECONDS = original_join_timeout
    assert client.claim_count == 1


def test_control_baseexception_wins_over_workspace_cleanup_failure(tmp_path, monkeypatch):
    from pp_mcare.__main__ import GracefulShutdown
    from pp_mcare.workspace import TaskWorkspace

    workspace = TaskWorkspace.create(tmp_path, 55)
    monkeypatch.setattr(workspace, "cleanup", lambda: (_ for _ in ()).throw(OSError("cleanup")))

    with pytest.raises(GracefulShutdown):
        with workspace:
            raise GracefulShutdown(0)
    TaskWorkspace.cleanup(workspace)


def test_sigterm_wins_when_heartbeat_is_blocked_and_cleanup_fails(tmp_path, monkeypatch):
    from pp_mcare.__main__ import GracefulShutdown, _handle_shutdown_signal
    from pp_mcare.workspace import TaskWorkspace

    entered = threading.Event()
    release = threading.Event()
    client = FakeClient()

    def blocking_heartbeat(*_args):
        entered.set()
        release.wait(2)

    client.heartbeat = blocking_heartbeat
    monkeypatch.setattr(worker, "_HEARTBEAT_JOIN_SECONDS", 0.01, raising=False)
    workspace = TaskWorkspace.create(tmp_path, 56)
    monkeypatch.setattr(workspace, "cleanup", lambda: (_ for _ in ()).throw(OSError("cleanup")))
    lease = worker.HeartbeatLease(client, make_job(), wait=lambda _seconds: False)

    try:
        with pytest.raises(GracefulShutdown):
            with workspace, lease:
                assert entered.wait(1)
                _handle_shutdown_signal(15, None)
    finally:
        release.set()
        lease.stop()
        TaskWorkspace.cleanup(workspace)
