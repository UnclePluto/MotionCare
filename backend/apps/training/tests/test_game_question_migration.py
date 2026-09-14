import importlib
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.prescriptions.models import ActionLibraryItem
from apps.training.game_question_legacy import parse_legacy_rounds


MIGRATE_FROM = [("training", "0016_game_question_results")]
MIGRATE_TO = [("training", "0017_backfill_game_question_results")]
GAME_CODE = "game-audiovisual-puzzle"


@pytest.fixture(autouse=True)
def _restore_latest_schema(django_db_setup, django_db_blocker):
    del django_db_setup
    with django_db_blocker.unblock():
        latest_leaf_nodes = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        yield
    finally:
        with django_db_blocker.unblock():
            MigrationExecutor(connection).migrate(latest_leaf_nodes)


@pytest.fixture
def legacy_game_action(active_prescription):
    item = ActionLibraryItem.objects.create(
        source_key=GAME_CODE,
        name="图片拼图",
        training_type="认知训练",
        internal_type=ActionLibraryItem.InternalType.GAME,
        action_type="视听训练",
    )
    return active_prescription.add_action_snapshot(item, difficulty="简单")


def _training_record(Record, *, project_patient, prescription, action, form_data):
    return Record.objects.create(
        project_patient_id=project_patient.id,
        prescription_id=prescription.id,
        prescription_action_id=action.id,
        training_date=timezone.localdate(),
        status="completed",
        form_data=form_data,
    )


@pytest.mark.django_db(transaction=True)
def test_frozen_migration_parser_matches_online_parser():
    migration = importlib.import_module(
        "apps.training.migrations.0017_backfill_game_question_results"
    )
    kwargs = {
        "form_data": {
            "difficulty": "中等",
            "raw_detail": {
                "game_code": GAME_CODE,
                "rounds": [
                    {"round_index": 1, "response_ms": 0, "correct": True},
                    {
                        "round_index": 3,
                        "response_ms": 2400,
                        "correct": False,
                        "result": "timeout",
                    },
                    {"round_index": 3, "response_ms": 2, "correct": True},
                    {"round_index": 4, "response_ms": True, "correct": True},
                ],
            },
        },
        "source_key": GAME_CODE,
        "prescribed_difficulty": "简单",
    }

    online = parse_legacy_rounds(**kwargs)
    frozen = migration.parse_legacy_rounds(**kwargs)

    assert frozen.rows == online.rows
    assert frozen.skipped_count == online.skipped_count


@pytest.mark.django_db(transaction=True)
def test_backfill_keeps_valid_rows_and_json_and_is_idempotent(
    project_patient,
    active_prescription,
    legacy_game_action,
    capsys,
):
    executor = MigrationExecutor(connection)
    executor.migrate(MIGRATE_FROM)
    old_apps = executor.loader.project_state(MIGRATE_FROM).apps
    Record = old_apps.get_model("training", "TrainingRecord")
    Question = old_apps.get_model("training", "GameQuestionResult")

    mixed_form_data = {
        "difficulty": "中等",
        "raw_detail": {
            "game_code": GAME_CODE,
            "rounds": [
                {"round_index": 1, "response_ms": 0, "correct": True},
                {
                    "round_index": 3,
                    "response_ms": 2400,
                    "correct": False,
                    "result": "timeout",
                },
                {"round_index": 3, "response_ms": 2, "correct": True},
                {"round_index": 4, "response_ms": "bad", "correct": True},
            ],
        },
    }
    migrated_record = _training_record(
        Record,
        project_patient=project_patient,
        prescription=active_prescription,
        action=legacy_game_action,
        form_data=mixed_form_data,
    )

    existing_form_data = {
        "difficulty": "困难",
        "raw_detail": {
            "rounds": [
                {"round_index": 1, "response_ms": 999, "correct": False}
            ]
        },
    }
    existing_record = _training_record(
        Record,
        project_patient=project_patient,
        prescription=active_prescription,
        action=legacy_game_action,
        form_data=existing_form_data,
    )
    Question.objects.create(
        training_record_id=existing_record.id,
        question_index=1,
        game_code=GAME_CODE,
        difficulty="困难",
        response_duration_ms=123,
        is_correct=True,
        result_type="answered",
        swap_count=2,
        capture_version="active_response_v1",
    )

    executor = MigrationExecutor(connection)
    executor.migrate(MIGRATE_TO)
    new_apps = executor.loader.project_state(MIGRATE_TO).apps
    Record = new_apps.get_model("training", "TrainingRecord")
    Question = new_apps.get_model("training", "GameQuestionResult")

    migrated_rows = list(
        Question.objects.filter(training_record_id=migrated_record.id)
        .order_by("question_index")
        .values(
            "question_index",
            "response_duration_ms",
            "is_correct",
            "result_type",
            "swap_count",
            "capture_version",
        )
    )
    assert migrated_rows == [
        {
            "question_index": 1,
            "response_duration_ms": 0,
            "is_correct": True,
            "result_type": "answered",
            "swap_count": None,
            "capture_version": "legacy_wall_clock_v0",
        },
        {
            "question_index": 3,
            "response_duration_ms": 2400,
            "is_correct": False,
            "result_type": "timeout",
            "swap_count": None,
            "capture_version": "legacy_wall_clock_v0",
        },
    ]
    assert Record.objects.get(pk=migrated_record.id).form_data == mixed_form_data
    assert list(
        Question.objects.filter(training_record_id=existing_record.id).values_list(
            "response_duration_ms", "capture_version"
        )
    ) == [(123, "active_response_v1")]

    first_output = capsys.readouterr().out
    assert "scanned=2" in first_output
    assert "created=2" in first_output
    assert "skipped=3" in first_output
    assert "raw_detail" not in first_output

    migration = importlib.import_module(
        "apps.training.migrations.0017_backfill_game_question_results"
    )
    migration.backfill_game_question_results(
        new_apps, SimpleNamespace(connection=connection)
    )

    assert Question.objects.count() == 3
    second_output = capsys.readouterr().out
    assert "scanned=2" in second_output
    assert "created=0" in second_output
    assert "skipped=2" in second_output
