from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class CrfExport(TimeStampedModel):
    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="crf_exports",
    )
    exported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    template_version = models.CharField(max_length=40)
    missing_fields = models.JSONField(default=list)
    docx_file = models.FileField(upload_to="crf_exports/", null=True, blank=True)
    pdf_file = models.FileField(upload_to="crf_exports/", null=True, blank=True)

