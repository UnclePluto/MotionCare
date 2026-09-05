import importlib
import io
import tempfile
import threading
from pathlib import Path

import pytest
from motion_analysis_contract import PROTOCOL_VERSION, ClaimedJob

from pp_mcare.api_client import MotionCareUnavailableError
from pp_mcare.config import Settings
from pp_mcare.safe_logging import configure_safe_logging
from pp_mcare.worker import run_worker


def make_job(job_id):
    return ClaimedJob.from_dict(
        {
            "protocol_version": PROTOCOL_VERSION,
            "job_id": job_id,
            "action_source_key": "motion-resistance-shoulder-press",
            "algorithm_version": "PP-TinyPose_128x96",
            "rule_version": "shoulder-press-v2",
            "parameter_version": "shoulder-press-v2-defaults",
            "subject_tracker_version": "primary-subject-v1",
            "lease_token": f"lease-{job_id:037d}",
            "lease_expires_at": "2026-09-05T10:00:00+00:00",
            "heartbeat_interval_seconds": 60,
            "download": {
                "url": f"https://private.example/{job_id}.mp4?token=download-secret",
                "bucket": "original-videos",
                "object_key": f"training-videos/{job_id}/original.mp4",
                "expires_at": "2026-09-05T11:00:00+00:00",
                "size_bytes": 1024,
                "content_type": "video/mp4",
            },
            "upload": {
                "bucket": "analysis-skeletons",
                "object_key": f"motion-analysis/{job_id}/skeleton.mp4",
                "token": "upload-secret-token",
                "expires_at": "2026-09-05T13:00:00+00:00",
            },
        }
    )


TEST_DIRECTORY = tempfile.TemporaryDirectory(
    prefix="pp-mcare-worker-tests-",
    dir=Path(tempfile.gettempdir()).resolve(),
)
TEST_PATH_BASE = Path(TEST_DIRECTORY.name)


def service_settings():
    return Settings(
        api_base_url="https://motioncare.example",
        service_token="machine-service-secret",
        worker_id="worker-1",
        work_root=TEST_PATH_BASE / "jobs",
        model_cache=TEST_PATH_BASE / "model-cache",
        _trusted_path_base=TEST_PATH_BASE,
    )


class FakeClient:
    def __init__(self, claims, events=None):
        self.claims = iter(claims)
        self.claim_count = 0
        self.fail_calls = []
        self.events = events if events is not None else []

    def claim(self):
        self.claim_count += 1
        self.events.append("claim")
        value = next(self.claims)
        if isinstance(value, Exception):
            raise value
        return value

    def fail(self, job_id, **payload):
        self.events.append(f"fail:{job_id}")
        self.fail_calls.append((job_id, payload))


def test_empty_queue_sleeps_exactly_900_seconds_after_immediate_claim():
    events = []
    client = FakeClient([None], events)
    sleeps = []

    run_worker(
        client=client,
        processor=lambda job: events.append(f"process:{job.job_id}"),
        sleeper=lambda seconds: (events.append(f"sleep:{seconds}"), sleeps.append(seconds)),
        settings=service_settings(),
        max_claims=1,
    )

    assert events == ["claim", "sleep:900"]
    assert sleeps == [900]


def test_two_backlogged_jobs_are_processed_contiguously_before_empty_sleep():
    events = []
    client = FakeClient([make_job(1), make_job(2), None], events)

    run_worker(
        client=client,
        processor=lambda job: events.append(f"process:{job.job_id}"),
        sleeper=lambda seconds: events.append(f"sleep:{seconds}"),
        settings=service_settings(),
        max_claims=3,
    )

    assert client.claim_count == 3
    assert events == [
        "claim",
        "process:1",
        "claim",
        "process:2",
        "claim",
        "sleep:900",
    ]


def test_processor_exception_fails_once_then_claims_next_without_rerunning_inference():
    events = []
    client = FakeClient([make_job(1), make_job(2), None], events)
    process_calls = []

    def processor(job):
        events.append(f"process:{job.job_id}")
        process_calls.append(job.job_id)
        if job.job_id == 1:
            raise RuntimeError("inference failed /private/patient.mp4 token=secret")

    run_worker(
        client=client,
        processor=processor,
        sleeper=lambda seconds: events.append(f"sleep:{seconds}"),
        settings=service_settings(),
        max_claims=3,
    )

    assert process_calls == [1, 2]
    assert events == [
        "claim",
        "process:1",
        "fail:1",
        "claim",
        "process:2",
        "claim",
        "sleep:900",
    ]
    assert len(client.fail_calls) == 1
    job_id, payload = client.fail_calls[0]
    assert job_id == 1
    assert payload == {
        "lease_token": make_job(1).lease_token,
        "idempotency_key": "worker-processor-error-1",
        "failure_code": "processor_error",
        "summary": "任务处理异常",
        "stage_timings": {},
    }


def test_claim_retry_exhaustion_sleeps_poll_interval_and_keeps_loop_alive():
    client = FakeClient(
        [MotionCareUnavailableError("3次网络尝试耗尽"), make_job(2)],
    )
    sleeps = []
    processed = []

    run_worker(
        client=client,
        processor=lambda job: processed.append(job.job_id),
        sleeper=sleeps.append,
        settings=service_settings(),
        max_claims=2,
    )

    assert sleeps == [900]
    assert processed == [2]


def test_processor_fail_reporting_error_does_not_exit_or_start_second_active_job():
    events = []
    output = io.StringIO()
    configure_safe_logging(secrets=("machine-service-secret",), stream=output)
    client = FakeClient([make_job(1), make_job(2)], events)
    active = 0
    maximum_active = 0

    def broken_fail(job_id, **payload):
        client.fail_calls.append((job_id, payload))
        raise MotionCareUnavailableError(
            "https://private.example/fail?token=secret /private/patient.mp4"
        )

    client.fail = broken_fail

    def processor(job):
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        try:
            if job.job_id == 1:
                raise RuntimeError("patient-name private")
        finally:
            active -= 1

    run_worker(
        client=client,
        processor=processor,
        sleeper=lambda seconds: events.append(f"sleep:{seconds}"),
        settings=service_settings(),
        max_claims=2,
    )

    assert maximum_active == 1
    assert client.claim_count == 2
    assert len(client.fail_calls) == 1
    rendered = output.getvalue()
    assert "private.example" not in rendered
    assert "patient.mp4" not in rendered
    assert "machine-service-secret" not in rendered
    assert "event=motion_analysis_processor_failed" in rendered
    assert "method=None" in rendered
    assert "path=None" in rendered


def test_max_claims_zero_is_a_deterministic_noop():
    client = FakeClient([make_job(1)])

    run_worker(
        client=client,
        processor=lambda job: None,
        sleeper=lambda seconds: None,
        settings=service_settings(),
        max_claims=0,
    )

    assert client.claim_count == 0


def test_blocked_processor_prevents_prefetch_and_second_active_job():
    client = FakeClient([make_job(1), make_job(2)])
    started = threading.Event()
    release = threading.Event()
    active = 0
    maximum_active = 0
    processed = []

    def processor(job):
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        processed.append(job.job_id)
        try:
            if job.job_id == 1:
                started.set()
                assert release.wait(timeout=2)
        finally:
            active -= 1

    thread = threading.Thread(
        target=run_worker,
        kwargs={
            "client": client,
            "processor": processor,
            "sleeper": lambda _seconds: None,
            "settings": service_settings(),
            "max_claims": 2,
        },
    )
    thread.start()
    assert started.wait(timeout=2)

    assert client.claim_count == 1
    assert processed == [1]
    assert maximum_active == 1

    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert client.claim_count == 2
    assert processed == [1, 2]
    assert maximum_active == 1


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt(), SystemExit(7)])
def test_process_control_exceptions_are_not_converted_to_failure_reports(interrupt):
    client = FakeClient([make_job(1)])

    with pytest.raises(type(interrupt)):
        run_worker(
            client=client,
            processor=lambda _job: (_ for _ in ()).throw(interrupt),
            sleeper=lambda _seconds: None,
            settings=service_settings(),
            max_claims=1,
        )

    assert client.claim_count == 1
    assert client.fail_calls == []


def test_importing_cli_has_no_environment_or_network_side_effect(monkeypatch):
    monkeypatch.setenv("QINIU_ACCESS_KEY", "must-not-be-read-at-import")

    module = importlib.import_module("pp_mcare.__main__")

    assert callable(module.main)


def test_cli_refuses_to_start_before_constructing_client_or_claiming_jobs(monkeypatch, capsys):
    module = importlib.import_module("pp_mcare.__main__")
    configured = service_settings()
    calls = []

    class PoisonClient:
        def __init__(self, received_settings):
            calls.append(("client", received_settings))

        def claim(self):
            calls.append(("claim",))

        def fail(self, *_args, **_kwargs):
            calls.append(("fail",))

    monkeypatch.setattr(module.Settings, "from_env", lambda: configured)
    monkeypatch.setattr("pp_mcare.api_client.MotionCareClient", PoisonClient)
    monkeypatch.setattr(
        "pp_mcare.worker.run_worker",
        lambda **kwargs: calls.append(("worker", kwargs)),
    )

    assert module.main() != 0

    assert calls == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "pp-mcare 执行器尚未接入，拒绝启动\n"
    assert "machine-service-secret" not in captured.err
