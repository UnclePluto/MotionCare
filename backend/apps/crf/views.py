from pathlib import Path

from django.conf import settings
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.studies.models import ProjectPatient

from .models import CrfExport
from .serializers import CrfExportSerializer
from .services.aggregate import build_crf_preview
from .services.export_docx import export_preview_to_docx


class CrfViewSet(ViewSet):
    permission_classes = [IsAdminOrDoctor]

    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request, pk=None):
        project_patient = ProjectPatient.objects.select_related("patient", "project", "group").get(pk=pk)
        return Response(build_crf_preview(project_patient))

    @action(detail=True, methods=["post"], url_path="export")
    def export(self, request, pk=None):
        project_patient = ProjectPatient.objects.select_related("patient", "project", "group").get(pk=pk)
        preview = build_crf_preview(project_patient)
        export = CrfExport.objects.create(
            project_patient=project_patient,
            exported_by=request.user,
            template_version=project_patient.project.crf_template_version,
            missing_fields=preview["missing_fields"],
        )
        output = Path(settings.CRF_EXPORT_DIR) / f"crf-{project_patient.id}-{export.id}.docx"
        export_preview_to_docx(preview, output)
        export.docx_file.name = str(output.relative_to(settings.ROOT_DIR / "media"))
        export.save(update_fields=["docx_file"])
        return Response(CrfExportSerializer(export).data)

