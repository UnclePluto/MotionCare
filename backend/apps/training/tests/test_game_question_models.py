import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.training.models import GameQuestionResult, TrainingRecord


@pytest.fixture
def training_record(project_patient, active_prescription, prescription_action):
    return TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
    )


def _question(training_record, **overrides):
    values = {
        "training_record": training_record,
        "question_index": 1,
        "game_code": "game-executive-inhibition",
        "difficulty": "中等",
        "response_duration_ms": 2380,
        "is_correct": True,
        "result_type": GameQuestionResult.ResultType.ANSWERED,
        "capture_version": GameQuestionResult.CaptureVersion.ACTIVE_RESPONSE_V1,
    }
    values.update(overrides)
    return GameQuestionResult.objects.create(**values)


@pytest.mark.django_db
def test_game_question_result_persists_core_metrics(training_record):
    question = _question(training_record)

    persisted = training_record.question_results.get()
    assert persisted.pk == question.pk
    assert persisted.question_index == 1
    assert persisted.game_code == "game-executive-inhibition"
    assert persisted.difficulty == "中等"
    assert persisted.response_duration_ms == 2380
    assert persisted.is_correct is True
    assert persisted.result_type == "answered"
    assert persisted.swap_count is None
    assert persisted.capture_version == "active_response_v1"


@pytest.mark.django_db
def test_training_record_persists_client_idempotency_fields(training_record):
    session_id = uuid.uuid4()
    training_record.client_session_id = session_id
    training_record.client_payload_fingerprint = "a" * 64
    training_record.save(
        update_fields=["client_session_id", "client_payload_fingerprint"]
    )

    persisted = TrainingRecord.objects.get(pk=training_record.pk)
    assert persisted.client_session_id == session_id
    assert persisted.client_payload_fingerprint == "a" * 64


@pytest.mark.django_db
def test_training_client_session_id_is_unique(
    training_record, project_patient, active_prescription, prescription_action
):
    session_id = uuid.uuid4()
    training_record.client_session_id = session_id
    training_record.save(update_fields=["client_session_id"])
    second = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        status=TrainingRecord.Status.COMPLETED,
    )
    second.client_session_id = session_id

    with pytest.raises(IntegrityError), transaction.atomic():
        second.save(update_fields=["client_session_id"])


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        {"question_index": 0},
        {"response_duration_ms": -1},
        {"result_type": "timeout", "is_correct": True},
    ],
)
def test_game_question_database_constraints_reject_invalid_rows(
    training_record, overrides
):
    with pytest.raises(IntegrityError), transaction.atomic():
        _question(training_record, **overrides)


@pytest.mark.django_db
def test_game_question_index_is_unique_per_training_record(training_record):
    _question(training_record)

    with pytest.raises(IntegrityError), transaction.atomic():
        _question(training_record, response_duration_ms=1)


@pytest.mark.django_db
def test_game_question_choices_reject_unknown_values_on_validation(training_record):
    question = GameQuestionResult(
        training_record=training_record,
        question_index=1,
        game_code="game-executive-inhibition",
        difficulty="中等",
        response_duration_ms=1,
        is_correct=True,
        result_type="unknown",
        capture_version="unknown",
    )

    with pytest.raises(ValidationError):
        question.full_clean()
