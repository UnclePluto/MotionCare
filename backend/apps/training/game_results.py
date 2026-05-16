from django.core.exceptions import ValidationError

from apps.prescriptions.models import ActionLibraryItem, PrescriptionAction


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_non_negative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_raw_detail(prescription_action: PrescriptionAction, raw_detail: dict) -> None:
    game_code = raw_detail.get("game_code")
    if game_code not in (None, ""):
        source_key = prescription_action.action_library_item.source_key
        if not source_key or game_code != source_key:
            raise ValidationError("游戏编码必须匹配处方动作")

    ended_by = raw_detail.get("ended_by")
    if ended_by not in (None, "", "timer", "manual"):
        raise ValidationError("游戏结束方式必须是 timer 或 manual")

    ended_early = raw_detail.get("ended_early")
    if ended_early not in (None, "") and not isinstance(ended_early, bool):
        raise ValidationError("游戏提前结束标记必须是布尔值")

    upload_mode = raw_detail.get("upload_mode")
    if upload_mode not in (None, "", "direct", "retry"):
        raise ValidationError("游戏上传方式必须是 direct 或 retry")

    retry_count = raw_detail.get("retry_count")
    if retry_count not in (None, "") and not _is_non_negative_int(retry_count):
        raise ValidationError("游戏补传次数必须是非负整数")

    total_retry_count = raw_detail.get("total_retry_count")
    if total_retry_count not in (None, "") and not _is_non_negative_int(total_retry_count):
        raise ValidationError("游戏累计补传次数必须是非负整数")

    for key in (
        "session_duration_seconds",
        "suggested_duration_minutes",
        "completed_units",
        "correct_units",
    ):
        value = raw_detail.get(key)
        if value not in (None, "") and not _is_non_negative_int(value):
            raise ValidationError("游戏会话数值必须是非负整数")


def validate_game_result_fields(
    prescription_action: PrescriptionAction,
    *,
    form_data,
) -> None:
    if prescription_action.internal_type_snapshot != ActionLibraryItem.InternalType.GAME:
        return
    if form_data in (None, ""):
        return
    if not isinstance(form_data, dict):
        raise ValidationError("游戏结果明细必须是对象")

    accuracy_rate = form_data.get("accuracy_rate")
    if accuracy_rate not in (None, ""):
        if not _is_number(accuracy_rate) or accuracy_rate < 0 or accuracy_rate > 100:
            raise ValidationError("正确率必须在 0 到 100 之间")

    error_count = form_data.get("error_count")
    if error_count not in (None, ""):
        if not _is_non_negative_int(error_count):
            raise ValidationError("错误次数必须是非负整数")

    difficulty = form_data.get("difficulty")
    if difficulty is not None and not isinstance(difficulty, str):
        raise ValidationError("游戏难度必须是文本")

    raw_detail = form_data.get("raw_detail")
    if raw_detail not in (None, ""):
        if not isinstance(raw_detail, dict):
            raise ValidationError("游戏原始明细必须是对象")
        _validate_raw_detail(prescription_action, raw_detail)
