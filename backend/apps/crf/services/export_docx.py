from pathlib import Path

from django.conf import settings
from docx import Document

from apps.crf.registry_loader import load_crf_registry
from apps.crf.services.docx_binding import fill_crf_document


def export_preview_to_docx(preview: dict, output_path: Path) -> Path:
    registry = load_crf_registry()
    document = fill_crf_document(Document(settings.CRF_TEMPLATE_PATH), preview, registry)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)
    return output_path
