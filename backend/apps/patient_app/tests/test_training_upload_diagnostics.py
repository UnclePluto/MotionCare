import json
import uuid
from collections import defaultdict
from datetime import timedelta
from io import StringIO

import pytest
from django.apps import apps
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.patient_app.services import create_binding_code, bind_project_patient_with_code
from apps.patient_app.throttles import RedisFixedWindowRateThrottle
from apps.training.models import TrainingVideo

URL = "/api/patient-app/training-upload-diagnostics/"
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def rate_limit(monkeypatch):
    counts = defaultdict(int)

    class Redis:
        def eval(self, script, key_count, key, window):
            counts[key] += 1
            return counts[key]

    monkeypatch.setattr(
        RedisFixedWindowRateThrottle, "redis_client_factory", staticmethod(lambda _: Redis())
    )


@pytest.fixture
def authenticated(project_patient, doctor):
    code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    token, _ = bind_project_patient_with_code(code, wx_openid="diagnostic-openid")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def video(project_patient, active_prescription, prescription_action):
    return TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        client_session_id=uuid.uuid4(),
    )


def payload(**overrides):
    return dict(
        event_id=str(uuid.uuid4()),
        occurred_at=timezone.now().isoformat(),
        stage="upload",
        error_code="upload_network_failed",
        message="uploadFile:fail timeout",
        network_type="wifi",
        platform="ios",
        sdk_version="3.0.0",
        app_version="1.0.0",
        **overrides,
    )


def rows():
    return apps.get_model("training", "TrainingUploadDiagnostic").objects


def test_authenticated_diagnostic_without_video_is_idempotent(authenticated, project_patient):
    data = payload()
    first = authenticated.post(URL, data, format="json")
    assert first.status_code == 200
    assert first.json() == {"event_id": data["event_id"]}
    row = rows().get()
    assert row.project_patient == project_patient
    assert row.video_id is None
    received_at = row.received_at
    data["message"] = "changed"
    assert authenticated.post(URL, data, format="json").status_code == 200
    row.refresh_from_db()
    assert rows().count() == 1
    assert row.received_at == received_at
    assert row.message == "uploadFile:fail timeout"


def test_requires_patient_bearer_authentication(client, doctor):
    assert client.post(URL, payload(), content_type="application/json").status_code in (401, 403)
    client.force_login(doctor)
    assert client.post(URL, payload(), content_type="application/json").status_code in (401, 403)


def test_video_ownership_and_session_match(authenticated, video):
    data = payload(video_id=video.id, client_session_id=str(video.client_session_id))
    assert authenticated.post(URL, data, format="json").status_code == 200
    assert rows().get().video_id == video.id
    data["event_id"] = str(uuid.uuid4())
    data["client_session_id"] = str(uuid.uuid4())
    assert authenticated.post(URL, data, format="json").status_code == 400
    video.project_patient = None
    video.save(update_fields=["project_patient"])
    data["client_session_id"] = str(video.client_session_id)
    assert authenticated.post(URL, data, format="json").status_code == 400
    assert rows().count() == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("token", "secret"),
        ("patient_id", 1),
        ("event_id", "not-uuid"),
        ("client_session_id", "not-uuid"),
        ("stage", "unknown"),
        ("occurred_at", "bad"),
        ("error_code", "x" * 65),
        ("error_code", "https://secret"),
        ("message", "x" * 501),
        ("platform", "x" * 33),
        ("sdk_version", "x" * 33),
        ("app_version", "x" * 33),
        ("network_type", "https://secret"),
        ("video_id", -1),
        ("segment_index", -1),
        ("http_status", 99),
        ("http_status", 600),
    ],
)
def test_invalid_fields_rejected(authenticated, field, value):
    data = payload()
    data[field] = value
    assert authenticated.post(URL, data, format="json").status_code == 400
    assert rows().count() == 0


def test_oversized_body_and_non_object_rejected(authenticated):
    raw = json.dumps(payload()) + " " * 4096
    assert authenticated.post(URL, raw, content_type="application/json").status_code == 413
    assert authenticated.post(URL, [], format="json").status_code == 400


@pytest.mark.parametrize(
    "message",
    [
        "uploadFile:fail timeout https://cdn.example/a?token=SECRET wxfile://tmp/a.mp4 13812345678",
        "Bearer SECRET token=SECRET /private/tmp/private.mp4 C:\\Users\\private.mp4",
        '{"responseBody":{"name":"患者甲","secret":"SECRET"}}',
        "name=患者甲 response body: SECRET",
    ],
)
def test_message_never_persists_sensitive_original(authenticated, message):
    data = payload()
    data["message"] = message
    assert authenticated.post(URL, data, format="json").status_code == 200
    saved = rows().get().message
    for secret in ("SECRET", "患者甲", "13812345678", "cdn.example", "private.mp4", "responseBody"):
        assert secret not in saved


def test_rate_limit_and_safe_outage(authenticated, monkeypatch):
    for _ in range(60):
        assert authenticated.post(URL, payload(), format="json").status_code == 200
    assert authenticated.post(URL, payload(), format="json").status_code == 429

    def fail(_):
        raise RuntimeError("redis://user:SECRET@host")

    monkeypatch.setattr(RedisFixedWindowRateThrottle, "redis_client_factory", staticmethod(fail))
    response = authenticated.post(URL, payload(), format="json")
    assert response.status_code == 503
    assert "SECRET" not in response.content.decode()


def test_retention_boundary_query_and_scheduled_cleanup(
    authenticated, video, settings, monkeypatch
):
    from apps.training.tasks import cleanup_training_upload_diagnostics

    now = timezone.now()
    for age in [
        timedelta(days=15, microseconds=1),
        timedelta(days=15),
        timedelta(days=15, microseconds=-1),
    ]:
        data = payload(video_id=video.pk, client_session_id=str(video.client_session_id))
        assert authenticated.post(URL, data, format="json").status_code == 200
        rows().filter(event_id=data["event_id"]).update(received_at=now - age)
    monkeypatch.setattr("django.utils.timezone.now", lambda: now)
    out = StringIO()
    call_command("training_upload_diagnostics", video_id=video.pk, stdout=out)
    result = json.loads(out.getvalue())
    assert len(result) == 1
    assert "project_patient_id" not in result[0]
    out = StringIO()
    call_command(
        "training_upload_diagnostics", client_session_id=str(video.client_session_id), stdout=out
    )
    assert len(json.loads(out.getvalue())) == 1
    assert cleanup_training_upload_diagnostics() == 2
    assert rows().count() == 1
    assert TrainingVideo.objects.filter(pk=video.pk).exists()
    entry = settings.CELERY_BEAT_SCHEDULE["cleanup-training-upload-diagnostics"]
    assert entry["schedule"] == 3600
    assert entry["task"] == "apps.training.tasks.cleanup_training_upload_diagnostics"


def test_event_id_and_video_are_scoped_to_project_patient(
    authenticated, project_patient, doctor, video
):
    from apps.patients.models import Patient
    from apps.studies.models import ProjectPatient

    other = ProjectPatient.objects.create(
        project=project_patient.project,
        group=project_patient.group,
        patient=Patient.objects.create(
            name="患者乙", gender="female", age=60, phone="13900001112", primary_doctor=doctor
        ),
    )
    code, _ = create_binding_code(project_patient=other, created_by=doctor)
    token, _ = bind_project_patient_with_code(code, wx_openid="other-diagnostic-openid")
    other_client = APIClient()
    other_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    data = payload()
    assert authenticated.post(URL, data, format="json").status_code == 200
    assert other_client.post(URL, data, format="json").status_code == 200
    assert rows().filter(event_id=data["event_id"]).count() == 2
    data = payload(video_id=video.pk, client_session_id=str(video.client_session_id))
    assert other_client.post(URL, data, format="json").status_code == 400
    assert rows().count() == 2


def test_query_default_limit_filters_and_requires_correlation(authenticated, video):
    from django.core.management.base import CommandError

    data = payload(video_id=video.pk, client_session_id=str(video.client_session_id))
    assert authenticated.post(URL, data, format="json").status_code == 200
    template = rows().get()
    copies = []
    for _ in range(104):
        copies.append(
            type(template)(
                project_patient=template.project_patient,
                event_id=uuid.uuid4(),
                occurred_at=template.occurred_at,
                client_session_id=video.client_session_id,
                video_id=video.pk,
                stage="upload",
                error_code="upload_network_failed",
                message="operation failed",
                network_type="unknown",
                platform="unknown",
                sdk_version="unknown",
                app_version="unknown",
            )
        )
    rows().bulk_create(copies)
    out = StringIO()
    call_command("training_upload_diagnostics", video_id=video.pk, stdout=out)
    assert len(json.loads(out.getvalue())) == 100
    out = StringIO()
    call_command(
        "training_upload_diagnostics", video_id=video.pk, client_session_id=uuid.uuid4(), stdout=out
    )
    assert json.loads(out.getvalue()) == []
    with pytest.raises(CommandError):
        call_command("training_upload_diagnostics", stdout=StringIO())
    with pytest.raises(CommandError):
        call_command("training_upload_diagnostics", video_id=video.pk, limit=101, stdout=StringIO())


def test_duplicate_event_does_not_renew_expired_received_time(authenticated, monkeypatch):
    data = payload()
    assert authenticated.post(URL, data, format="json").status_code == 200
    expired = timezone.now() - timedelta(days=15)
    rows().update(received_at=expired)
    assert authenticated.post(URL, data, format="json").status_code == 200
    assert rows().get().received_at == expired


def test_actual_body_limit_is_enforced_by_parser_without_content_length():
    from apps.patient_app.diagnostic_views import DiagnosticJSONParser, DiagnosticRequestTooLarge
    from io import BytesIO

    with pytest.raises(DiagnosticRequestTooLarge):
        DiagnosticJSONParser().parse(BytesIO(b" " * 4097))


@pytest.mark.parametrize("field", ["sdk_version", "app_version", "error_code"])
def test_phone_cannot_be_smuggled_in_metadata(field):
    from apps.patient_app.diagnostic_views import DiagnosticSerializer

    data = payload()
    data[field] = "13812345678" if field != "error_code" else "upload_13812345678"
    serializer = DiagnosticSerializer(data=data)
    assert not serializer.is_valid()
