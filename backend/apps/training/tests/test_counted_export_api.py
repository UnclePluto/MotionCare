import uuid
from io import BytesIO

import openpyxl
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.prescriptions.models import ActionLibraryItem
from apps.training.models import (
    MotionTrainingSession,
    MotionTrainingSet,
    MotionSetAttempt,
    TrainingVideo,
    TrainingRecord,
)


@pytest.mark.django_db(transaction=True)
def test_export_partial_motion_has_group_identity_and_no_fake_duration(
    doctor, project_patient, active_prescription
):
    item, _ = ActionLibraryItem.objects.get_or_create(
        source_key="motion-resistance-leg-kickback",
        defaults={
            "name": "腿部后踢",
            "internal_type": "motion",
            "training_type": "运动训练",
            "action_type": "抗阻训练",
        },
    )
    action = active_prescription.add_action_snapshot(
        item, dose_mode="sets", repetitions=10, sets=3, count_unit="per_side"
    )
    start = timezone.now() - timezone.timedelta(minutes=10)
    session = MotionTrainingSession.objects.create(
        project_patient=project_patient,
        prescription_action=action,
        client_session_id=uuid.uuid4(),
        planned_sets=3,
        repetitions=10,
        count_unit="per_side",
        started_at=start,
        training_date=timezone.localdate(start),
    )
    group = MotionTrainingSet.objects.create(
        session=session,
        index=1,
        completed=True,
        started_at=start,
        ended_at=start + timezone.timedelta(seconds=40),
    )
    attempt = MotionSetAttempt.objects.create(id=uuid.uuid4(), group=group)
    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=session.training_date,
        status="completed",
    )
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_record=record,
        motion_attempt=attempt,
        status="attached",
        training_started_at=start,
        training_ended_at=group.ended_at,
        expected_duration_seconds=1800,
        actual_duration_seconds=40,
    )
    group.video, group.attempt_id = video, attempt.id
    group.save()
    MotionTrainingSet.objects.create(
        session=session,
        index=2,
        completed=True,
        started_at=group.ended_at + timezone.timedelta(seconds=180),
        ended_at=group.ended_at + timezone.timedelta(seconds=220),
        attempt_id=uuid.uuid4(),
    )
    client = APIClient()
    client.force_authenticate(doctor)
    response = client.post(
        f"/api/training/tracking/patients/{project_patient.patient_id}/export/",
        {"project_patient": project_patient.id, "range": "all"},
        format="json",
    )
    assert response.status_code == 200
    book = openpyxl.load_workbook(BytesIO(b"".join(response.streaming_content)))
    response.close()
    values = list(book["运动明细"].values)
    row = dict(zip(values[0], values[1]))
    assert row["所属运动编号"] == session.id
    assert row["组序号"] == "1/3"
    assert row["每侧目标个数"] == 10
    assert row["所属运动状态"] == "部分完成"
    assert row["处方时长（秒）"] is None

    pending = dict(zip(values[0], values[2]))
    assert pending["组序号"] == "2/3"
    assert pending["录像编号"] is None
    assert pending["动作总次数"] is None
    assert pending["实际训练秒数"] == 40
    assert pending["录像处理状态"] == "待上传"
