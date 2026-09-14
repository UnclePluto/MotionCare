"""只读快照内准备导出行，完成后可在事务外重复读取私有暂存。"""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from typing import Iterator

from django.db import DatabaseError, connection
from django.db.models import Count, Max, Min, OuterRef, Subquery
from django.utils import timezone

from apps.wearables.services.training_windows import training_video_health_window
from ._export_mapping import (
    ACTIVE_DESCRIPTION,
    WINDOW_DESCRIPTION,
    has_valid_response_duration,
    motion_row,
    question_row,
    selection_rows,
    session_row,
)
from ._export_measurements import stream_measurements, summary_fields
from .export_schema import CellValue, FIELD_DEFINITIONS, SHEET_HEADERS
from .export_scope import ExportFilter
from .models import GameQuestionSelectionStep, GameQuestionResult, MotionAnalysisJob, TrainingRecord

MAX_RECORDS = 10_000
MAX_SHEET_ROWS = 200_000
MAX_TOTAL_ROWS = 500_000
RECORD_CHUNK_SIZE = 100
TEXT_CHUNK_SIZE = 32_767


class ExportLimitError(Exception):
    pass


class ExportDeadlineError(Exception):
    pass


def _encode(value):
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("导出数值必须有限")
        return {"type": "decimal", "value": str(value)}
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ValueError("不支持的导出单元格类型")


def _decode(value):
    if not isinstance(value, dict):
        return value
    return {"datetime": datetime.fromisoformat, "date": date.fromisoformat, "decimal": Decimal}[
        value["type"]
    ](value["value"])


class ExportRows:
    def __init__(self, *, deadline: float):
        self.deadline = deadline
        self._temp = TemporaryDirectory(prefix="motioncare-training-export-")
        self.directory = self._temp.name
        self._files = {}
        self._paths = {}
        self.metadata: dict = {}
        self.row_counts: dict[str, int] = dict.fromkeys(SHEET_HEADERS, 0)
        self.text_chunk_counts: dict[str, dict[str, int]] = {name: {} for name in SHEET_HEADERS}
        self.quality_chunk_count = 1
        self._total = 0
        self._closed = False
        try:
            for index, name in enumerate(SHEET_HEADERS):
                path = Path(self.directory) / f"{index}.jsonl"
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                self._files[name] = os.fdopen(descriptor, "w", encoding="utf-8")
                self._paths[name] = path
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def check_deadline(self):
        if time.monotonic() >= self.deadline:
            raise ExportDeadlineError("导出生成超时，请缩小日期范围")

    def append(self, sheet_name: str, row: dict[str, CellValue]):
        self.check_deadline()
        if self._closed:
            raise ValueError("导出行暂存已关闭")
        headers = SHEET_HEADERS[sheet_name]
        if set(row) - set(headers):
            raise ValueError("导出行包含未知字段")
        count = self.row_counts[sheet_name] + 1
        business = sheet_name != "字段说明"
        if business and (
            count > MAX_SHEET_ROWS
            or self._total + 1 > MAX_TOTAL_ROWS
            or (sheet_name == "训练场次" and count > MAX_RECORDS)
        ):
            raise ExportLimitError("导出数据过多，请缩小日期范围")
        encoded = {key: _encode(row.get(key)) for key in headers}
        self._files[sheet_name].write(
            json.dumps(encoded, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
        )
        self.row_counts[sheet_name] = count
        self._total += int(business)
        for key, value in row.items():
            if isinstance(value, str):
                chunks = max(1, math.ceil(len(value) / TEXT_CHUNK_SIZE))
                self.text_chunk_counts[sheet_name][key] = max(
                    self.text_chunk_counts[sheet_name].get(key, 1), chunks
                )
        self.quality_chunk_count = self.text_chunk_counts["运动明细"].get("动作质量详情1", 1)

    def iter_rows(self, sheet_name: str) -> Iterator[dict[str, CellValue]]:
        if self._closed:
            raise ValueError("导出行暂存已关闭")
        file = self._files[sheet_name]
        file.flush()
        with self._paths[sheet_name].open(encoding="utf-8") as source:
            for line in source:
                self.check_deadline()
                row = {key: _decode(value) for key, value in json.loads(line).items()}
                if sheet_name == "运动明细":
                    quality = row.pop("动作质量详情1")
                    for index in range(self.quality_chunk_count):
                        row[f"动作质量详情{index + 1}"] = (
                            quality[index * TEXT_CHUNK_SIZE : (index + 1) * TEXT_CHUNK_SIZE]
                            if quality is not None
                            else None
                        )
                yield row

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            for file in self._files.values():
                file.close()
        finally:
            self._temp.cleanup()


def _set_statement_deadline(rows):
    rows.check_deadline()
    milliseconds = max(1, int((rows.deadline - time.monotonic()) * 1000))
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", [f"{milliseconds}ms"])


def _records_query(project_patient, filters):
    latest_job = MotionAnalysisJob.objects.filter(training_record_id=OuterRef("pk")).order_by(
        "-created_at", "-pk"
    )
    queryset = TrainingRecord.objects.filter(project_patient_id=project_patient.pk)
    if filters.start_date is not None:
        queryset = queryset.filter(training_date__gte=filters.start_date)
    if filters.end_date is not None:
        queryset = queryset.filter(training_date__lte=filters.end_date)
    return (
        queryset.select_related(
            "prescription",
            "prescription_action",
            "prescription_action__action_library_item",
            "video",
            "motion_result_updated_by",
        )
        .annotate(export_analysis_status=Subquery(latest_job.values("status")[:1]))
        .order_by("training_date", "pk")
    )


def _questions_for_records(records, *, rows=None):
    grouped = defaultdict(list)
    question_count = 0
    question_limit = (
        MAX_SHEET_ROWS
        if rows is None
        else min(MAX_SHEET_ROWS - rows.row_counts["游戏逐题"], MAX_TOTAL_ROWS - rows._total)
    )
    step_limit = (
        MAX_SHEET_ROWS
        if rows is None
        else min(MAX_SHEET_ROWS - rows.row_counts["顺序选择明细"], MAX_TOTAL_ROWS - rows._total)
    )
    fields = (
        "id",
        "expected_step_count",
        "click_count",
        "training_record_id",
        "question_index",
        "game_code",
        "difficulty",
        "response_duration_ms",
        "is_correct",
        "result_type",
        "swap_count",
        "capture_version",
    )
    for question in (
        GameQuestionResult.objects.filter(training_record_id__in=[r.pk for r in records])
        .order_by("training_record_id", "question_index", "pk")
        .values(*fields)
        .iterator(chunk_size=500)
    ):
        question["selection_steps"] = []
        if rows is not None:
            rows.check_deadline()
        question_count += 1
        if question_count > question_limit:
            raise ExportLimitError("导出数据过多，请缩小日期范围")
        grouped[question["training_record_id"]].append(question)
    parents = {q["id"]: q for questions in grouped.values() for q in questions}
    if parents:
        step_count = 0
        for step in (
            GameQuestionSelectionStep.objects.filter(
                question__training_record_id__in=[r.pk for r in records]
            )
            .order_by("question_id", "step_index", "pk")
            .values(
                "question_id",
                "step_index",
                "selected_value",
                "expected_value",
                "response_duration_ms",
                "is_correct",
            )
            .iterator(chunk_size=500)
        ):
            step_count += 1
            if rows is not None:
                rows.check_deadline()
            if step_count > step_limit:
                raise ExportLimitError("导出数据过多，请缩小日期范围")
            parents[step.pop("question_id")]["selection_steps"].append(step)
    for questions in grouped.values():
        for index, question in enumerate(questions):
            question["_is_last"] = index == len(questions) - 1
    return grouped


def _prepare_chunk(records, project_patient, rows):
    questions = _questions_for_records(records, rows=rows)
    windows = []
    window_by_record = {}
    for record in records:
        video = getattr(record, "video", None)
        if video and record.prescription_action.internal_type_snapshot == "motion":
            window = training_video_health_window(video)
            if window:
                windows.append((record.pk, video.pk, *window))
                window_by_record[record.pk] = window
    stats = stream_measurements(patient_id=project_patient.patient_id, windows=windows, rows=rows)
    for record in records:
        video = getattr(record, "video", None)
        window = window_by_record.get(record.pk)
        record_questions = questions[record.pk]
        rows.append(
            "训练场次",
            session_row(
                record,
                project_patient,
                video,
                window,
                record_questions,
                summary_fields(stats.get(record.pk), has_window=window is not None),
            ),
        )
        if record.prescription_action.internal_type_snapshot == "game":
            for question in record_questions:
                if has_valid_response_duration(question):
                    rows.append("游戏逐题", question_row(record, question))
                    for step in selection_rows(record, question):
                        rows.append("顺序选择明细", step)
        elif record.prescription_action.internal_type_snapshot == "motion":
            rows.append("运动明细", motion_row(record, video))


def _add_explanations(rows):
    for key, value in rows.metadata.items():
        if key != "row_counts":
            rows.append("字段说明", {"分类": "导出元数据", "字段或项目": key, "说明或值": value})
    for sheet in SHEET_HEADERS:
        if sheet != "字段说明":
            rows.append(
                "字段说明",
                {"分类": "各表行数", "字段或项目": sheet, "说明或值": rows.row_counts[sheet]},
            )
    for field, definition in FIELD_DEFINITIONS.items():
        rows.append("字段说明", {"分类": "字段定义", "字段或项目": field, "说明或值": definition})
    for field, value in (
        ("规范计时口径", ACTIVE_DESCRIPTION),
        (
            "逐题导出范围",
            "仅导出具有合法有效作答时间的题目；缺失或无效计时不展示，整场训练记录保留。",
        ),
        ("观察窗口", WINDOW_DESCRIPTION),
        ("缺失含义", "缺失值留空，真实0与false保留，不插值、不补零。"),
        ("时长区别", "游戏会话/运动实际训练时长、视频文件媒体时长、处方计划时长各自独立。"),
        ("游戏时间限制", "游戏未采集可靠绝对起止时间，本期无游戏健康观察窗口。"),
        ("重叠测量", "一条测量可能关联多个窗口，可按测量记录编号去重；重复关联不是新测量。"),
        ("长文本", "超过32767字符的文本按编号分列，按列顺序拼接可还原。"),
    ):
        rows.append("字段说明", {"分类": "数据口径", "字段或项目": field, "说明或值": value})


def prepare_export_rows(*, project_patient, filters: ExportFilter, deadline: float) -> ExportRows:
    """调用者负责建立只读一致性快照，并在快照内二次授权。"""
    rows = ExportRows(deadline=deadline)
    try:
        if filters.project_patient_id != project_patient.pk:
            raise ValueError("筛选关系与授权关系不一致")
        _set_statement_deadline(rows)
        queryset = _records_query(project_patient, filters)
        aggregate = queryset.aggregate(
            count=Count("pk"), start=Min("training_date"), end=Max("training_date")
        )
        if aggregate["count"] > MAX_RECORDS:
            raise ExportLimitError("导出数据过多，请缩小日期范围")
        rows.metadata = {
            "format_version": "training_detail_v2",
            "timezone": "Asia/Shanghai",
            "snapshot_at": timezone.now(),
            "patient_id": project_patient.patient_id,
            "project_id": project_patient.project_id,
            "project_patient_id": project_patient.pk,
            "range": filters.range_value,
            "requested_start_date": filters.start_date,
            "requested_end_date": filters.end_date,
            "actual_start_date": aggregate["start"],
            "actual_end_date": aggregate["end"],
            "group_scope": "导出时当前分组，不是训练时历史分组快照",
        }
        for offset in range(0, aggregate["count"], RECORD_CHUNK_SIZE):
            _set_statement_deadline(rows)
            records = list(queryset[offset : offset + RECORD_CHUNK_SIZE])
            _prepare_chunk(records, project_patient, rows)
            rows.check_deadline()
        _add_explanations(rows)
        rows.metadata["row_counts"] = dict(rows.row_counts)
        rows.check_deadline()
        return rows
    except DatabaseError as exc:
        rows.close()
        if getattr(exc.__cause__, "sqlstate", None) == "57014":
            raise ExportDeadlineError("导出生成超时，请缩小日期范围") from exc
        raise
    except BaseException:
        rows.close()
        raise
