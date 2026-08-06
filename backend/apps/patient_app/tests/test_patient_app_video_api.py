from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.patient_app.services import bind_project_patient_with_code, create_binding_code
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient
from apps.training.models import TrainingVideo, TrainingVideoSegment, VideoAssemblyJob
from apps.training.video_staging import segment_path

CLIENT_SESSION_ID = "8cf99c30-9b03-4bda-b4d3-b492f3a2db12"


@pytest.fixture(autouse=True)
def video_staging_settings(settings, tmp_path):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    settings.TRAINING_VIDEO_MIN_FREE_BYTES = 0
    settings.FFMPEG_PATH = "/usr/bin/true"
    settings.FFPROBE_PATH = "/usr/bin/true"


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
        "training_started_at": "2026-07-11T09:32:14+08:00",
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


def _staged_segment_path(root: Path, video_id, index):
    return (
        root
        / f"{video_id}-{CLIENT_SESSION_ID.replace('-', '')}"
        / "segments"
        / f"{index:06d}.mp4"
    )


def _staged_relative_path(video_id, index):
    return f"{video_id}-{CLIENT_SESSION_ID.replace('-', '')}/segments/{index:06d}.mp4"


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


def _create_uploaded_segments(video, root, durations_ms):
    for index, duration_ms in enumerate(durations_ms):
        path = segment_path(video, index)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"segment")
        TrainingVideoSegment.objects.create(
            training_video=video,
            index=index,
            duration_ms=duration_ms,
            size_bytes=7,
            sha256="a" * 64,
            relative_path=path.relative_to(root).as_posix(),
            status=TrainingVideoSegment.Status.UPLOADED,
            uploaded_at=timezone.now(),
        )


def _finalize_url(video):
    return f"/api/patient-app/training-video-sessions/{video.id}/finalize/"


def _finalize_payload(**overrides):
    return {
        "segment_count": 1,
        "actual_duration_seconds": 60,
        "note": "",
        "training_ended_at": "2026-07-11T09:41:27+08:00",
        **overrides,
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
def test_create_session_saves_client_training_started_at(
    project_patient, doctor, active_prescription
):
    action = _shoulder_press_action(active_prescription)
    response = _create_session(_auth_client(project_patient, doctor), action)
    video = TrainingVideo.objects.get(pk=response.data["video_id"])

    assert video.training_started_at == datetime(2026, 7, 11, 1, 32, 14, tzinfo=UTC)


@pytest.mark.django_db
def test_create_session_rejects_training_started_at_without_offset(
    project_patient, doctor, active_prescription
):
    action = _shoulder_press_action(active_prescription)
    response = _auth_client(project_patient, doctor).post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action, training_started_at="2026-07-11T09:32:14"),
        format="json",
    )

    assert response.status_code == 400
    assert "时区" in str(response.data)


@pytest.mark.django_db
def test_create_session_rejects_start_date_mismatch(
    project_patient, doctor, active_prescription
):
    action = _shoulder_press_action(active_prescription)
    response = _auth_client(project_patient, doctor).post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action, training_date="2026-07-12"),
        format="json",
    )

    assert response.status_code == 400
    assert "训练日期" in str(response.data)


@pytest.mark.django_db
def test_create_session_start_time_is_idempotent_and_immutable(
    project_patient, doctor, active_prescription
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    payload = _session_payload(action)

    first = client.post("/api/patient-app/training-video-sessions/", payload, format="json")
    same = client.post("/api/patient-app/training-video-sessions/", payload, format="json")
    changed = client.post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action, training_started_at="2026-07-11T09:32:15+08:00"),
        format="json",
    )

    assert first.status_code == 201
    assert same.status_code == 200
    assert changed.status_code == 409
    video = TrainingVideo.objects.get(pk=first.data["video_id"])
    assert video.training_started_at == datetime(2026, 7, 11, 1, 32, 14, tzinfo=UTC)


@pytest.mark.django_db
def test_legacy_client_can_create_session_without_start_time(
    project_patient, doctor, active_prescription
):
    action = _shoulder_press_action(active_prescription)
    payload = _session_payload(action)
    payload.pop("training_started_at")

    response = _auth_client(project_patient, doctor).post(
        "/api/patient-app/training-video-sessions/",
        payload,
        format="json",
    )

    assert response.status_code == 201
    assert TrainingVideo.objects.get(pk=response.data["video_id"]).training_started_at is None


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
        (
            {
                "training_date": "2026-07-12",
                "training_started_at": "2026-07-12T09:32:14+08:00",
            },
            "日期",
        ),
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
def test_create_session_rejects_unavailable_ffprobe(
    project_patient, doctor, active_prescription, settings
):
    settings.FFPROBE_PATH = "/missing/ffprobe"
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)

    response = client.post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action),
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "FFprobe" in str(response.data)
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
    path = _staged_segment_path(tmp_path, session.data["video_id"], 0)
    assert path.read_bytes() == b"video-bytes"
    _assert_no_partial_files(tmp_path)
    segment = TrainingVideoSegment.objects.get()
    assert segment.relative_path == _staged_relative_path(session.data["video_id"], 0)
    assert segment.status == TrainingVideoSegment.Status.UPLOADED


@pytest.mark.django_db
def test_same_client_session_id_isolated_between_patients(
    project_patient, doctor, active_prescription, tmp_path
):
    first_action = _shoulder_press_action(active_prescription)
    first_client = _auth_client(project_patient, doctor)
    first_session = _create_session(first_client, first_action)

    other_project_patient = _other_project_patient(project_patient, doctor)
    other_prescription = Prescription.objects.create(
        project_patient=other_project_patient,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    second_action = _shoulder_press_action(other_prescription)
    second_client = _auth_client(
        other_project_patient,
        doctor,
        wx_openid="openid-same-session-id",
    )
    second_session = _create_session(second_client, second_action)

    first_upload = first_client.post(
        _segment_url(first_session.data["video_id"], 0),
        _segment_payload(b"first-patient-video"),
    )
    second_upload = second_client.post(
        _segment_url(second_session.data["video_id"], 0),
        _segment_payload(b"second-patient-video"),
    )

    assert first_upload.status_code == 201, first_upload.data
    assert second_upload.status_code == 201, second_upload.data
    first_video = TrainingVideo.objects.get(pk=first_session.data["video_id"])
    second_video = TrainingVideo.objects.get(pk=second_session.data["video_id"])
    first_path = _staged_segment_path(tmp_path, first_video.pk, 0)
    second_path = _staged_segment_path(tmp_path, second_video.pk, 0)

    assert first_path != second_path
    assert first_path.read_bytes() == b"first-patient-video"
    assert second_path.read_bytes() == b"second-patient-video"
    assert (first_path.parents[1] / "locks" / "000000.lock").exists()
    assert (second_path.parents[1] / "locks" / "000000.lock").exists()
    assert TrainingVideoSegment.objects.get(training_video=first_video).relative_path == (
        _staged_relative_path(first_video.pk, 0)
    )
    assert TrainingVideoSegment.objects.get(training_video=second_video).relative_path == (
        _staged_relative_path(second_video.pk, 0)
    )


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
    path = _staged_segment_path(tmp_path, session.data["video_id"], 0)
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
def test_upload_segment_allows_total_size_above_legacy_limit(
    project_patient, doctor, active_prescription, settings, tmp_path
):
    settings.TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES = 10
    if hasattr(settings, "TRAINING_VIDEO_MAX_SIZE_BYTES"):
        del settings.TRAINING_VIDEO_MAX_SIZE_BYTES
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
    assert response.status_code == 201, response.data
    assert TrainingVideoSegment.objects.count() == 2
    session_root = _staged_segment_path(tmp_path, session.data["video_id"], 0).parent
    assert (session_root / "000000.mp4").read_bytes() == b"123456"
    assert (session_root / "000001.mp4").read_bytes() == b"abcdef"
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
    destination = _staged_segment_path(tmp_path, session.data["video_id"], index)
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
    destination = _staged_segment_path(tmp_path, video.id, 0)
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
    destination = _staged_segment_path(tmp_path, video.id, 0)
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
def test_finalize_requires_contiguous_segments_and_enqueues_once(
    project_patient,
    doctor,
    active_prescription,
    tmp_path,
    settings,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate(),
        expected_duration_seconds=60,
        status=TrainingVideo.Status.UPLOADING_SEGMENTS,
    )
    _create_uploaded_segments(video, tmp_path, [30000, 30000])
    delay = Mock()
    monkeypatch.setattr("apps.training.video_tasks.run_video_assembly_job.delay", delay)
    payload = {"segment_count": 2, "actual_duration_seconds": 60, "note": ""}

    with django_capture_on_commit_callbacks(execute=True):
        first = client.post(_finalize_url(video), payload, format="json")
        second = client.post(_finalize_url(video), payload, format="json")

    assert first.status_code == 202, first.data
    assert second.status_code == 200, second.data
    assert first.data["assembly_job_id"] == second.data["assembly_job_id"]
    assert delay.call_count == 1
    video.refresh_from_db()
    assert video.status == TrainingVideo.Status.QUEUED
    assert video.expected_segment_count == 2
    assert video.actual_duration_seconds == 60
    assert video.finalized_at is not None
    assert VideoAssemblyJob.objects.filter(training_video=video).count() == 1


@pytest.mark.django_db
def test_finalize_saves_client_training_ended_at(
    project_patient, doctor, active_prescription, tmp_path
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    _create_uploaded_segments(video, tmp_path, [60_000])

    response = client.post(_finalize_url(video), _finalize_payload(), format="json")
    video.refresh_from_db()
    assert response.status_code == 202
    assert video.training_ended_at == datetime(2026, 7, 11, 1, 41, 27, tzinfo=UTC)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("ended_at", "expected_fragment"),
    [
        ("2026-07-11T09:32:14+08:00", "晚于"),
        ("2026-07-12T09:32:15+08:00", "24 小时"),
        ("2026-07-11T09:32:30", "时区"),
    ],
)
def test_finalize_rejects_invalid_training_window(
    project_patient,
    doctor,
    active_prescription,
    tmp_path,
    ended_at,
    expected_fragment,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    _create_uploaded_segments(video, tmp_path, [60_000])

    response = client.post(
        _finalize_url(video),
        _finalize_payload(training_ended_at=ended_at),
        format="json",
    )

    assert response.status_code == 400
    assert expected_fragment in str(response.data)


@pytest.mark.django_db
def test_finalize_rejects_video_duration_longer_than_wall_time(
    project_patient, doctor, active_prescription, tmp_path
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    _create_uploaded_segments(video, tmp_path, [60_000])

    response = client.post(
        _finalize_url(video),
        _finalize_payload(training_ended_at="2026-07-11T09:32:44+08:00"),
        format="json",
    )

    assert response.status_code == 400
    assert "录像时长" in str(response.data)


@pytest.mark.django_db
def test_finalize_end_time_is_idempotent_and_immutable(
    project_patient,
    doctor,
    active_prescription,
    tmp_path,
    django_capture_on_commit_callbacks,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    _create_uploaded_segments(video, tmp_path, [60_000])

    with django_capture_on_commit_callbacks(execute=False):
        first = client.post(_finalize_url(video), _finalize_payload(), format="json")
    same = client.post(_finalize_url(video), _finalize_payload(), format="json")
    changed = client.post(
        _finalize_url(video),
        _finalize_payload(training_ended_at="2026-07-11T09:41:28+08:00"),
        format="json",
    )

    assert first.status_code == 202
    assert same.status_code == 200
    assert changed.status_code == 409


@pytest.mark.django_db
def test_legacy_session_without_training_window_still_finalizes(
    project_patient, doctor, active_prescription, tmp_path
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    create_payload = _session_payload(action)
    create_payload.pop("training_started_at")
    session = client.post(
        "/api/patient-app/training-video-sessions/",
        create_payload,
        format="json",
    )
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    _create_uploaded_segments(video, tmp_path, [60_000])
    finalize_payload = _finalize_payload()
    finalize_payload.pop("training_ended_at")

    response = client.post(_finalize_url(video), finalize_payload, format="json")

    assert response.status_code == 202
    video.refresh_from_db()
    assert video.training_started_at is None
    assert video.training_ended_at is None


@pytest.mark.django_db
def test_finalize_allows_total_size_above_legacy_limit(
    project_patient,
    doctor,
    active_prescription,
    tmp_path,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate(),
        expected_duration_seconds=60,
        status=TrainingVideo.Status.UPLOADING_SEGMENTS,
    )
    _create_uploaded_segments(video, tmp_path, [30000, 30000])
    TrainingVideoSegment.objects.filter(training_video=video, index=0).update(
        size_bytes=200 * 1024 * 1024
    )
    TrainingVideoSegment.objects.filter(training_video=video, index=1).update(
        size_bytes=1
    )
    delay = Mock()
    monkeypatch.setattr("apps.training.video_tasks.run_video_assembly_job.delay", delay)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            _finalize_url(video),
            {"segment_count": 2, "actual_duration_seconds": 60, "note": ""},
            format="json",
        )

    assert response.status_code == 202, response.data
    assert delay.call_count == 1
    assert VideoAssemblyJob.objects.filter(training_video=video).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("indexes", "durations_ms", "payload", "expected_fragment"),
    [
        ([0, 2], [30000, 30000], {"segment_count": 3, "actual_duration_seconds": 60}, "连续"),
        ([0, 1], [30000, 30000], {"segment_count": 2, "actual_duration_seconds": 55}, "时长"),
    ],
)
def test_finalize_rejects_missing_index_and_duration_mismatch(
    project_patient,
    doctor,
    active_prescription,
    tmp_path,
    indexes,
    durations_ms,
    payload,
    expected_fragment,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate(),
        expected_duration_seconds=60,
        status=TrainingVideo.Status.UPLOADING_SEGMENTS,
    )
    for index, duration_ms in zip(indexes, durations_ms, strict=True):
        path = segment_path(video, index)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"segment")
        TrainingVideoSegment.objects.create(
            training_video=video,
            index=index,
            duration_ms=duration_ms,
            size_bytes=7,
            sha256="a" * 64,
            relative_path=path.relative_to(tmp_path).as_posix(),
            status=TrainingVideoSegment.Status.UPLOADED,
        )

    response = client.post(_finalize_url(video), payload, format="json")

    assert response.status_code == 400
    assert expected_fragment in response.content.decode()
    assert not VideoAssemblyJob.objects.exists()


@pytest.mark.django_db
def test_finalize_rejects_more_than_configured_120_segments(
    project_patient, doctor, active_prescription, settings
):
    settings.TRAINING_VIDEO_MAX_SEGMENTS = 120
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate(),
        expected_duration_seconds=60,
        status=TrainingVideo.Status.UPLOADING_SEGMENTS,
    )

    response = client.post(
        _finalize_url(video),
        {"segment_count": 121, "actual_duration_seconds": 60, "note": ""},
        format="json",
    )

    assert response.status_code == 400
    assert "分段" in response.content.decode()
    assert not VideoAssemblyJob.objects.exists()


@pytest.mark.django_db
def test_finalize_rejects_conflicting_repeated_payload(
    project_patient,
    doctor,
    active_prescription,
    tmp_path,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate(),
        expected_duration_seconds=60,
        status=TrainingVideo.Status.UPLOADING_SEGMENTS,
    )
    _create_uploaded_segments(video, tmp_path, [60000])
    monkeypatch.setattr(
        "apps.training.video_tasks.run_video_assembly_job.delay", Mock()
    )
    with django_capture_on_commit_callbacks(execute=True):
        first = client.post(
            _finalize_url(video),
            {"segment_count": 1, "actual_duration_seconds": 60, "note": "first"},
            format="json",
        )

    conflict = client.post(
        _finalize_url(video),
        {"segment_count": 1, "actual_duration_seconds": 59, "note": "first"},
        format="json",
    )

    assert first.status_code == 202, first.data
    assert conflict.status_code == 409, conflict.data
    assert VideoAssemblyJob.objects.count() == 1


@pytest.mark.django_db
def test_finalize_rejects_after_project_patient_unbind(
    project_patient,
    doctor,
    active_prescription,
    tmp_path,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate(),
        expected_duration_seconds=60,
        status=TrainingVideo.Status.UPLOADING_SEGMENTS,
    )
    _create_uploaded_segments(video, tmp_path, [60000])
    url = _finalize_url(video)
    project_patient.delete()

    response = client.post(
        url,
        {"segment_count": 1, "actual_duration_seconds": 60, "note": ""},
        format="json",
    )

    assert response.status_code in {401, 403, 404}
    assert not VideoAssemblyJob.objects.exists()


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
