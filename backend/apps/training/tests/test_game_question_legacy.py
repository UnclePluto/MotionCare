import importlib

import pytest

from apps.training.game_question_legacy import (
    parse_legacy_rounds as online_parse_legacy_rounds,
)


GAME_CODE = "game-audiovisual-puzzle"


@pytest.fixture(
    params=[
        pytest.param(online_parse_legacy_rounds, id="online"),
        pytest.param(
            importlib.import_module(
                "apps.training.migrations.0017_backfill_game_question_results"
            ).parse_legacy_rounds,
            id="migration-frozen",
        ),
    ]
)
def parse_legacy_rounds(request):
    return request.param


def _parse(parse_legacy_rounds, rounds, **overrides):
    form_data = {
        "difficulty": "中等",
        "raw_detail": {"rounds": rounds},
    }
    form_data.update(overrides.pop("form_data", {}))
    return parse_legacy_rounds(
        form_data=form_data,
        source_key=overrides.pop("source_key", GAME_CODE),
        prescribed_difficulty=overrides.pop("prescribed_difficulty", "简单"),
    )


def test_legacy_keeps_zero_and_gaps_without_inventing_swaps(parse_legacy_rounds):
    result = parse_legacy_rounds(
        form_data={
            "difficulty": "中等",
            "raw_detail": {
                "rounds": [
                    {"round_index": 1, "response_ms": 0, "correct": True},
                    {"round_index": 3, "response_ms": 2400, "correct": False},
                    {"round_index": 3, "response_ms": 2, "correct": True},
                    {"round_index": 4, "response_ms": "bad", "correct": True},
                ]
            },
        },
        source_key=GAME_CODE,
        prescribed_difficulty="简单",
    )

    assert [row["question_index"] for row in result.rows] == [1, 3]
    assert result.rows[0]["response_duration_ms"] == 0
    assert result.rows[0]["swap_count"] is None
    assert {row["capture_version"] for row in result.rows} == {
        "legacy_wall_clock_v0"
    }
    assert result.skipped_count == 2


@pytest.mark.parametrize(
    "round_item",
    [
        {"round_index": True, "response_ms": 20, "correct": True},
        {"round_index": 0, "response_ms": 20, "correct": True},
        {"round_index": -1, "response_ms": 20, "correct": True},
        {"round_index": 2147483648, "response_ms": 20, "correct": True},
        {"round_index": 1, "response_ms": True, "correct": True},
        {"round_index": 1, "response_ms": -1, "correct": True},
        {"round_index": 1, "response_ms": 2147483648, "correct": True},
        {"round_index": 1, "response_ms": 20, "correct": 1},
    ],
)
def test_legacy_skips_invalid_integer_and_boolean_shapes(
    parse_legacy_rounds, round_item
):
    result = _parse(parse_legacy_rounds, [round_item])

    assert result.rows == []
    assert result.skipped_count == 1


@pytest.mark.parametrize(
    "form_data",
    [None, [], "bad", {}, {"raw_detail": []}, {"raw_detail": {"rounds": {}}}],
)
def test_legacy_non_object_or_non_list_payload_is_safe(
    parse_legacy_rounds, form_data
):
    result = parse_legacy_rounds(
        form_data=form_data,
        source_key=GAME_CODE,
        prescribed_difficulty="简单",
    )

    assert result.rows == []
    assert result.skipped_count == 0


def test_legacy_uses_first_present_game_code_and_difficulty(parse_legacy_rounds):
    result = parse_legacy_rounds(
        form_data={
            "difficulty": "困难",
            "raw_detail": {
                "game_code": GAME_CODE,
                "rounds": [
                    {
                        "round_index": 1,
                        "response_ms": 20,
                        "correct": True,
                        "difficulty": "简单",
                    },
                    {"round_index": 2, "response_ms": 30, "correct": False},
                ],
            },
        },
        source_key=GAME_CODE,
        prescribed_difficulty="中等",
    )

    assert [row["difficulty"] for row in result.rows] == ["简单", "困难"]
    assert {row["game_code"] for row in result.rows} == {GAME_CODE}


@pytest.mark.parametrize(
    ("form_data", "source_key"),
    [
        (
            {
                "difficulty": "中等",
                "raw_detail": {
                    "rounds": [
                        {
                            "round_index": 1,
                            "response_ms": 20,
                            "correct": True,
                            "game_code": "game-memory-color-sequence",
                        }
                    ]
                },
            },
            GAME_CODE,
        ),
        (
            {
                "difficulty": "中等",
                "raw_detail": {
                    "game_code": "game-unknown",
                    "rounds": [
                        {"round_index": 1, "response_ms": 20, "correct": True}
                    ],
                },
            },
            GAME_CODE,
        ),
        (
            {
                "difficulty": "中等",
                "raw_detail": {
                    "rounds": [
                        {"round_index": 1, "response_ms": 20, "correct": True}
                    ]
                },
            },
            "game-unknown",
        ),
    ],
)
def test_legacy_skips_unknown_or_mismatched_game_code(
    parse_legacy_rounds, form_data, source_key
):
    result = parse_legacy_rounds(
        form_data=form_data,
        source_key=source_key,
        prescribed_difficulty="简单",
    )

    assert result.rows == []
    assert result.skipped_count == 1


def test_legacy_skips_invalid_first_present_difficulty_without_fallback(
    parse_legacy_rounds,
):
    result = _parse(
        parse_legacy_rounds,
        [
            {
                "round_index": 1,
                "response_ms": 20,
                "correct": True,
                "difficulty": "普通",
            }
        ]
    )

    assert result.rows == []
    assert result.skipped_count == 1


@pytest.mark.parametrize(
    "round_overrides",
    [
        {"game_code": []},
        {"game_code": {}},
        {"difficulty": []},
        {"difficulty": {}},
    ],
)
def test_legacy_skips_non_string_game_code_and_difficulty(
    parse_legacy_rounds, round_overrides
):
    result = _parse(
        parse_legacy_rounds,
        [
            {
                "round_index": 1,
                "response_ms": 20,
                "correct": True,
                **round_overrides,
            }
        ]
    )

    assert result.rows == []
    assert result.skipped_count == 1


def test_legacy_keeps_consistent_timeout_and_skips_contradiction(
    parse_legacy_rounds,
):
    result = _parse(
        parse_legacy_rounds,
        [
            {
                "round_index": 1,
                "response_ms": 4000,
                "correct": False,
                "result": "timeout",
            },
            {
                "round_index": 2,
                "response_ms": 4000,
                "correct": True,
                "result": "timeout",
            },
        ]
    )

    assert [row["result_type"] for row in result.rows] == ["timeout"]
    assert result.skipped_count == 1


def test_legacy_skips_non_object_round_and_counts_it(parse_legacy_rounds):
    result = _parse(
        parse_legacy_rounds,
        [None, {"round_index": 2, "response_ms": 10, "correct": True}],
    )

    assert [row["question_index"] for row in result.rows] == [2]
    assert result.skipped_count == 1
