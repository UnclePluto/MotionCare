from django.core.exceptions import ValidationError

from apps.prescriptions.models import ActionLibraryItem, PrescriptionAction


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
        if not isinstance(error_count, int) or isinstance(error_count, bool) or error_count < 0:
            raise ValidationError("错误次数必须是非负整数")

    difficulty = form_data.get("difficulty")
    if difficulty is not None and not isinstance(difficulty, str):
        raise ValidationError("游戏难度必须是文本")
