"""v2 选择步骤校验；独立于 v1 规范化以保留旧指纹。"""

from copy import deepcopy

from django.core.exceptions import ValidationError

V1 = "active_response_v1"
V2 = "active_response_v2"
NEW_FIELDS = {"expected_step_count", "selection_steps", "click_count"}
QUESTION_FIELDS = {
    "question_index",
    "game_code",
    "difficulty",
    "response_duration_ms",
    "is_correct",
    "result_type",
    "swap_count",
    "capture_version",
} | NEW_FIELDS
STEP_FIELDS = {
    "step_index",
    "selected_value",
    "expected_value",
    "response_duration_ms",
    "is_correct",
}
SEQUENCE_TOKENS = {
    "game-memory-color-sequence": ("blue", "green", "yellow", "red", "teal"),
    "game-memory-pattern-sequence": ("sun", "coconut", "boat", "lighthouse", "shell"),
}


def integer(value, maximum=2147483647):
    return type(value) is int and 0 <= value <= maximum


def normalize_selection_fields(item, *, is_last):
    if set(item) != QUESTION_FIELDS:
        raise ValidationError("v2 题目字段必须完整且不得包含未知字段")
    steps = item["selection_steps"]
    if not isinstance(steps, list) or len(steps) > 5:
        raise ValidationError("选择步骤必须是最多5项的数组")
    code = item["game_code"]
    expected = item["expected_step_count"]
    clicks = item["click_count"]
    if code not in SEQUENCE_TOKENS:
        if expected is not None or steps or item["result_type"] == "interrupted":
            raise ValidationError("非顺序题不能提交选择步骤或中断结果")
        if code == "game-audiovisual-puzzle":
            if not integer(clicks) or clicks < 2 * item["swap_count"]:
                raise ValidationError("拼图点击次数必须为非负整数且不少于交换次数的两倍")
        elif clicks is not None:
            raise ValidationError("非拼图题不能提交点击次数")
    else:
        size = {"简单": 3, "中等": 4, "困难": 5}[item["difficulty"]]
        if not integer(expected) or expected != size or clicks is not None:
            raise ValidationError("顺序题应选步数必须匹配难度且不能提交点击次数")
        tokens = SEQUENCE_TOKENS[code][:size]
        for index, step in enumerate(steps, 1):
            if not isinstance(step, dict) or set(step) != STEP_FIELDS:
                raise ValidationError("选择步骤字段必须完整且不得包含未知字段")
            if (
                not integer(step["step_index"])
                or step["step_index"] != index
                or not isinstance(step["selected_value"], str)
                or step["selected_value"] not in tokens
                or not isinstance(step["expected_value"], str)
                or step["expected_value"] not in tokens
                or not integer(step["response_duration_ms"], 3600000)
                or type(step["is_correct"]) is not bool
                or step["is_correct"] != (step["selected_value"] == step["expected_value"])
            ):
                raise ValidationError("选择步骤编号、内容、耗时或判定不合法")
        count = len(steps)
        result = item["result_type"]
        if (
            count > size
            or sum(step["response_duration_ms"] for step in steps) > item["response_duration_ms"]
        ):
            raise ValidationError("选择步数或步骤总耗时超过题目范围")
        if result == "answered":
            if count != size or item["is_correct"] != all(step["is_correct"] for step in steps):
                raise ValidationError("已作答顺序题必须选满且正确性与步骤一致")
        elif (
            item["is_correct"]
            or count >= size
            or (result == "interrupted" and (not count or not is_last))
        ):
            raise ValidationError("未完成顺序题必须保留合法部分步骤，中断题只能是末题")
    return {key: deepcopy(item[key]) for key in NEW_FIELDS}
