import logging
from pathlib import Path
import shutil
from tempfile import mkdtemp

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.training.tracking import accessible_project_patients

from .models import CrfExport
from .serializers import CrfExportSerializer
from .services.aggregate import build_crf_preview
from .services.export_docx import export_preview_to_docx
from .services.export_pdf import convert_docx_to_pdf

logger = logging.getLogger(__name__)


class CrfViewSet(ViewSet):
    permission_classes = [IsAdminOrDoctor]

    def get_project_patient(self, request, pk):
        return get_object_or_404(accessible_project_patients(request.user), pk=pk)

    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request, pk=None):
        return Response(build_crf_preview(self.get_project_patient(request, pk)))

    @action(detail=True, methods=["post"], url_path="export")
    def export(self, request, pk=None):
        project_patient = self.get_project_patient(request, pk)
        preview = build_crf_preview(project_patient)
        work_dir = None
        try:
            media_root = Path(settings.MEDIA_ROOT).resolve()
            export_dir = Path(settings.CRF_EXPORT_DIR).resolve()
            # FileField URLs must resolve within the configured media storage.
            export_dir.relative_to(media_root)
            export_dir.mkdir(parents=True, exist_ok=True)
            work_dir = Path(mkdtemp(prefix=f"crf-{project_patient.id}-", dir=export_dir))
            docx = export_preview_to_docx(preview, work_dir / f"crf-{project_patient.id}.docx")
            pdf = convert_docx_to_pdf(docx, work_dir)
            with transaction.atomic():
                export = CrfExport.objects.create(
                    project_patient=project_patient,
                    exported_by=request.user,
                    template_version=preview["template_revision"],
                    missing_fields=preview["missing_fields"],
                    docx_file=str(docx.relative_to(media_root)),
                    pdf_file=str(pdf.relative_to(media_root)),
                )
                payload = CrfExportSerializer(export).data
        except Exception:
            logger.exception("CRF 导出失败，项目患者 ID=%s", project_patient.id)
            if work_dir is not None:
                try:
                    shutil.rmtree(work_dir)
                except OSError:
                    logger.exception("CRF 导出清理失败，项目患者 ID=%s", project_patient.id)
            return Response(
                {"detail": "导出失败，文件未生成。请稍后重试或联系管理员。"}, status=503
            )
        return Response(payload)
