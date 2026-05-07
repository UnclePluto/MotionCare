from rest_framework import serializers

from .models import CrfExport


class CrfExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = CrfExport
        fields = [
            "id",
            "project_patient",
            "exported_by",
            "template_version",
            "missing_fields",
            "docx_file",
            "pdf_file",
            "created_at",
        ]
        read_only_fields = fields

