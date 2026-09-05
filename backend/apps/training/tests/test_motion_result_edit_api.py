import uuid

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.training.models import (
    MotionAnalysisJob,
    MotionResultSource,
    TrainingRecord,
    TrainingVideo,
)


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def _record(project_patient, active_prescription, prescription_action):
    return TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
    )


def _job(record, *, status):
    video = TrainingVideo.objects.create(
        project_patient=record.project_patient,
        prescription=record.prescription,
        prescription_action=record.prescription_action,
        training_record=record,
        bucket="motioncare-training",
        object_key=f"training-videos/{record.id}/{uuid.uuid4()}.mp4",
        object_hash="original-hash",
        content_type="video/mp4",
        size_bytes=1024,
        duration_seconds=120,
        status=TrainingVideo.Status.ATTACHED,
    )
    return MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=record,
        project_patient=record.project_patient,
        prescription_action=record.prescription_action,
        status=status,
        total_count=8 if status == MotionAnalysisJob.Status.SUCCEEDED else None,
        standard_count=6 if status == MotionAnalysisJob.Status.SUCCEEDED else None,
        nonstandard_count=2 if status == MotionAnalysisJob.Status.SUCCEEDED else None,
        result_payload={"private_diagnostic": "原始算法证据"},
    )


def _url(record):
    return f"/api/training/{record.id}/motion-result/"


@pytest.mark.django_db
def test_doctor_overwrites_algorithm_fields_on_same_training_record(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    record = _record(project_patient, active_prescription, prescription_action)
    job = _job(record, status=MotionAnalysisJob.Status.SUCCEEDED)
    record.motion_total_count = 8
    record.motion_standard_count = 6
    record.motion_nonstandard_count = 2
    record.motion_quality_data = {"algorithm_confidence": 0.92}
    record.motion_result_source = MotionResultSource.ALGORITHM
    record.save()
    original_job_payload = dict(job.result_payload)

    response = _client(doctor).patch(
        _url(record),
        {
            "total_count": 90,
            "standard_count": 85,
            "nonstandard_count": 5,
            "quality_note": "人工复核",
        },
        format="json",
    )

    record.refresh_from_db()
    job.refresh_from_db()
    assert response.status_code == 200, response.data
    assert (
        record.motion_total_count,
        record.motion_standard_count,
        record.motion_nonstandard_count,
    ) == (90, 85, 5)
    assert record.motion_quality_data == {"doctor_note": "人工复核"}
    assert record.motion_result_source == MotionResultSource.DOCTOR
    assert record.motion_result_updated_by == doctor
    assert record.motion_result_updated_at is not None
    assert response.data["motion_result_source"] == MotionResultSource.DOCTOR
    assert "private_diagnostic" not in str(response.data)
    assert job.result_payload == original_job_payload
    assert (job.total_count, job.standard_count, job.nonstandard_count) == (8, 6, 2)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "analysis_status",
    [MotionAnalysisJob.Status.PENDING, MotionAnalysisJob.Status.RUNNING],
)
def test_doctor_cannot_edit_while_analysis_is_active(
    analysis_status,
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    record = _record(project_patient, active_prescription, prescription_action)
    _job(record, status=analysis_status)

    response = _client(doctor).patch(
        _url(record),
        {
            "total_count": 10,
            "standard_count": 8,
            "nonstandard_count": 2,
            "quality_note": "等待算法完成",
        },
        format="json",
    )

    record.refresh_from_db()
    assert response.status_code == 409
    assert response.data == {"detail": "动作分析完成前暂不可修改"}
    assert record.motion_total_count is None
    assert record.motion_result_source == ""


@pytest.mark.django_db
@pytest.mark.parametrize("with_failed_job", [False, True])
def test_doctor_can_fill_results_for_unsupported_or_failed_analysis(
    with_failed_job,
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    record = _record(project_patient, active_prescription, prescription_action)
    if with_failed_job:
        _job(record, status=MotionAnalysisJob.Status.FAILED)

    response = _client(doctor).patch(
        _url(record),
        {
            "total_count": 12,
            "standard_count": 9,
            "nonstandard_count": 3,
            "quality_note": "医生填写",
        },
        format="json",
    )

    record.refresh_from_db()
    assert response.status_code == 200, response.data
    assert record.motion_total_count == 12
    assert record.motion_result_source == MotionResultSource.DOCTOR


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("total_count", True),
        ("total_count", "10"),
        ("total_count", 10.0),
        ("total_count", -1),
        ("standard_count", 2_147_483_648),
    ],
)
def test_motion_result_edit_rejects_non_integer_or_out_of_range_counts(
    field,
    value,
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    record = _record(project_patient, active_prescription, prescription_action)
    payload = {
        "total_count": 10,
        "standard_count": 8,
        "nonstandard_count": 2,
        "quality_note": "人工复核",
    }
    payload[field] = value

    response = _client(doctor).patch(_url(record), payload, format="json")

    record.refresh_from_db()
    assert response.status_code == 400
    assert record.motion_total_count is None


@pytest.mark.django_db
def test_motion_result_edit_rejects_inconsistent_counts_and_unknown_fields(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    record = _record(project_patient, active_prescription, prescription_action)

    inconsistent = _client(doctor).patch(
        _url(record),
        {
            "total_count": 10,
            "standard_count": 8,
            "nonstandard_count": 1,
            "quality_note": "人工复核",
        },
        format="json",
    )
    unknown = _client(doctor).patch(
        _url(record),
        {
            "total_count": 10,
            "standard_count": 8,
            "nonstandard_count": 2,
            "quality_note": "人工复核",
            "motion_result_source": "algorithm",
        },
        format="json",
    )

    assert inconsistent.status_code == 400
    assert unknown.status_code == 400


@pytest.mark.django_db
def test_motion_result_quality_note_has_a_bounded_length(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    accepted = _record(project_patient, active_prescription, prescription_action)
    rejected = _record(project_patient, active_prescription, prescription_action)
    wrong_type = _record(project_patient, active_prescription, prescription_action)
    counts = {"total_count": 0, "standard_count": 0, "nonstandard_count": 0}

    accepted_response = _client(doctor).patch(
        _url(accepted),
        {**counts, "quality_note": "复" * 2000},
        format="json",
    )
    rejected_response = _client(doctor).patch(
        _url(rejected),
        {**counts, "quality_note": "复" * 2001},
        format="json",
    )
    wrong_type_response = _client(doctor).patch(
        _url(wrong_type),
        {**counts, "quality_note": 123},
        format="json",
    )

    assert accepted_response.status_code == 200, accepted_response.data
    assert rejected_response.status_code == 400
    assert wrong_type_response.status_code == 400


@pytest.mark.django_db
@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=True)
def test_motion_result_edit_requires_row_level_access(
    project_patient,
    active_prescription,
    prescription_action,
):
    record = _record(project_patient, active_prescription, prescription_action)
    unrelated_doctor = User.objects.create_user(
        phone="13800009998",
        password="pass123456",
        name="无权限医生",
        role=User.Role.DOCTOR,
    )

    response = _client(unrelated_doctor).patch(
        _url(record),
        {
            "total_count": 10,
            "standard_count": 8,
            "nonstandard_count": 2,
            "quality_note": "越权修改",
        },
        format="json",
    )

    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=True)
def test_training_record_list_and_retrieve_apply_row_level_scope(
    doctor,
    project_patient,
    active_prescription,
    prescription_action,
):
    record = _record(project_patient, active_prescription, prescription_action)
    unrelated_doctor = User.objects.create_user(
        phone="13800009996",
        password="pass123456",
        name="无权限医生",
        role=User.Role.DOCTOR,
    )

    owner_list = _client(doctor).get("/api/training/")
    owner_retrieve = _client(doctor).get(f"/api/training/{record.id}/")
    unrelated_list = _client(unrelated_doctor).get("/api/training/")
    unrelated_retrieve = _client(unrelated_doctor).get(f"/api/training/{record.id}/")

    assert owner_list.status_code == 200
    assert [item["id"] for item in owner_list.data] == [record.id]
    assert owner_retrieve.status_code == 200
    assert owner_retrieve.data["id"] == record.id
    assert unrelated_list.status_code == 200
    assert unrelated_list.data == []
    assert unrelated_retrieve.status_code == 404


@pytest.mark.django_db
@override_settings(TRAINING_HEALTH_ENFORCE_ROW_SCOPE=False)
def test_training_record_reads_keep_global_compatibility_when_row_scope_is_disabled(
    project_patient,
    active_prescription,
    prescription_action,
):
    record = _record(project_patient, active_prescription, prescription_action)
    unrelated_doctor = User.objects.create_user(
        phone="13800009995",
        password="pass123456",
        name="兼容模式医生",
        role=User.Role.DOCTOR,
    )
    client = _client(unrelated_doctor)

    list_response = client.get("/api/training/")
    retrieve_response = client.get(f"/api/training/{record.id}/")

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.data] == [record.id]
    assert retrieve_response.status_code == 200
    assert retrieve_response.data["id"] == record.id
