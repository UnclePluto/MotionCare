import base64
import json
import uuid

import pytest
from django.utils import timezone

from apps.patient_app.tests.test_motion_sets_api import counted_client
from apps.training.models import TrainingVideo, VideoAssemblyJob, TrainingRecord

URL = "/api/patient-app/training-video-direct-uploads/"


@pytest.fixture
def direct_group(project_patient, active_prescription, settings):
    settings.QINIU_ACCESS_KEY = "test-ak"
    settings.QINIU_SECRET_KEY = "test-sk"
    settings.QINIU_BUCKET = "test-private"
    settings.QINIU_DIRECT_UPLOAD_URL = "https://upload.example.test"
    settings.QINIU_DIRECT_UPLOAD_TOKEN_TTL_SECONDS = 3600
    client, action = counted_client(project_patient, active_prescription)
    start = timezone.now() - timezone.timedelta(minutes=3)
    active_prescription.effective_at = start - timezone.timedelta(days=1)
    active_prescription.save()
    attempt = str(uuid.uuid4())
    result = client.post("/api/patient-app/motion-sessions/recover/", {
        "client_session_id": str(uuid.uuid4()), "prescription_action": action.id,
        "started_at": start.isoformat(), "completed_sets": [{
            "index": 1, "attempt_id": attempt, "started_at": start.isoformat(),
            "ended_at": (start + timezone.timedelta(seconds=120)).isoformat(),
            "completion_reason": "manual",
        }],
    }, format="json")
    assert result.status_code == 200, result.data
    return client, {
        "client_session_id": str(uuid.uuid4()), "motion_attempt_id": attempt,
        "size_bytes": 100 * 1024 * 1024, "duration_ms": 120000,
    }


@pytest.mark.django_db
def test_large_whole_video_gets_one_object_grant_without_assembly(direct_group):
    client, payload = direct_group
    response = client.post(URL, payload, format="json")
    assert response.status_code == 201, response.data
    video = TrainingVideo.objects.get(pk=response.data["video_id"])
    assert video.upload_mode == "direct"
    assert not VideoAssemblyJob.objects.filter(training_video=video).exists()
    policy = json.loads(base64.urlsafe_b64decode(response.data["upload_token"].split(":")[-1]))
    assert policy["scope"] == f"test-private:{video.object_key}"
    assert policy["insertOnly"] == 1
    assert policy["fsizeLimit"] == 104857600
    assert policy["mimeLimit"] == "video/mp4;video/quicktime"
    repeat = client.post(URL, payload, format="json")
    assert repeat.status_code == 200
    assert repeat.data["video_id"] == video.id
    assert TrainingVideo.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("field,value", [("size_bytes", 0), ("size_bytes", True), ("duration_ms", 300001), ("duration_ms", 1)])
def test_grant_rejects_invalid_or_conflicting_file_metadata(direct_group, field, value):
    client, payload = direct_group
    response = client.post(URL, {**payload, field: value}, format="json")
    assert response.status_code == 400
    assert not TrainingVideo.objects.exists()


@pytest.mark.django_db
def test_existing_upload_id_cannot_change_file_or_attempt(direct_group):
    client, payload = direct_group
    assert client.post(URL, payload, format="json").status_code == 201
    for change in ({"size_bytes": 1024}, {"motion_attempt_id": str(uuid.uuid4())}):
        assert client.post(URL, {**payload, **change}, format="json").status_code in {400, 404, 409}
    assert TrainingVideo.objects.count() == 1


@pytest.mark.django_db
def test_abandoned_attempt_cannot_get_upload_credentials(direct_group):
    from apps.training.set_models import MotionSetAttempt
    client, payload = direct_group
    MotionSetAttempt.objects.filter(pk=payload["motion_attempt_id"]).update(abandoned_at=timezone.now())
    assert client.post(URL, payload, format="json").status_code == 400
    assert not TrainingVideo.objects.exists()


@pytest.mark.django_db
def test_uncompleted_attempt_cannot_get_upload_credentials(direct_group):
    from apps.training.set_models import MotionSetAttempt
    client, payload = direct_group
    group = MotionSetAttempt.objects.get(pk=payload["motion_attempt_id"]).group
    group.completed = False
    group.save(update_fields=["completed"])
    assert client.post(URL, payload, format="json").status_code == 400
    assert not TrainingVideo.objects.exists()


@pytest.mark.django_db
def test_other_patient_cannot_get_upload_credentials(direct_group, project_patient):
    from apps.patient_app.authentication import PatientAppPrincipal
    from apps.patient_app.models import PatientAppSession
    from apps.patients.models import Patient
    from apps.studies.models import ProjectPatient
    client, payload = direct_group
    granted = client.post(URL, payload, format="json").data
    another_project_patient = ProjectPatient.objects.create(
        project=project_patient.project, group=project_patient.group,
        patient=Patient.objects.create(name="另一患者", phone="13912345678"),
    )
    client.force_authenticate(PatientAppPrincipal(PatientAppSession(
        project_patient=another_project_patient, patient=another_project_patient.patient,
    )))
    assert client.post(URL, payload, format="json").status_code == 404
    assert client.post(f"{URL}{granted['video_id']}/complete/", {}, format="json").status_code == 404


@pytest.mark.django_db
def test_direct_endpoint_requires_patient_authentication(direct_group):
    client, payload = direct_group
    client.force_authenticate(None)
    assert client.post(URL, payload, format="json").status_code in {401, 403}


@pytest.fixture
def uploaded_direct(direct_group, monkeypatch, settings):
    client, payload = direct_group
    response = client.post(URL, payload, format="json")
    assert response.status_code == 201, response.data
    video = TrainingVideo.objects.get(pk=response.data["video_id"])
    metadata = {"hash": "F" + "a" * 27, "fsize": payload["size_bytes"], "mimeType": "video/mp4"}
    media = {"format": {"duration": "120.1", "size": str(payload["size_bytes"])},
             "streams": [{"codec_type": "video", "codec_name": "h264", "width": 480, "height": 640}]}
    monkeypatch.setattr("apps.training.qiniu.stat_object_metadata_or_none", lambda **kw: metadata)
    monkeypatch.setattr("apps.training.qiniu.read_private_video_info", lambda key: media, raising=False)
    settings.PP_MCARE_AUTO_ENQUEUE_ENABLED = True
    return client, video, metadata, media


@pytest.mark.django_db
def test_direct_completion_checks_cloud_then_attaches_and_counts_once(uploaded_direct):
    from apps.training.models import MotionAnalysisJob
    client, video, _, _ = uploaded_direct
    for _ in range(2):
        response = client.post(f"{URL}{video.id}/complete/", {}, format="json")
        assert response.status_code == 200, response.data
        assert response.data["status"] == "attached"
    video.refresh_from_db()
    assert video.training_record_id is not None
    assert TrainingRecord.objects.filter(video=video).count() == 1
    assert MotionAnalysisJob.objects.filter(training_video=video).count() == 1
    assert not VideoAssemblyJob.objects.filter(training_video=video).exists()
    assert video.motion_attempt.group.video_id == video.id
    assert video.motion_attempt.group.session.completed_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize("case", ["missing", "size", "mime", "hash", "duration", "nan", "stream", "length"])
def test_unverified_cloud_video_cannot_be_attached(uploaded_direct, monkeypatch, case):
    client, video, metadata, media = uploaded_direct
    if case == "missing":
        monkeypatch.setattr("apps.training.qiniu.stat_object_metadata_or_none", lambda **kw: None)
    if case == "size":
        metadata["fsize"] = 5
    if case == "mime":
        metadata["mimeType"] = "text/plain"
    if case == "hash":
        metadata["hash"] = "invalid"
    if case == "duration":
        media["format"]["duration"] = "310"
    if case == "nan":
        media["format"]["duration"] = "NaN"
    if case == "stream":
        media["streams"] = []
    if case == "length":
        media["format"]["duration"] = "30"
    response = client.post(f"{URL}{video.id}/complete/", {}, format="json")
    assert response.status_code == (200 if case == "missing" else 400), response.data
    assert response.data.get("status") != "attached"
    assert not TrainingRecord.objects.exists()


@pytest.mark.django_db
def test_unbind_during_remote_verification_cannot_publish(uploaded_direct, monkeypatch):
    client, video, metadata, _ = uploaded_direct
    def remote(**kwargs):
        TrainingVideo.objects.filter(pk=video.id).update(project_patient=None, cleanup_requested_at=timezone.now())
        return metadata
    monkeypatch.setattr("apps.training.qiniu.stat_object_metadata_or_none", remote)
    assert client.post(f"{URL}{video.id}/complete/", {}, format="json").status_code == 404
    assert not TrainingRecord.objects.exists()


@pytest.mark.django_db
def test_direct_upload_cannot_use_legacy_segment_finalize(uploaded_direct):
    client, video, _, _ = uploaded_direct
    response = client.post(f"/api/patient-app/training-video-sessions/{video.id}/finalize/", {
        "segment_count": 1, "actual_duration_seconds": 120,
        "training_ended_at": video.training_ended_at.isoformat(),
    }, format="json")
    assert response.status_code == 400
    assert not VideoAssemblyJob.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["expired", "failed"])
def test_expired_direct_file_can_receive_fresh_object_grant(direct_group, monkeypatch, status):
    client, payload = direct_group
    first = client.post(URL, payload, format="json").data
    TrainingVideo.objects.filter(pk=first["video_id"]).update(status=status)
    monkeypatch.setattr("apps.training.qiniu.stat_object_metadata_or_none", lambda **kw: pytest.fail("失效对象不应核验绑定"))
    response = client.post(f"{URL}{first['video_id']}/complete/", {}, format="json")
    assert response.status_code == 200
    assert response.data["status"] == status
    second = client.post(URL, {**payload, "client_session_id": str(uuid.uuid4())}, format="json")
    assert second.status_code == 201
    assert second.data["object_key"] != first["object_key"]
    assert TrainingRecord.objects.count() == 0


@pytest.mark.django_db
def test_time_limit_completion_is_preserved_and_conflicting_recovery_rejected(direct_group):
    from apps.training.set_models import MotionSetAttempt
    client, payload = direct_group
    original = MotionSetAttempt.objects.get(pk=payload["motion_attempt_id"])
    start = timezone.now() - timezone.timedelta(minutes=6)
    body = {"client_session_id": str(uuid.uuid4()),
            "prescription_action": original.group.session.prescription_action_id,
            "started_at": start.isoformat(), "completed_sets": [{
                "index": 1, "attempt_id": str(uuid.uuid4()), "started_at": start.isoformat(),
                "ended_at": (start + timezone.timedelta(seconds=300)).isoformat(),
                "completion_reason": "time_limit",
            }]}
    path = "/api/patient-app/motion-sessions/recover/"
    response = client.post(path, body, format="json")
    assert response.status_code == 200, response.data
    assert response.data["sets"][0]["completion_reason"] == "time_limit"
    body["completed_sets"][0]["completion_reason"] = "manual"
    assert client.post(path, body, format="json").status_code == 400


@pytest.mark.django_db
def test_unbound_direct_cleanup_waits_out_upload_grant_and_never_needs_staging(uploaded_direct, monkeypatch):
    from apps.training.models import QiniuCleanupTombstone
    from apps.training.video_tasks import cleanup_unbound_training_video, cleanup_qiniu_tombstone
    _, video, _, _ = uploaded_direct
    TrainingVideo.objects.filter(pk=video.id).update(project_patient=None, cleanup_requested_at=timezone.now())
    monkeypatch.setattr("apps.training.video_tasks._remove_session_files", lambda v: pytest.fail("直传不应访问分片目录"))
    monkeypatch.setattr(cleanup_qiniu_tombstone, "delay", lambda *a: None)
    assert cleanup_unbound_training_video(video.id) is True
    tombstone = QiniuCleanupTombstone.objects.get(session_id=video.client_session_id)
    assert tombstone.canonical_key == video.object_key
    assert tombstone.next_check_at >= video.direct_upload_expires_at + timezone.timedelta(seconds=300)
    monkeypatch.setattr("apps.training.video_tasks.stat_object_metadata_or_none", lambda **kw: pytest.fail("凭证到期前不能完成清理"))
    assert cleanup_qiniu_tombstone(tombstone.id) is False
