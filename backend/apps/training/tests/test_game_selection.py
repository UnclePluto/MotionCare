from copy import deepcopy
import pytest
from django.core.exceptions import ValidationError
from apps.training.tests import test_game_questions as base

normalize = base.normalize
fingerprint = base.fingerprint
game_action = base.game_action
form = base.form

pytestmark = pytest.mark.django_db


@pytest.fixture
def selection(game_action, form):
    game_action.action_library_item.source_key = "game-memory-color-sequence"
    form["difficulty"] = "简单"
    return dict(
        question_index=1,
        game_code="game-memory-color-sequence",
        difficulty="简单",
        response_duration_ms=900,
        is_correct=True,
        result_type="answered",
        swap_count=None,
        capture_version="active_response_v2",
        expected_step_count=3,
        click_count=None,
        selection_steps=[
            dict(
                step_index=i + 1,
                selected_value=t,
                expected_value=t,
                response_duration_ms=300,
                is_correct=True,
            )
            for i, t in enumerate(["blue", "green", "yellow"])
        ],
    )


def test_v2_steps_and_interrupted_summary(game_action, form, selection):
    interrupted = deepcopy(selection)
    interrupted.update(question_index=2, result_type="interrupted", is_correct=False)
    interrupted["selection_steps"] = interrupted["selection_steps"][:1]
    result = normalize(game_action, [selection, interrupted], form)
    assert result.rows[1]["selection_steps"] == interrupted["selection_steps"]
    assert result.form_data["raw_detail"]["recorded_question_count"] == 2
    assert result.form_data["raw_detail"]["completed_units"] == 1
    assert result.form_data["error_count"] == 0
    assert result.form_data["accuracy_rate"] == 100


@pytest.mark.parametrize(
    "patch",
    [
        {"expected_step_count": True},
        {"expected_step_count": 4},
        {"click_count": 0},
        {"selection_steps": None},
        {"selection_steps": [{}]},
        {"selection_steps": []},
        {"result_type": "interrupted", "is_correct": False},
        {"result_type": "timeout", "is_correct": False},
        {"is_correct": False},
        {"response_duration_ms": 899},
        {"unknown": 5},
    ],
)
def test_v2_rejects_invalid_parent(game_action, form, selection, patch):
    selection.update(patch)
    with pytest.raises(ValidationError):
        normalize(game_action, [selection], form)


@pytest.mark.parametrize(
    "patch",
    [
        {"step_index": True},
        {"step_index": 2},
        {"selected_value": "red"},
        {"expected_value": []},
        {"selected_value": {}},
        {"is_correct": False},
        {"is_correct": 1},
        {"response_duration_ms": -1},
        {"response_duration_ms": True},
        {"response_duration_ms": 3600001},
        {"unknown": 1},
    ],
)
def test_v2_rejects_invalid_step(game_action, form, selection, patch):
    selection["selection_steps"][0].update(patch)
    with pytest.raises(ValidationError):
        normalize(game_action, [selection], form)


@pytest.mark.parametrize("count", [0, 1, 2])
def test_timeout_preserves_partial_steps(game_action, form, selection, count):
    selection.update(result_type="timeout", is_correct=False)
    selection["selection_steps"] = selection["selection_steps"][:count]
    result = normalize(game_action, [selection], form)
    assert len(result.rows[0]["selection_steps"]) == count
    assert result.form_data["error_count"] == 1


def test_interrupted_only_last_nonempty_partial(game_action, form, selection):
    first = deepcopy(selection)
    first.update(result_type="interrupted", is_correct=False)
    first["selection_steps"] = first["selection_steps"][:1]
    with pytest.raises(ValidationError):
        normalize(game_action, [first, dict(selection, question_index=2)], form)
    first["selection_steps"] = []
    with pytest.raises(ValidationError):
        normalize(game_action, [first], form)


def test_v1_unknown_compatibility_and_new_fields_rejected(game_action, form, selection):
    legacy = {
        k: v
        for k, v in selection.items()
        if k not in ("selection_steps", "expected_step_count", "click_count")
    }
    legacy["capture_version"] = "active_response_v1"
    baseline = fingerprint(game_action, legacy, form)
    legacy["old_unknown"] = {"opaque": True}
    assert fingerprint(game_action, legacy, form) == baseline
    assert (
        "recorded_question_count"
        not in normalize(game_action, [legacy], form).form_data["raw_detail"]
    )
    for key, value in [
        ("selection_steps", []),
        ("expected_step_count", None),
        ("click_count", None),
        ("result_type", "interrupted"),
    ]:
        with pytest.raises(ValidationError):
            normalize(game_action, [dict(legacy, **{key: value})], form)
    with pytest.raises(ValidationError):
        normalize(game_action, [legacy, dict(selection, question_index=2)], form)


def test_v2_puzzle_clicks_and_single_choice(game_action, form, selection):
    for code in ["game-audiovisual-puzzle", "game-executive-inhibition"]:
        game_action.action_library_item.source_key = code
        selection.update(
            game_code=code,
            expected_step_count=None,
            selection_steps=[],
            swap_count=2 if "puzzle" in code else None,
            click_count=5 if "puzzle" in code else None,
        )
        assert (
            normalize(game_action, [selection], form).rows[0]["click_count"]
            == selection["click_count"]
        )
        for patch in [
            {"click_count": True},
            {"click_count": 3},
            {"result_type": "interrupted", "is_correct": False},
        ]:
            with pytest.raises(ValidationError):
                normalize(game_action, [dict(selection, **patch)], form)


def test_v2_child_failure_rolls_back_and_retry_is_idempotent(
    game_action, form, selection, monkeypatch
):
    from uuid import uuid4
    from django.db import IntegrityError
    from apps.training.models import GameQuestionSelectionStep, GameQuestionResult, TrainingRecord
    from apps.training.game_record_service import create_game_training_record, GameSessionConflict
    from apps.prescriptions.models import ActionLibraryItem

    game_action.action_library_item = ActionLibraryItem.objects.get_or_create(
        source_key="game-memory-color-sequence",
        defaults={"name": "颜色顺序", "internal_type": "game", "training_type": "认知训练"},
    )[0]
    game_action.save(update_fields=["action_library_item"])
    params = dict(
        project_patient=game_action.prescription.project_patient,
        prescription_action=game_action,
        training_date="2026-09-09",
        client_session_id=uuid4(),
        question_results=[selection],
        form_data=form,
        status="completed",
    )
    original = GameQuestionSelectionStep.objects.bulk_create

    def fail_after_insert(rows, **kwargs):
        original(rows, **kwargs)
        raise IntegrityError("模拟步骤存储故障")

    with monkeypatch.context() as patch:
        patch.setattr(GameQuestionSelectionStep.objects, "bulk_create", fail_after_insert)
        with pytest.raises(IntegrityError, match="模拟步骤存储故障"):
            create_game_training_record(**params)
    assert (
        TrainingRecord.objects.count()
        == GameQuestionResult.objects.count()
        == GameQuestionSelectionStep.objects.count()
        == 0
    )
    first = create_game_training_record(**params)
    form["raw_detail"]["retry_count"] = 3
    again = create_game_training_record(**params)
    assert first.created and not again.created
    assert first.record.pk == again.record.pk
    assert GameQuestionSelectionStep.objects.count() == 3
    selection["selection_steps"][0]["response_duration_ms"] -= 1
    with pytest.raises(GameSessionConflict):
        create_game_training_record(**params)
    first.record.delete()
    assert GameQuestionSelectionStep.objects.count() == 0


@pytest.mark.parametrize(
    "code,tokens",
    [
        ("game-memory-color-sequence", ["blue", "green", "yellow", "red", "teal"]),
        ("game-memory-pattern-sequence", ["sun", "coconut", "boat", "lighthouse", "shell"]),
    ],
)
@pytest.mark.parametrize("difficulty,count", [("简单", 3), ("中等", 4), ("困难", 5)])
def test_all_sequence_tokens_difficulties_and_wrong_answer(
    game_action, form, selection, code, tokens, difficulty, count
):
    game_action.action_library_item.source_key = code
    form["difficulty"] = difficulty
    selection.update(
        game_code=code,
        difficulty=difficulty,
        expected_step_count=count,
        selection_steps=[
            dict(
                step_index=i + 1,
                selected_value=token,
                expected_value=token,
                response_duration_ms=0,
                is_correct=True,
            )
            for i, token in enumerate(tokens[:count])
        ],
    )
    assert normalize(game_action, [selection], form).form_data["accuracy_rate"] == 100
    selection["selection_steps"][0].update(selected_value=tokens[1], is_correct=False)
    selection["is_correct"] = False
    assert normalize(game_action, [selection], form).form_data["error_count"] == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("changed", [False, True])
def test_v2_concurrent_uuid_race_preserves_single_parent_children(
    game_action, form, selection, monkeypatch, changed
):
    from apps.prescriptions.models import ActionLibraryItem
    from apps.patient_app.tests.test_game_record_idempotency import (
        test_concurrent_uuid_unique_race_is_atomic,
    )
    from apps.training.models import GameQuestionSelectionStep

    game_action.action_library_item = ActionLibraryItem.objects.get_or_create(
        source_key="game-memory-color-sequence",
        defaults={"name": "颜色顺序", "internal_type": "game", "training_type": "认知训练"},
    )[0]
    game_action.save(update_fields=["action_library_item"])
    payload = dict(
        prescription_action=game_action.pk,
        training_date="2026-09-09",
        status="completed",
        form_data=form,
        question_results=[selection],
    )
    test_concurrent_uuid_unique_race_is_atomic(game_action, payload, monkeypatch, changed)
    assert GameQuestionSelectionStep.objects.count() == 3


def test_v2_click_fingerprint_and_missing_fields(game_action, form, selection):
    game_action.action_library_item.source_key = "game-audiovisual-puzzle"
    selection.update(
        game_code="game-audiovisual-puzzle",
        expected_step_count=None,
        selection_steps=[],
        swap_count=2,
        click_count=4,
    )
    old = fingerprint(game_action, selection, form)
    selection["click_count"] = 5
    assert fingerprint(game_action, selection, form) != old
    for field in selection:
        incomplete = dict(selection)
        incomplete.pop(field)
        with pytest.raises(ValidationError):
            normalize(game_action, [incomplete], form)
