"""同步下载协调：授权、独立审计、只读一致性快照及临时文件移交。"""

import logging
import time
from zoneinfo import ZoneInfo

from django.db import DatabaseError, connection, transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrDoctor
from ._export_deadline import StatementBudget
from .export_rows import ExportDeadlineError, ExportLimitError, prepare_export_rows
from .export_scope import authorize_export, resolve_export_filter
from .export_workbook import build_training_detail_workbook
from .models import TrainingDetailExportLog

SHANGHAI = ZoneInfo("Asia/Shanghai")
EXPORT_SECONDS = 60
logger = logging.getLogger(__name__)


class _AuditError(Exception):
    pass


def _filters_json(filters):
    result = {"project_patient": filters.project_patient_id, "range": filters.range_value}
    if filters.start_date is not None:
        result["start_date"] = filters.start_date.isoformat()
    if filters.end_date is not None:
        result["end_date"] = filters.end_date.isoformat()
    return result


def _filename(project_patient, filters, generated_at):
    date_range = (
        "全部历史"
        if filters.range_value == "all"
        else f"{filters.start_date:%Y%m%d}-{filters.end_date:%Y%m%d}"
    )
    return f"{project_patient.patient_id}_{project_patient.project_id}_训练明细_{date_range}_{generated_at.astimezone(SHANGHAI):%Y%m%d_%H%M%S}.xlsx"


def _error_details(exc):
    codes = TrainingDetailExportLog.ErrorCode
    if isinstance(exc, ExportLimitError):
        return 400, "导出数据过多，请缩小日期范围", codes.LIMIT_EXCEEDED
    if isinstance(exc, ExportDeadlineError) or (
        isinstance(exc, DatabaseError) and getattr(exc.__cause__, "sqlstate", None) == "57014"
    ):
        return 503, "导出生成超时，请缩小日期范围", codes.DEADLINE_EXCEEDED
    if isinstance(exc, Http404):
        return 404, "未找到。", codes.SCOPE_CHANGED
    return (
        500,
        "导出失败，请重试",
        codes.AUDIT_FAILED if isinstance(exc, _AuditError) else codes.GENERATION_FAILED,
    )


class TrackingPatientExportView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, patient_id):
        generated_at = timezone.now()
        filters = resolve_export_filter(
            request.data, today=generated_at.astimezone(SHANGHAI).date()
        )
        project_patient = authorize_export(
            request.user, patient_id=patient_id, project_patient_id=filters.project_patient_id
        )
        try:
            audit = TrainingDetailExportLog.objects.create(
                format_version="training_detail_v2",
                operator=request.user,
                patient_id_snapshot=patient_id,
                project_id_snapshot=project_patient.project_id,
                project_patient_id_snapshot=project_patient.pk,
                filters=_filters_json(filters),
                started_at=generated_at,
            )
        except Exception:
            logger.error("训练明细导出审计创建失败")
            return Response({"detail": "导出失败，请重试"}, status=500)
        deadline = time.monotonic() + EXPORT_SECONDS
        rows = handle = None
        try:
            if time.monotonic() >= deadline:
                raise ExportDeadlineError()
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                with StatementBudget(deadline=deadline):
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT transaction_timestamp()")
                        snapshot_at = cursor.fetchone()[0]
                    project_patient = authorize_export(
                        request.user,
                        patient_id=patient_id,
                        project_patient_id=filters.project_patient_id,
                    )
                    rows = prepare_export_rows(
                        project_patient=project_patient, filters=filters, deadline=deadline
                    )
                    rows.metadata.update(
                        snapshot_at=snapshot_at,
                        generated_at=generated_at,
                        operator=request.user.name,
                        operator_id=request.user.pk,
                    )
            handle = build_training_detail_workbook(rows, deadline=deadline)
            audit.status = TrainingDetailExportLog.Status.SUCCEEDED
            audit.finished_at = timezone.now()
            audit.row_counts = dict(rows.row_counts)
            try:
                audit.save(update_fields=["status", "finished_at", "row_counts"])
            except Exception as exc:
                raise _AuditError() from exc
            response = FileResponse(
                handle,
                as_attachment=True,
                filename=_filename(project_patient, filters, generated_at),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Cache-Control"] = "no-store"
            handle = None  # FileResponse now owns this handle, including disconnect/close cleanup.
            return response
        except Exception as exc:
            status_code, message, code = _error_details(exc)
            audit.status = TrainingDetailExportLog.Status.FAILED
            audit.finished_at = timezone.now()
            audit.error_code = code
            try:
                audit.save(update_fields=["status", "finished_at", "error_code"])
            except Exception:
                logger.error("训练明细导出失败审计保存失败")
                return Response({"detail": "导出失败，请重试"}, status=500)
            return Response({"detail": message}, status=status_code)
        finally:
            if handle is not None:
                handle.close()
            if rows is not None:
                rows.close()
