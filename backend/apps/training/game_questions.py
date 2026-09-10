"""新版游戏题目的严格输入校验及会话语义规范化。"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import hashlib
import json

from django.core.exceptions import ValidationError

from apps.prescriptions.models import ActionLibraryItem, PrescriptionAction

from .game_question_legacy import DIFFICULTIES, GAME_CODES
from .game_results import validate_game_result_fields
from .game_selection_validation import NEW_FIELDS, V1, V2, normalize_selection_fields
from .models import GameQuestionResult

MAX_QUESTIONS = 2000
MAX_RESPONSE_DURATION_MS = 3600000
MAX_DATABASE_INTEGER = 2147483647
UPLOAD_METADATA_KEYS = ("upload_mode", "retry_count", "total_retry_count")


@dataclass(frozen=True)
class NormalizedGameQuestions:
    rows: list[dict]
    form_data: dict


def _strict_integer(value, *, minimum=0, maximum=MAX_DATABASE_INTEGER):
    return type(value) is int and minimum <= value <= maximum


def normalize_new_question_results(
    *, prescription_action: PrescriptionAction, raw_results: list[dict], form_data: dict
) -> NormalizedGameQuestions:
    source_key = prescription_action.action_library_item.source_key
    if (
        prescription_action.internal_type_snapshot != ActionLibraryItem.InternalType.GAME
        or source_key not in GAME_CODES
    ):
        raise ValidationError("规范逐题结果只支持正式游戏动作")
    if not isinstance(raw_results, list) or len(raw_results) > MAX_QUESTIONS:
        raise ValidationError("游戏逐题结果必须是数组，且最多 2000 题")
    if not isinstance(form_data, dict):
        raise ValidationError("游戏结果明细必须是对象")
    form = deepcopy(form_data)
    difficulty = form.get("difficulty")
    if not isinstance(difficulty, str) or difficulty not in DIFFICULTIES:
        raise ValidationError("游戏实际难度必须为简单、中等或困难")
    raw = form.get("raw_detail")
    if not isinstance(raw, dict) or not _strict_integer(raw.get("session_duration_seconds")):
        raise ValidationError("游戏会话时长必须是非负整数秒")

    rows = []
    session_version = None
    for index, item in enumerate(raw_results, start=1):
        if not isinstance(item, dict):
            raise ValidationError("游戏逐题结果必须是对象")
        capture_version = item.get("capture_version", V1)
        if capture_version not in (V1, V2):
            raise ValidationError("新版题目不得使用历史采集版本")
        if session_version is not None and session_version != capture_version:
            raise ValidationError("同一场次不得混合采集版本")
        session_version = capture_version
        if capture_version == V1 and (NEW_FIELDS.intersection(item) or item.get("result_type") == "interrupted"):
            raise ValidationError("v1 题目不得包含 v2 选择数据或中断结果")
        if (
            not _strict_integer(item.get("question_index"), minimum=1)
            or item["question_index"] != index
        ):
            raise ValidationError("游戏题号必须从 1 连续递增")
        if item.get("game_code") != source_key:
            raise ValidationError("游戏编码必须匹配处方动作")
        if item.get("difficulty") != difficulty:
            raise ValidationError("逐题难度必须匹配本场实际难度")
        duration = item.get("response_duration_ms")
        if not _strict_integer(duration, maximum=MAX_RESPONSE_DURATION_MS):
            raise ValidationError("单题有效作答时长必须为 0 至 3600000 毫秒的整数")
        correct = item.get("is_correct")
        result_type = item.get("result_type")
        if type(correct) is not bool or result_type not in GameQuestionResult.ResultType.values:
            raise ValidationError("游戏判定必须包含布尔正确性及合法结果类型")
        if result_type == "timeout" and correct:
            raise ValidationError("超时题必须判定为错误")
        swap_count = item.get("swap_count")
        if source_key == "game-audiovisual-puzzle":
            if result_type != "answered" or not correct or not _strict_integer(swap_count):
                raise ValidationError("拼图只能提交完成题，且必须包含非负整数交换次数")
        elif swap_count is not None:
            raise ValidationError("非拼图题不得提交交换次数")
        rows.append(
            {
                "question_index": index,
                "game_code": source_key,
                "difficulty": difficulty,
                "response_duration_ms": duration,
                "is_correct": correct,
                "result_type": result_type,
                "swap_count": swap_count,
                "capture_version": capture_version,
            }
        )
        if capture_version == V2:
            rows[-1].update(normalize_selection_fields(item, is_last=index == len(raw_results)))

    if (
        sum(row["response_duration_ms"] for row in rows)
        > raw["session_duration_seconds"] * 1000 + 1000
    ):
        raise ValidationError("逐题有效作答总时长不能超过游戏会话时长")
    scored_rows = [row for row in rows if row["result_type"] != "interrupted"]
    completed = len(scored_rows)
    correct = sum(row["is_correct"] for row in scored_rows)
    if session_version == V2:
        raw["recorded_question_count"] = len(rows)
    form["error_count"] = completed - correct
    form["accuracy_rate"] = round(correct * 100 / completed, 1) if completed else 0
    raw.update(
        completed_units=completed,
        correct_units=correct,
        prescribed_difficulty=prescription_action.difficulty,
        difficulty_adjusted=difficulty != prescription_action.difficulty,
        difficulty_adjust_reason="",
    )
    # 新版题目是唯一来源；冗余旧题目不参与保存、汇总或重传匹配。
    raw.pop("rounds", None)
    validate_game_result_fields(prescription_action, form_data=form)
    return NormalizedGameQuestions(rows=rows, form_data=form)


def _canonical_json_value(value):
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite decimal")
        return format(value.normalize(), "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _canonical_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_json_value(item) for item in value]
    return value


def semantic_game_payload_fingerprint(
    *,
    project_patient_id: int,
    prescription_action_id: int,
    training_date: date,
    fields: dict,
    questions: NormalizedGameQuestions,
) -> str:
    form = deepcopy(questions.form_data)
    for key in ("accuracy_rate", "error_count", *UPLOAD_METADATA_KEYS):
        form.pop(key, None)
    raw = form.get("raw_detail", {})
    for key in ("completed_units", "correct_units", "rounds", *UPLOAD_METADATA_KEYS):
        raw.pop(key, None)
    try:
        canonical = {
            "project_patient": project_patient_id,
            "prescription_action": prescription_action_id,
            "training_date": date.fromisoformat(training_date)
            if isinstance(training_date, str)
            else training_date,
            "status": fields.get("status", ""),
            "actual_duration_minutes": fields.get("actual_duration_minutes"),
            "score": Decimal(str(fields["score"])) if fields.get("score") is not None else None,
            "note": fields.get("note", ""),
            "form_data": form,
            "question_results": questions.rows,
        }
        serialized = json.dumps(
            _canonical_json_value(canonical),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationError("游戏会话内容必须是有限数值的合法 JSON") from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
