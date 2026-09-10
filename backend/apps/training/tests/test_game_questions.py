from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.prescriptions.models import ActionLibraryItem
from apps.training.game_questions import (
    normalize_new_question_results,
    semantic_game_payload_fingerprint,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def game_action(active_prescription):
    item, _ = ActionLibraryItem.objects.get_or_create(
        source_key="game-executive-inhibition",
        defaults={"name": "反应抑制", "internal_type": "game", "training_type": "认知训练"},
    )
    return active_prescription.add_action_snapshot(item, difficulty="简单")


@pytest.fixture
def question():
    return {
        "question_index": 1,
        "game_code": "game-executive-inhibition",
        "difficulty": "困难",
        "response_duration_ms": 2300,
        "is_correct": True,
        "result_type": "answered",
        "swap_count": None,
    }


@pytest.fixture
def form():
    return {
        "difficulty": "困难",
        "accuracy_rate": 7,
        "error_count": 88,
        "raw_detail": {"session_duration_seconds": 10},
    }


def normalize(action, rows, form):
    return normalize_new_question_results(
        prescription_action=action,
        raw_results=rows,
        form_data=form,
    )


def test_authoritative_summary_and_no_input_mutation(game_action, question, form):
    original = deepcopy(form)
    normalized = normalize(game_action, [question], form)
    assert normalized.form_data["accuracy_rate"] == 100
    assert normalized.form_data["error_count"] == 0
    assert normalized.form_data["raw_detail"] == {
        "session_duration_seconds": 10,
        "completed_units": 1,
        "correct_units": 1,
        "prescribed_difficulty": "简单",
        "difficulty_adjusted": True,
        "difficulty_adjust_reason": "",
    }
    assert normalized.rows[0]["capture_version"] == "active_response_v1"
    assert form == original
    assert "capture_version" not in question


def test_empty_session_and_zero_duration_remain_real_values(game_action, question, form):
    normalized = normalize(game_action, [], form)
    assert normalized.rows == []
    assert normalized.form_data["accuracy_rate"] == 0
    assert normalized.form_data["raw_detail"]["completed_units"] == 0
    question.update(response_duration_ms=0, result_type="timeout", is_correct=False)
    normalized = normalize(game_action, [question], form)
    assert normalized.rows[0]["response_duration_ms"] == 0
    assert normalized.rows[0]["is_correct"] is False
    assert normalized.form_data["error_count"] == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"question_index": True},
        {"question_index": "1"},
        {"question_index": 2},
        {"response_duration_ms": True},
        {"response_duration_ms": "2300"},
        {"response_duration_ms": -1},
        {"response_duration_ms": 3600001},
        {"is_correct": "false"},
        {"is_correct": 1},
        {"difficulty": "极难"},
        {"difficulty": "简单"},
        {"game_code": "unknown"},
        {"game_code": "game-memory-color-sequence"},
        {"result_type": "unknown"},
        {"result_type": "timeout"},
        {"swap_count": 0},
        {"capture_version": "legacy_wall_clock_v0"},
    ],
)
def test_rejects_invalid_question_fields(game_action, question, form, patch):
    question.update(patch)
    with pytest.raises(ValidationError):
        normalize(game_action, [question], form)


@pytest.mark.parametrize("rows", [None, {}, [None], [{}]])
def test_rejects_malformed_rows(game_action, rows, form):
    with pytest.raises(ValidationError):
        normalize(game_action, rows, form)


@pytest.mark.parametrize(
    "bad_form",
    [
        None,
        [],
        {"difficulty": "困难"},
        {"difficulty": "困难", "raw_detail": []},
        {"difficulty": "困难", "raw_detail": {"session_duration_seconds": True}},
        {"difficulty": "困难", "raw_detail": {"session_duration_seconds": "10"}},
        {"difficulty": "极难", "raw_detail": {"session_duration_seconds": 10}},
    ],
)
def test_rejects_invalid_session_form(game_action, question, bad_form):
    with pytest.raises(ValidationError):
        normalize(game_action, [question], bad_form)


def test_rejects_motion_and_unknown_game(game_action, prescription_action, question, form):
    with pytest.raises(ValidationError):
        normalize(prescription_action, [], form)
    game_action.action_library_item.source_key = "unknown"
    with pytest.raises(ValidationError):
        normalize(game_action, [question], form)


def test_count_and_duration_limits_inclusive(game_action, question, form):
    rows = [dict(question, question_index=i + 1, response_duration_ms=0) for i in range(2000)]
    assert len(normalize(game_action, rows, form).rows) == 2000
    with pytest.raises(ValidationError):
        normalize(game_action, rows + [dict(question, question_index=2001)], form)
    question["response_duration_ms"] = 11000
    assert normalize(game_action, [question], form).rows[0]["response_duration_ms"] == 11000
    question["response_duration_ms"] = 11001
    with pytest.raises(ValidationError):
        normalize(game_action, [question], form)
    question["response_duration_ms"] = 3600000
    form["raw_detail"]["session_duration_seconds"] = 3600
    assert normalize(game_action, [question], form).rows[0]["response_duration_ms"] == 3600000


@pytest.mark.parametrize(
    "patch",
    [
        {"swap_count": None},
        {"swap_count": -1},
        {"swap_count": True},
        {"swap_count": "3"},
        {"swap_count": 2147483648},
        {"is_correct": False},
        {"result_type": "timeout", "is_correct": False},
    ],
)
def test_puzzle_only_accepts_completed_correct_with_integer_swaps(
    game_action, question, form, patch
):
    game_action.action_library_item.source_key = "game-audiovisual-puzzle"
    question.update(game_code="game-audiovisual-puzzle", swap_count=0)
    assert normalize(game_action, [question], form).rows[0]["swap_count"] == 0
    question.update(patch)
    with pytest.raises(ValidationError):
        normalize(game_action, [question], form)


def fingerprint(action, question, form, **overrides):
    params = {
        "project_patient_id": action.prescription.project_patient_id,
        "prescription_action_id": action.pk,
        "training_date": date(2026, 9, 9),
        "fields": {"status": "completed", "score": Decimal("90.00"), "note": "完成"},
        "questions": normalize(action, [question], form),
    }
    params.update(overrides)
    return semantic_game_payload_fingerprint(**params)


def test_fingerprint_ignores_derived_and_upload_metadata_and_legacy_rounds(
    game_action, question, form
):
    first = fingerprint(game_action, question, form)
    form.update(accuracy_rate=90, error_count=5)
    form["raw_detail"].update(
        completed_units=88,
        correct_units=77,
        upload_mode="retry",
        retry_count=2,
        total_retry_count=100,
        rounds=[{"round_index": 999}],
    )
    assert fingerprint(game_action, question, form) == first
    assert len(first) == 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("prescription_action_id", 999),
        ("project_patient_id", 999),
        ("training_date", date(2026, 9, 8)),
        ("fields", {"status": "completed", "score": Decimal("90.00"), "note": "变化"}),
    ],
)
def test_fingerprint_changes_for_semantic_fields(game_action, question, form, field, value):
    assert fingerprint(game_action, question, form, **{field: value}) != fingerprint(
        game_action, question, form
    )


def test_fingerprint_changes_for_question_time_and_difficulty(game_action, question, form):
    first = fingerprint(game_action, question, form)
    question["response_duration_ms"] += 1
    assert fingerprint(game_action, question, form) != first
    question["response_duration_ms"] -= 1
    question["difficulty"] = form["difficulty"] = "中等"
    assert fingerprint(game_action, question, form) != first


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_recursive_json_rejects_nonfinite_values(game_action, question, form, invalid):
    form["raw_detail"]["nested"] = {"value": [invalid]}
    with pytest.raises(ValidationError):
        fingerprint(game_action, question, form)
