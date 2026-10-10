from django.test import override_settings
from pathlib import Path
import subprocess

import pytest
from rest_framework.test import APIClient

from apps.crf.models import CrfExport
from apps.studies.models import StudyProject


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_crf_preview_allowed_for_completed_project(doctor, project_patient):
    project = project_patient.project
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])

    response = _client(doctor).get(f"/api/crf/project-patients/{project_patient.id}/preview/")

    assert response.status_code == 200, response.content
    assert response.data["project_patient_id"] == project_patient.id
    assert response.data["project"]["name"] == project.name


@pytest.mark.django_db
def test_crf_export_allowed_for_completed_project(doctor, project_patient, tmp_path, monkeypatch):
    class ConverterProcessStub:
        def __init__(self, command, **kwargs):
            self.command = command

        def wait(self, timeout=None):
            command = self.command
            folder = Path(command[command.index("--outdir") + 1])
            (folder / Path(command[-1]).with_suffix(".pdf").name).write_bytes(b"%PDF-1.7\nfixture")
            return 0

    monkeypatch.setattr(subprocess, "Popen", ConverterProcessStub)
    project = project_patient.project
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])
    root_dir = tmp_path
    media_root = root_dir / "media"
    export_dir = media_root / "crf_exports"
    export_dir.mkdir(parents=True)

    with override_settings(ROOT_DIR=root_dir, MEDIA_ROOT=media_root, CRF_EXPORT_DIR=export_dir):
        response = _client(doctor).post(f"/api/crf/project-patients/{project_patient.id}/export/")

    assert response.status_code == 200, response.content
    assert CrfExport.objects.filter(project_patient=project_patient).exists()
    assert response.data["docx_file"]

    assert response.data["pdf_file"]
    export = CrfExport.objects.get(project_patient=project_patient)
    assert (media_root / export.docx_file.name).is_file()
    assert (media_root / export.pdf_file.name).read_bytes().startswith(b"%PDF-")
