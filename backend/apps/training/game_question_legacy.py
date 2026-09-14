from dataclasses import dataclass


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
