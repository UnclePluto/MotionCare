from dataclasses import dataclass

from django.db import migrations


GAME_CODES = frozenset(
    {
        "game-memory-color-sequence",
        "game-memory-pattern-sequence",
        "game-executive-inhibition",
        "game-executive-category-switch",
        "game-audiovisual-sound-discrimination",
        "game-audiovisual-puzzle",
    }
)
DIFFICULTIES = frozenset({"简单", "中等", "困难"})
MAX_DATABASE_INTEGER = 2147483647
BATCH_SIZE = 500


@dataclass(frozen=True)
class LegacyParseResult:
    rows: list[dict]
    skipped_count: int


def _first_present(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _is_bounded_integer(value, *, minimum):
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and minimum <= value <= MAX_DATABASE_INTEGER
    )


def parse_legacy_rounds(
    *, form_data: dict, source_key: str, prescribed_difficulty: str
) -> LegacyParseResult:
    if not isinstance(form_data, dict):
        return LegacyParseResult(rows=[], skipped_count=0)

    raw_detail = form_data.get("raw_detail")
    if not isinstance(raw_detail, dict):
        return LegacyParseResult(rows=[], skipped_count=0)

    rounds = raw_detail.get("rounds")
    if not isinstance(rounds, list):
        return LegacyParseResult(rows=[], skipped_count=0)

    rows = []
    skipped_count = 0
    seen_indices = set()
    for item in rounds:
        if not isinstance(item, dict):
            skipped_count += 1
            continue

        index = item.get("round_index")
        response_ms = item.get("response_ms")
        correct = item.get("correct")
        game_code = _first_present(
            item.get("game_code"), raw_detail.get("game_code"), source_key
        )
        difficulty = _first_present(
            item.get("difficulty"),
            form_data.get("difficulty"),
            prescribed_difficulty,
        )
        is_timeout = item.get("result") == "timeout"

        if (
            not _is_bounded_integer(index, minimum=1)
            or index in seen_indices
            or not _is_bounded_integer(response_ms, minimum=0)
            or not isinstance(correct, bool)
            or not isinstance(source_key, str)
            or source_key not in GAME_CODES
            or not isinstance(game_code, str)
            or game_code not in GAME_CODES
            or game_code != source_key
            or not isinstance(difficulty, str)
            or difficulty not in DIFFICULTIES
            or (is_timeout and correct)
        ):
            skipped_count += 1
            continue

        rows.append(
            {
                "question_index": index,
                "game_code": game_code,
                "difficulty": difficulty,
                "response_duration_ms": response_ms,
                "is_correct": correct,
                "result_type": "timeout" if is_timeout else "answered",
                "swap_count": None,
                "capture_version": "legacy_wall_clock_v0",
            }
        )
        seen_indices.add(index)

    return LegacyParseResult(rows=rows, skipped_count=skipped_count)


def backfill_game_question_results(apps, schema_editor):
    Record = apps.get_model("training", "TrainingRecord")
    Question = apps.get_model("training", "GameQuestionResult")
    alias = schema_editor.connection.alias
    records = (
        Record.objects.using(alias)
        .filter(prescription_action__internal_type_snapshot="game")
        .select_related("prescription_action__action_library_item")
    )

    scanned_count = 0
    created_count = 0
    skipped_count = 0
    pending_questions = []

    def flush_pending():
        nonlocal created_count
        if not pending_questions:
            return
        Question.objects.using(alias).bulk_create(
            pending_questions, batch_size=BATCH_SIZE
        )
        created_count += len(pending_questions)
        pending_questions.clear()

    for record in records.iterator(chunk_size=BATCH_SIZE):
        scanned_count += 1
        if Question.objects.using(alias).filter(
            training_record_id=record.pk
        ).exists():
            skipped_count += 1
            continue

        action = record.prescription_action
        result = parse_legacy_rounds(
            form_data=record.form_data,
            source_key=action.action_library_item.source_key,
            prescribed_difficulty=action.difficulty,
        )
        skipped_count += result.skipped_count
        for row in result.rows:
            pending_questions.append(
                Question(training_record_id=record.pk, **row)
            )
            if len(pending_questions) >= BATCH_SIZE:
                flush_pending()

    flush_pending()
    print(
        "game question backfill: "
        f"scanned={scanned_count} created={created_count} skipped={skipped_count}"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0016_game_question_results"),
    ]

    operations = [
        migrations.RunPython(
            backfill_game_question_results,
            migrations.RunPython.noop,
        ),
    ]
