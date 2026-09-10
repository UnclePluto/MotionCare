"""已预载训练记录的纯字段映射；禁止在这些函数内查询数据库。"""

import json
import math
from decimal import Decimal

from .game_questions import MAX_QUESTIONS, MAX_RESPONSE_DURATION_MS
from .motion_analysis_support import get_analysis_profile
from .tracking import phone_masked
from .video_serializers import ANALYSIS_FAILURE_MESSAGE

WINDOW_DESCRIPTION = "首次录像开始＋处方秒数＋300秒（含处方时长后5分钟，闭区间）"
ACTIVE_DESCRIPTION = "有效作答时间；排除展示、暂停、隐藏、语音及答后反馈"
QUALITY_FIELDS = (
    "confidence_level",
    "quality_flags",
    "subject_coverage_ratio",
    "ambiguity_ratio",
    "doctor_note",
)


def number(value):
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return value
    return None


def object_data(value):
    return value if isinstance(value, dict) else {}


def finite_json_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def duration_fields(record, video, is_game):
    raw = object_data(object_data(record.form_data).get("raw_detail"))
    if is_game and number(raw.get("session_duration_seconds")) is not None:
        return raw["session_duration_seconds"], "游戏会话秒数"
    if not is_game and video is not None and video.actual_duration_seconds is not None:
        return video.actual_duration_seconds, "录像实际训练秒数"
    if record.actual_duration_minutes is not None:
        return record.actual_duration_minutes * 60, "按分钟记录"
    return None, "未记录"


def plan_seconds(action, video):
    if video is not None and video.expected_duration_seconds is not None:
        return video.expected_duration_seconds
    return action.duration_minutes * 60 if action.duration_minutes is not None else None


SEQUENCE_TOKENS = {
    "game-memory-color-sequence": {
        "blue": "蓝色",
        "green": "绿色",
        "yellow": "黄色",
        "red": "红色",
        "teal": "青色",
    },
    "game-memory-pattern-sequence": {
        "sun": "太阳",
        "coconut": "椰子",
        "boat": "小船",
        "lighthouse": "灯塔",
        "shell": "贝壳",
    },
}


def _integer(value, maximum=MAX_RESPONSE_DURATION_MS):
    return type(value) is int and 0 <= value <= maximum


def has_valid_response_duration(question):
    if not _integer(question.get("response_duration_ms")):
        return False
    version = question.get("capture_version")
    if version == "active_response_v1":
        return (
            question.get("result_type") != "interrupted"
            and question.get("expected_step_count") is None
            and question.get("click_count") is None
            and not question.get("selection_steps")
        )
    if version != "active_response_v2":
        return False
    if question.get("difficulty") not in ("简单", "中等", "困难"):
        return False
    code, result = question.get("game_code"), question.get("result_type")
    correct, steps = question.get("is_correct"), question.get("selection_steps")
    if (
        type(correct) is not bool
        or result not in ("answered", "timeout", "interrupted")
        or not isinstance(steps, list)
    ):
        return False
    if result != "answered" and correct:
        return False
    if code in SEQUENCE_TOKENS:
        expected = {"简单": 3, "中等": 4, "困难": 5}.get(question.get("difficulty"))
        if (
            expected is None
            or type(question.get("expected_step_count")) is not int
            or question["expected_step_count"] != expected
        ):
            return False
        if (
            question.get("click_count") is not None
            or question.get("swap_count") is not None
            or len(steps) > expected
        ):
            return False
        allowed = list(SEQUENCE_TOKENS[code])[:expected]
        total = 0
        for index, step in enumerate(steps, 1):
            if (
                not isinstance(step, dict)
                or type(step.get("step_index")) is not int
                or step["step_index"] != index
            ):
                return False
            selected, target = step.get("selected_value"), step.get("expected_value")
            if (
                selected not in allowed
                or target not in allowed
                or type(step.get("is_correct")) is not bool
                or step["is_correct"] != (selected == target)
            ):
                return False
            if not _integer(step.get("response_duration_ms")):
                return False
            total += step["response_duration_ms"]
        return total <= question["response_duration_ms"] and (
            (
                result == "answered"
                and len(steps) == expected
                and correct == all(s["is_correct"] for s in steps)
            )
            or (result == "timeout" and len(steps) < expected)
            or (
                result == "interrupted"
                and question.get("_is_last", True)
                and 0 < len(steps) < expected
            )
        )
    if steps or question.get("expected_step_count") is not None or result == "interrupted":
        return False
    if code == "game-audiovisual-puzzle":
        clicks, swaps = question.get("click_count"), question.get("swap_count")
        return (
            result == "answered"
            and correct
            and _integer(clicks, 2147483647)
            and _integer(swaps, 2147483647)
            and clicks >= 2 * swaps
        )
    return (
        code
        in (
            "game-executive-inhibition",
            "game-executive-category-switch",
            "game-audiovisual-sound-discrimination",
        )
        and question.get("click_count") is None
        and question.get("swap_count") is None
    )


def question_status(question):
    if question["result_type"] == "interrupted" or (
        question["game_code"] in SEQUENCE_TOKENS and question["result_type"] == "timeout"
    ):
        return "未完成"
    return "超时" if question["result_type"] == "timeout" else "已完成"


def selection_rows(record, question):
    if (
        question["capture_version"] != "active_response_v2"
        or question["game_code"] not in SEQUENCE_TOKENS
    ):
        return
    labels = SEQUENCE_TOKENS[question["game_code"]]
    for step in question["selection_steps"]:
        yield {
            "训练记录编号": record.pk,
            "训练日期": record.training_date,
            "游戏编码": question["game_code"],
            "游戏名称": record.prescription_action.action_name_snapshot,
            "题号": question["question_index"],
            "题目状态": question_status(question),
            "选择序号": step["step_index"],
            "所选内容": labels[step["selected_value"]],
            "正确内容": labels[step["expected_value"]],
            "有效选择耗时（毫秒）": step["response_duration_ms"],
            "判定": "正确" if step["is_correct"] else "错误",
            "实际难度": question["difficulty"],
        }


def question_row(record, question):
    return {
        "训练记录编号": record.pk,
        "训练日期": record.training_date,
        "游戏编码": question["game_code"],
        "游戏名称": record.prescription_action.action_name_snapshot,
        "题号": question["question_index"],
        "实际难度": question["difficulty"],
        "有效作答时间（毫秒）": question["response_duration_ms"],
        "题目状态": question_status(question),
        "已选择步数": len(question["selection_steps"])
        if question.get("expected_step_count") is not None
        else None,
        "应选择步数": question.get("expected_step_count"),
        "拼图点击次数": question.get("click_count"),
        "判定": "未完成"
        if question["result_type"] == "interrupted"
        else "超时"
        if question["result_type"] == "timeout"
        else ("正确" if question["is_correct"] else "错误"),
        "实际交换次数": question["swap_count"],
        "采集版本": question["capture_version"],
        "数据口径说明": ACTIVE_DESCRIPTION,
    }


def game_summary(record, questions, is_game):
    if not is_game:
        return {
            "逐题记录数": 0,
            "规范计时题数": 0,
            "逐题完整性": "不适用（运动训练）",
        }
    action = record.prescription_action
    form = object_data(record.form_data)
    raw = object_data(form.get("raw_detail"))
    exported_questions = [q for q in questions if has_valid_response_duration(q)]
    count = len(exported_questions)
    # 当前行全部有效也不足以证明完整：题号和已保存题数必须相互印证。
    v2 = (
        any(q.get("capture_version") == "active_response_v2" for q in questions)
        if questions
        else "recorded_question_count" in raw
    )
    scored = [q for q in questions if q.get("result_type") != "interrupted"]
    score_count = len(scored)
    expected_count = raw.get("recorded_question_count" if v2 else "completed_units")
    authoritative = (
        count == len(questions)
        and (
            not v2
            or (
                all(q.get("capture_version") == "active_response_v2" for q in questions)
                and type(raw.get("completed_units")) is int
                and raw["completed_units"] == score_count
                and all(q.get("result_type") != "interrupted" for q in questions[:-1])
            )
        )
        and (count > 0 or record.client_session_id is not None)
        and type(expected_count) is int
        and 0 <= expected_count <= MAX_QUESTIONS
        and expected_count == count
        and all(
            type(q.get("question_index")) is int and q["question_index"] == index
            for index, q in enumerate(questions, start=1)
        )
    )
    if authoritative:
        correct_count = sum(q["is_correct"] for q in scored)
        authoritative = all(
            key not in source or (type(source[key]) is int and source[key] == expected)
            for source, key, expected in (
                (raw, "correct_units", correct_count),
                (form, "error_count", score_count - correct_count),
            )
        )
    completed = score_count if authoritative else number(raw.get("completed_units"))
    correct = (
        sum(q["is_correct"] for q in scored) if authoritative else number(raw.get("correct_units"))
    )
    errors = score_count - correct if authoritative else number(form.get("error_count"))
    # 与规范写入的权威汇总使用同一舍入口径；生理均值另用 HALF_UP。
    accuracy = (
        (round(correct * 100 / score_count, 1) if score_count else 0)
        if authoritative
        else number(form.get("accuracy_rate"))
    )
    if authoritative:
        completeness = "规范逐题完整列表"
    elif count:
        completeness = "仅导出有效计时题目，逐题数据不完整；摘要保留原值"
    else:
        completeness = "无可导出的有效计时题目；摘要保留原值"
    if action.action_library_item.source_key == "game-audiovisual-puzzle":
        accuracy = None
        completeness += "；拼图正确率不适用"
    difficulty = form.get("difficulty") if isinstance(form.get("difficulty"), str) else None
    adjusted = raw.get("difficulty_adjusted")
    if not isinstance(adjusted, bool):
        adjusted = difficulty != action.difficulty if difficulty is not None else None
    ended_early = raw.get("ended_early")
    ended_by = raw.get("ended_by")
    return {
        "游戏得分": record.score,
        "实际难度": difficulty,
        "处方难度": action.difficulty or None,
        "是否调整难度": adjusted,
        "完成题数": completed,
        "正确题数": correct,
        "错误题数": errors,
        "正确率（%）": accuracy,
        "是否提前结束": ended_early if isinstance(ended_early, bool) else None,
        "结束方式": {"timer": "自动结束", "manual": "主动结束", "user": "主动结束"}.get(
            ended_by, ended_by if isinstance(ended_by, str) else None
        ),
        "逐题记录数": count,
        "规范计时题数": count,
        "逐题完整性": completeness,
    }


def session_row(record, pp, video, window, questions, stats):
    action = record.prescription_action
    is_game = action.internal_type_snapshot == "game"
    seconds, precision = duration_fields(record, video, is_game)
    start = video.training_started_at if video and not is_game else None
    end = video.training_ended_at if video and not is_game else None
    row = {
        "患者编号": pp.patient_id,
        "患者姓名": pp.patient.name,
        "脱敏手机号": phone_masked(pp.patient.phone),
        "项目编号": pp.project_id,
        "项目名称": pp.project.name,
        "项目患者编号": pp.pk,
        "当前分组名称": pp.group.name if pp.group_id else None,
        "训练记录编号": record.pk,
        "训练日期": record.training_date,
        "提交时间": record.created_at,
        "处方编号": record.prescription_id,
        "处方版本": record.prescription.version,
        "动作编号": action.pk,
        "动作编码": action.action_library_item.source_key,
        "动作名称": action.action_name_snapshot,
        "训练类型": action.training_type_snapshot,
        "完成状态": record.get_status_display(),
        "计划时长（秒）": plan_seconds(action, video),
        "实际训练时长（秒）": seconds,
        "时长来源与精度": precision,
        "训练开始时间": start,
        "实际结束时间": end,
        "起止时间可用性": "可用"
        if start and end
        else ("部分可用" if start or end else "未采集可靠起止时间"),
        "备注": record.note,
        "窗口开始": window[0] if window else None,
        "窗口结束": window[1] if window else None,
        "窗口口径": WINDOW_DESCRIPTION if window else "无可用观察窗口",
    }
    row.update(game_summary(record, questions, is_game))
    row.update(stats)
    return row


def quality_json(data):
    data = object_data(data)
    # Only supported business values, never arbitrary nested inference structures.
    clean = {}
    for key in QUALITY_FIELDS:
        value = data.get(key)
        if key == "confidence_level" and (
            isinstance(value, str) or finite_json_number(value) is not None
        ):
            clean[key] = value
        elif key == "doctor_note" and isinstance(value, str):
            clean[key] = value
        elif key == "quality_flags" and isinstance(value, list):
            clean[key] = [item for item in value if isinstance(item, str)]
        elif key in ("subject_coverage_ratio", "ambiguity_ratio") and number(value) is not None:
            clean[key] = value
    return (
        json.dumps(
            clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        if clean
        else None
    )


def motion_row(record, video):
    action = record.prescription_action
    supported = get_analysis_profile(action.action_library_item.source_key) is not None
    status = record.export_analysis_status
    analysis_status = {
        "pending": "等待分析",
        "running": "分析中",
        "succeeded": "分析成功",
        "failed": "分析失败",
    }.get(status, "未分析" if supported else "不支持AI")
    is_doctor = record.motion_result_source == "doctor"
    return {
        "训练记录编号": record.pk,
        "训练日期": record.training_date,
        "动作编码": action.action_library_item.source_key,
        "动作名称": action.action_name_snapshot,
        "处方时长（秒）": plan_seconds(action, video),
        "首次录像开始": video.training_started_at if video else None,
        "实际结束": video.training_ended_at if video else None,
        "实际训练秒数": duration_fields(record, video, False)[0],
        "视频文件秒数": video.duration_seconds if video else None,
        "动作总次数": record.motion_total_count,
        "标准次数": record.motion_standard_count,
        "非标准次数": record.motion_nonstandard_count,
        "结果来源": {"doctor": "医生", "algorithm": "算法"}.get(record.motion_result_source),
        "结果更新时间": record.motion_result_updated_at,
        "修订医生编号": record.motion_result_updated_by_id if is_doctor else None,
        "修订医生姓名": record.motion_result_updated_by.name
        if is_doctor and record.motion_result_updated_by
        else None,
        "分析状态": analysis_status,
        "分析失败说明": ANALYSIS_FAILURE_MESSAGE if status == "failed" else None,
        "动作质量详情1": quality_json(record.motion_quality_data),
        "录像编号": video.pk if video else None,
        "录像处理状态": video.get_status_display() if video else None,
        "备注": record.note,
    }
