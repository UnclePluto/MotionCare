from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.patient_app.services import bind_project_patient_with_code, create_binding_code
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient
from apps.training.models import TrainingVideo, TrainingVideoSegment

CLIENT_SESSION_ID = "8cf99c30-9b03-4bda-b4d3-b492f3a2db12"


@pytest.fixture(autouse=True)
def video_staging_settings(settings, tmp_path):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.TRAINING_VIDEO_MIN_FREE_BYTES = 0
    settings.FFMPEG_PATH = "/usr/bin/true"


def _auth_client(project_patient, doctor, *, wx_openid="openid-video"):
    code, _ = create_binding_code(project_patient=project_patient, created_by=doctor)
    token, _ = bind_project_patient_with_code(code, wx_openid=wx_openid)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _shoulder_press_action(active_prescription):
    item = ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press")
    return active_prescription.add_action_snapshot(
        item,
        weekly_frequency="2 次/周",
        weekly_target_count=2,
        duration_minutes=10,
    )


def _session_payload(action, **overrides):
    return {
        "client_session_id": CLIENT_SESSION_ID,
        "prescription_action": action.id,
        "training_date": "2026-07-11",
        "expected_duration_seconds": 180,
        **overrides,
    }


def _create_session(client, action):
    response = client.post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action),
        format="json",
    )
    assert response.status_code == 201, response.data
    return response


def _segment_url(video_id, index):
    return f"/api/patient-app/training-video-sessions/{video_id}/segments/{index}/"


def _segment_payload(content=b"video-bytes", *, duration_ms=30000, size_bytes=None):
    return {
        "file": SimpleUploadedFile(
            "../../client-name.mp4",
            content,
            content_type="video/mp4",
        ),
        "duration_ms": duration_ms,
        "size_bytes": len(content) if size_bytes is None else size_bytes,
    }


def _other_project_patient(project_patient, doctor):
    patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900001112",
        primary_doctor=doctor,
    )
    return ProjectPatient.objects.create(
        project=project_patient.project,
        patient=patient,
        group=project_patient.group,
    )


def _assert_no_partial_files(root: Path):
    assert list(root.rglob("*.part")) == []


@pytest.mark.django_db
def test_create_session_is_idempotent(project_patient, doctor, active_prescription):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    payload = _session_payload(action)

    first = client.post("/api/patient-app/training-video-sessions/", payload, format="json")
    second = client.post("/api/patient-app/training-video-sessions/", payload, format="json")

    assert first.status_code == 201, first.data
    assert second.status_code == 200, second.data
    assert first.data["video_id"] == second.data["video_id"]
    assert second.data["uploaded_segments"] == []
    video = TrainingVideo.objects.get(pk=first.data["video_id"])
    assert video.project_patient == project_patient
    assert video.prescription_action == action
    assert video.training_date.isoformat() == "2026-07-11"
    assert video.expected_duration_seconds == 180
    assert video.status == TrainingVideo.Status.RECORDING


@pytest.mark.django_db
@pytest.mark.parametrize("changed_prerequisite", ["ffmpeg", "disk", "prescription"])
def test_existing_session_recovers_before_mutable_prerequisite_checks(
    project_patient,
    doctor,
    active_prescription,
    settings,
    changed_prerequisite,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    payload = _session_payload(action)
    first = client.post("/api/patient-app/training-video-sessions/", payload, format="json")
    assert first.status_code == 201, first.data

    if changed_prerequisite == "ffmpeg":
        settings.FFMPEG_PATH = "/missing/ffmpeg"
    elif changed_prerequisite == "disk":
        settings.TRAINING_VIDEO_MIN_FREE_BYTES = 10**30
    else:
        active_prescription.status = Prescription.Status.ARCHIVED
        active_prescription.save(update_fields=["status", "updated_at"])

    recovered = client.post("/api/patient-app/training-video-sessions/", payload, format="json")

    assert recovered.status_code == 200, recovered.data
    assert recovered.data["video_id"] == first.data["video_id"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("payload_override", "expected_fragment"),
    [
        ({"prescription_action": 999999}, "动作"),
        ({"training_date": "2026-07-12"}, "日期"),
        ({"expected_duration_seconds": 181}, "时长"),
    ],
)
def test_existing_session_rejects_immutable_payload_conflict(
    project_patient,
    doctor,
    active_prescription,
    payload_override,
    expected_fragment,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    first = client.post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action),
        format="json",
    )
    assert first.status_code == 201, first.data

    conflict = client.post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action, **payload_override),
        format="json",
    )

    assert conflict.status_code == 409, conflict.data
    assert expected_fragment in str(conflict.data)


@pytest.mark.django_db
def test_create_session_rejects_non_shoulder_action(
    project_patient, doctor, active_prescription, prescription_action
):
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(prescription_action),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "肩部推举" in str(response.data)
    assert not TrainingVideo.objects.exists()


@pytest.mark.django_db
def test_create_session_rejects_unavailable_ffmpeg(
    project_patient, doctor, active_prescription, settings
):
    settings.FFMPEG_PATH = "/missing/ffmpeg"
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "FFmpeg" in str(response.data)
    assert not TrainingVideo.objects.exists()


@pytest.mark.django_db
def test_create_session_rejects_low_staging_disk_space(
    project_patient, doctor, active_prescription, settings
):
    settings.TRAINING_VIDEO_MIN_FREE_BYTES = 10**30
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "磁盘" in str(response.data)
    assert not TrainingVideo.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("expected_duration_seconds", "expected_status"),
    [(2, 201), (3, 400)],
)
def test_create_session_expected_duration_boundary(
    project_patient,
    doctor,
    active_prescription,
    settings,
    tmp_path,
    expected_duration_seconds,
    expected_status,
):
    settings.TRAINING_VIDEO_MAX_DURATION_SECONDS = 2
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(
            action,
            expected_duration_seconds=expected_duration_seconds,
        ),
        format="json",
    )

    assert response.status_code == expected_status, response.data
    assert TrainingVideo.objects.exists() is (expected_status == 201)
    assert list(tmp_path.rglob("*.mp4")) == []
    _assert_no_partial_files(tmp_path)


@pytest.mark.django_db
def test_upload_segment_streams_to_server_and_is_idempotent(
    project_patient, doctor, active_prescription, settings, tmp_path
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    url = _segment_url(session.data["video_id"], 0)

    first = client.post(url, _segment_payload())
    second = client.post(url, _segment_payload())

    assert first.status_code == 201, first.data
    assert second.status_code == 200, second.data
    assert first.data["sha256"] == second.data["sha256"]
    assert first.data["size_bytes"] == 11
    assert first.data["duration_ms"] == 30000
    assert first.data["uploaded_segment_count"] == 1
    path = tmp_path / "8cf99c309b034bdab4d3b492f3a2db12" / "segments" / "000000.mp4"
    assert path.read_bytes() == b"video-bytes"
    _assert_no_partial_files(tmp_path)
    segment = TrainingVideoSegment.objects.get()
    assert segment.relative_path == ("8cf99c309b034bdab4d3b492f3a2db12/segments/000000.mp4")
    assert segment.status == TrainingVideoSegment.Status.UPLOADED


@pytest.mark.django_db
def test_upload_segment_returns_conflict_for_reused_index_with_different_content(
    project_patient, doctor, active_prescription, tmp_path
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    url = _segment_url(session.data["video_id"], 0)
    first = client.post(url, _segment_payload(b"first-video"))

    conflict = client.post(url, _segment_payload(b"other-video"))

    assert first.status_code == 201, first.data
    assert conflict.status_code == 409, conflict.data
    assert "冲突" in str(conflict.data)
    path = tmp_path / CLIENT_SESSION_ID.replace("-", "") / "segments" / "000000.mp4"
    assert path.read_bytes() == b"first-video"
    assert TrainingVideoSegment.objects.count() == 1
    _assert_no_partial_files(tmp_path)


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["segment", "status"])
def test_training_video_session_is_hidden_from_another_patient(
    project_patient, doctor, active_prescription, endpoint
):
    action = _shoulder_press_action(active_prescription)
    owner_client = _auth_client(project_patient, doctor)
    session = _create_session(owner_client, action)
    other_project_patient = _other_project_patient(project_patient, doctor)
    other_client = _auth_client(
        other_project_patient,
        doctor,
        wx_openid=f"openid-other-{endpoint}",
    )
    if endpoint == "segment":
        response = other_client.post(
            _segment_url(session.data["video_id"], 0),
            _segment_payload(),
        )
    else:
        response = other_client.get(
            f"/api/patient-app/training-video-sessions/{session.data['video_id']}/status/"
        )

    assert response.status_code == 404, response.data


@pytest.mark.django_db
def test_upload_segment_rejects_actual_size_mismatch_without_file_residue(
    project_patient, doctor, active_prescription, tmp_path
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)

    response = client.post(
        _segment_url(session.data["video_id"], 0),
        _segment_payload(b"actual", size_bytes=99),
    )

    assert response.status_code == 400, response.data
    assert not TrainingVideoSegment.objects.exists()
    assert list(tmp_path.rglob("*.mp4")) == []
    _assert_no_partial_files(tmp_path)


@pytest.mark.django_db
def test_upload_segment_size_limit_leaves_no_partial_file(
    project_patient, doctor, active_prescription, settings, tmp_path
):
    settings.TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES = 5
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)

    response = client.post(
        _segment_url(session.data["video_id"], 0),
        _segment_payload(b"123456"),
    )

    assert response.status_code == 400, response.data
    assert not TrainingVideoSegment.objects.exists()
    assert list(tmp_path.rglob("*.mp4")) == []
    _assert_no_partial_files(tmp_path)


@pytest.mark.django_db
def test_upload_segment_total_size_limit_leaves_rejected_segment_no_residue(
    project_patient, doctor, active_prescription, settings, tmp_path
):
    settings.TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES = 10
    settings.TRAINING_VIDEO_MAX_SIZE_BYTES = 10
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    first = client.post(
        _segment_url(session.data["video_id"], 0),
        _segment_payload(b"123456", duration_ms=1000),
    )

    response = client.post(
        _segment_url(session.data["video_id"], 1),
        _segment_payload(b"abcdef", duration_ms=1000),
    )

    assert first.status_code == 201, first.data
    assert response.status_code == 400, response.data
    assert TrainingVideoSegment.objects.count() == 1
    session_root = tmp_path / CLIENT_SESSION_ID.replace("-", "") / "segments"
    assert (session_root / "000000.mp4").read_bytes() == b"123456"
    assert not (session_root / "000001.mp4").exists()
    _assert_no_partial_files(tmp_path)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("index", "expected_status"),
    [(1, 201), (2, 400)],
)
def test_upload_segment_index_boundary_leaves_no_rejected_file(
    project_patient,
    doctor,
    active_prescription,
    settings,
    tmp_path,
    index,
    expected_status,
):
    settings.TRAINING_VIDEO_MAX_SEGMENTS = 2
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)

    response = client.post(
        _segment_url(session.data["video_id"], index),
        _segment_payload(b"index-boundary", duration_ms=1000),
    )

    assert response.status_code == expected_status, response.data
    destination = tmp_path / CLIENT_SESSION_ID.replace("-", "") / "segments" / f"{index:06d}.mp4"
    assert destination.exists() is (expected_status == 201)
    _assert_no_partial_files(tmp_path)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("existing_count", "expected_status"),
    [(1, 201), (2, 400)],
)
def test_upload_segment_count_boundary_leaves_no_rejected_file(
    project_patient,
    doctor,
    active_prescription,
    settings,
    tmp_path,
    existing_count,
    expected_status,
):
    settings.TRAINING_VIDEO_MAX_SEGMENTS = 2
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    for offset in range(existing_count):
        TrainingVideoSegment.objects.create(
            training_video=video,
            index=10 + offset,
            duration_ms=100,
            size_bytes=1,
            sha256=f"existing-{offset}",
            relative_path=f"existing-{offset}.mp4",
            status=TrainingVideoSegment.Status.UPLOADED,
            uploaded_at=timezone.now(),
        )

    response = client.post(
        _segment_url(video.id, 0),
        _segment_payload(b"count-boundary", duration_ms=1000),
    )

    assert response.status_code == expected_status, response.data
    destination = tmp_path / CLIENT_SESSION_ID.replace("-", "") / "segments" / "000000.mp4"
    assert destination.exists() is (expected_status == 201)
    _assert_no_partial_files(tmp_path)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("new_duration_ms", "expected_status"),
    [(1000, 201), (1001, 400)],
)
def test_upload_segment_total_duration_boundary_leaves_no_rejected_file(
    project_patient,
    doctor,
    active_prescription,
    settings,
    tmp_path,
    new_duration_ms,
    expected_status,
):
    settings.TRAINING_VIDEO_MAX_DURATION_SECONDS = 2
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = client.post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action, expected_duration_seconds=2),
        format="json",
    )
    assert session.status_code == 201, session.data
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    TrainingVideoSegment.objects.create(
        training_video=video,
        index=1,
        duration_ms=1000,
        size_bytes=1,
        sha256="existing",
        relative_path="existing.mp4",
        status=TrainingVideoSegment.Status.UPLOADED,
        uploaded_at=timezone.now(),
    )

    response = client.post(
        _segment_url(video.id, 0),
        _segment_payload(b"duration-boundary", duration_ms=new_duration_ms),
    )

    assert response.status_code == expected_status, response.data
    destination = tmp_path / CLIENT_SESSION_ID.replace("-", "") / "segments" / "000000.mp4"
    assert destination.exists() is (expected_status == 201)
    _assert_no_partial_files(tmp_path)


@pytest.mark.django_db
def test_status_returns_real_uploaded_segment_indexes(project_patient, doctor, active_prescription):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    assert (
        client.post(
            _segment_url(session.data["video_id"], 2),
            _segment_payload(b"third"),
        ).status_code
        == 201
    )
    assert (
        client.post(
            _segment_url(session.data["video_id"], 0),
            _segment_payload(b"first"),
        ).status_code
        == 201
    )

    response = client.get(
        f"/api/patient-app/training-video-sessions/{session.data['video_id']}/status/"
    )

    assert response.status_code == 200, response.data
    assert response.data["video_id"] == session.data["video_id"]
    assert response.data["status"] == TrainingVideo.Status.UPLOADING_SEGMENTS
    assert response.data["uploaded_segments"] == [0, 2]
    assert response.data["uploaded_segment_count"] == 2
    assert "relative_path" not in response.data


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url", "payload"),
    [
        (
            "/api/patient-app/training-videos/upload-intent/",
            {
                "prescription_action": 1,
                "content_type": "video/mp4",
                "size_bytes": 1,
                "duration_seconds": 1,
            },
        ),
        (
            "/api/patient-app/training-videos/1/complete/",
            {
                "key": "legacy.mp4",
                "hash": "legacy-hash",
                "training_date": str(timezone.localdate()),
                "actual_duration_minutes": 1,
            },
        ),
    ],
)
def test_legacy_direct_upload_routes_are_removed(url, payload):
    response = APIClient().post(url, payload, format="json")

    assert response.status_code == 404
