from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
from urllib.parse import urlparse

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crf.models import CrfExport


@pytest.fixture(autouse=True)
def isolated_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.CRF_EXPORT_DIR = settings.MEDIA_ROOT / "crf_exports"


class ConverterProcessStub:
    """External-process boundary only; real file generation and API remain active."""

    pid = 99999999

    def __init__(self, command, handler, kwargs):
        self.command = command
        self.handler = handler
        self.kwargs = kwargs
        self.returncode = None
        self.waits = 0

    def wait(self, timeout=None):
        self.waits += 1
        if self.waits == 1:
            self.returncode = self.handler(self.command, **self.kwargs, timeout=timeout).returncode
        elif self.returncode is None:
            self.returncode = -15
        return self.returncode


def install_converter_stub(monkeypatch, handler):
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda command, **kwargs: ConverterProcessStub(command, handler, kwargs),
    )
    # Stub PIDs never identify actual processes. Real lifecycle cases below use neither patch.
    monkeypatch.setattr("apps.crf.services.export_pdf.os.killpg", lambda pid, sig: None)


@pytest.fixture
def export_settings(settings, tmp_path):
    # Deliberately different from ROOT_DIR/media: FileField must use MEDIA_ROOT.
    settings.MEDIA_ROOT = tmp_path / "custom-media"
    settings.CRF_EXPORT_DIR = settings.MEDIA_ROOT / "nested" / "exports"
    return settings


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def fake_success(command, **kwargs):
    out_dir = Path(command[command.index("--outdir") + 1])
    source = Path(command[-1])
    assert source.is_file()
    (out_dir / source.with_suffix(".pdf").name).write_bytes(
        b"%PDF-1.7\ncontrolled converter fixture\n"
    )
    return subprocess.CompletedProcess(command, 0, "", "")


@pytest.mark.django_db
def test_export_records_actual_version_and_both_files(
    doctor, project_patient, export_settings, monkeypatch
):
    install_converter_stub(monkeypatch, fake_success)
    project_patient.project.crf_template_version = "obsolete-project-config"
    project_patient.project.save(update_fields=["crf_template_version"])
    response = client_for(doctor).post(f"/api/crf/project-patients/{project_patient.id}/export/")
    assert response.status_code == 200, response.content
    record = CrfExport.objects.get()
    assert record.template_version == response.data["template_version"] == "1.1"
    assert record.docx_file and record.pdf_file
    assert Path(record.docx_file.path).is_file()
    pdf_path = Path(record.pdf_file.path)
    assert pdf_path.read_bytes().startswith(b"%PDF-")
    assert pdf_path.is_relative_to(export_settings.CRF_EXPORT_DIR)
    assert record.docx_file.name.startswith("nested/exports/")
    assert urlparse(response.data["pdf_file"]).path.startswith("/media/nested/exports/")


@pytest.mark.django_db
@pytest.mark.parametrize("failure", ["timeout", "exit", "missing", "invalid", "unavailable"])
def test_failed_conversion_leaves_no_success_log_or_files(
    doctor, project_patient, export_settings, monkeypatch, failure
):
    def fail(command, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        if failure == "unavailable":
            raise FileNotFoundError("missing soffice")
        if failure == "invalid":
            out_dir = Path(command[command.index("--outdir") + 1])
            (out_dir / Path(command[-1]).with_suffix(".pdf").name).write_bytes(b"not a PDF")
        return subprocess.CompletedProcess(
            command, 1 if failure == "exit" else 0, "", "conversion failed"
        )

    install_converter_stub(monkeypatch, fail)
    before_count = CrfExport.objects.count()
    response = client_for(doctor).post(f"/api/crf/project-patients/{project_patient.id}/export/")
    assert response.status_code == 503, response.content
    assert "detail" in response.data
    assert CrfExport.objects.count() == before_count
    assert not list(export_settings.CRF_EXPORT_DIR.rglob("*"))


@pytest.mark.django_db
def test_docx_generation_failure_cleans_partial_file(
    doctor, project_patient, export_settings, monkeypatch
):
    def fail(preview, output):
        output.write_bytes(b"partial docx")
        raise OSError("disk full")

    monkeypatch.setattr("apps.crf.views.export_preview_to_docx", fail)
    before_count = CrfExport.objects.count()
    response = client_for(doctor).post(f"/api/crf/project-patients/{project_patient.id}/export/")
    assert response.status_code == 503
    assert CrfExport.objects.count() == before_count
    assert not list(export_settings.CRF_EXPORT_DIR.rglob("*"))


@pytest.mark.django_db
def test_output_outside_media_is_rejected_without_files(
    doctor, project_patient, export_settings, tmp_path
):
    export_settings.CRF_EXPORT_DIR = tmp_path / "outside-media"
    response = client_for(doctor).post(f"/api/crf/project-patients/{project_patient.id}/export/")
    assert response.status_code == 503
    assert CrfExport.objects.count() == 0
    assert not export_settings.CRF_EXPORT_DIR.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["preview", "export"])
def test_scoped_outside_patient_is_not_accessible(doctor, project_patient, settings, endpoint):
    outsider = User.objects.create_user(
        phone="13800002222", password="password", role=User.Role.DOCTOR
    )
    settings.TRAINING_HEALTH_ENFORCE_ROW_SCOPE = True
    client = client_for(outsider)
    response = getattr(client, "get" if endpoint == "preview" else "post")(
        f"/api/crf/project-patients/{project_patient.id}/{endpoint}/"
    )
    assert response.status_code == 404
    assert CrfExport.objects.count() == 0


@pytest.mark.django_db
def test_default_global_doctor_and_admin_policy_is_preserved(project_patient, settings):
    outsider = User.objects.create_user(
        phone="13800002222", password="password", role=User.Role.DOCTOR
    )
    settings.TRAINING_HEALTH_ENFORCE_ROW_SCOPE = False
    url = f"/api/crf/project-patients/{project_patient.id}/preview/"
    assert client_for(outsider).get(url).status_code == 200
    settings.TRAINING_HEALTH_ENFORCE_ROW_SCOPE = True
    outsider.role = User.Role.ADMIN
    outsider.save(update_fields=["role"])
    assert client_for(outsider).get(url).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["preview", "export"])
def test_missing_patient_returns_404(doctor, endpoint):
    response = getattr(client_for(doctor), "get" if endpoint == "preview" else "post")(
        f"/api/crf/project-patients/999999/{endpoint}/"
    )
    assert response.status_code == 404


def test_converter_isolates_concurrent_workdirs_and_profiles(tmp_path, monkeypatch, settings):
    from apps.crf.services.export_pdf import convert_docx_to_pdf
    from threading import Barrier

    settings.CRF_LIBREOFFICE_BINARY = "/configured/soffice"
    source = tmp_path / "填好.docx"
    source.write_bytes(b"filled docx sentinel")
    barrier = Barrier(2)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert Path(command[-1]).read_bytes() == b"filled docx sentinel"
        barrier.wait(timeout=5)
        return fake_success(command, **kwargs)

    install_converter_stub(monkeypatch, run)
    outputs = [tmp_path / "shared-output", tmp_path / "shared-output"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda folder: convert_docx_to_pdf(source, folder, timeout_seconds=7), outputs)
        )
    assert all(p.read_bytes().startswith(b"%PDF-") for p in results)
    commands = [c for c, _ in calls]
    assert all(c[0] == "/configured/soffice" for c in commands)
    assert len({c[c.index("--outdir") + 1] for c in commands}) == 2
    assert (
        len({next(x for x in c if x.startswith("-env:UserInstallation=")) for c in commands}) == 2
    )
    assert all(kwargs["timeout"] == 7 for _, kwargs in calls)
    assert all(kwargs["start_new_session"] is True for _, kwargs in calls)
    assert all(not Path(kwargs["cwd"]).exists() for _, kwargs in calls)
    assert [p.name for p in outputs[0].iterdir()] == ["填好.pdf"]


def test_converter_accepts_relative_paths_and_uses_default_timeout(tmp_path, monkeypatch):
    from apps.crf.services.export_pdf import convert_docx_to_pdf

    monkeypatch.chdir(tmp_path)
    Path("filled.docx").write_bytes(b"filled source")

    def run(command, **kwargs):
        assert kwargs["timeout"] == 120
        return fake_success(command, **kwargs)

    install_converter_stub(monkeypatch, run)
    result = convert_docx_to_pdf(Path("filled.docx"), Path("relative-output"))
    assert result.read_bytes().startswith(b"%PDF-")
    assert list(Path("relative-output").iterdir()) == [Path("relative-output/filled.pdf")]


@pytest.mark.django_db
def test_log_write_failure_removes_both_generated_files(
    doctor, project_patient, export_settings, monkeypatch
):
    from django.db import IntegrityError

    install_converter_stub(monkeypatch, fake_success)

    def failed_log(**kwargs):
        raise IntegrityError("controlled log failure")

    monkeypatch.setattr(CrfExport.objects, "create", failed_log)
    before_count = CrfExport.objects.count()
    response = client_for(doctor).post(f"/api/crf/project-patients/{project_patient.id}/export/")
    assert response.status_code == 503
    assert CrfExport.objects.count() == before_count
    assert not list(export_settings.CRF_EXPORT_DIR.rglob("*"))


@pytest.mark.parametrize("stubborn_launcher", [False, True])
def test_timeout_terminates_real_descendant_without_killing_unrelated_process(
    tmp_path, settings, stubborn_launcher
):
    """An actual launcher and worker survive run(timeout) unless the group is stopped."""
    import os
    import signal
    import sys
    import time

    from apps.crf.services.export_pdf import CrfPdfConversionError, convert_docx_to_pdf

    worker_pid_file = tmp_path / "worker.pid"
    launcher = tmp_path / "converter-launcher"
    launcher.write_text(
        f"#!{sys.executable}\n"
        "import signal, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "worker = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        f"Path({str(worker_pid_file)!r}).write_text(str(worker.pid))\n"
        "def stop(signum, frame):\n"
        "    worker.wait(timeout=2)\n"
        f"    if {stubborn_launcher!r}:\n"
        "        while True: time.sleep(1)\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "worker.wait()\n"
    )
    launcher.chmod(0o755)
    settings.CRF_LIBREOFFICE_BINARY = str(launcher)
    source = tmp_path / "filled.docx"
    source.write_bytes(b"already filled source")
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )
    worker_pid = None
    try:
        started = time.monotonic()
        with pytest.raises(CrfPdfConversionError, match="超时"):
            convert_docx_to_pdf(source, tmp_path / "out", timeout_seconds=1)
        elapsed = time.monotonic() - started
        assert elapsed < 5, elapsed
        worker_pid = int(worker_pid_file.read_text())
        try:
            os.kill(worker_pid, 0)
            alive = True
        except ProcessLookupError:
            alive = False
        assert not alive, f"converter child {worker_pid} survived its timeout"
        assert unrelated.poll() is None
        assert not list((tmp_path / "out").iterdir())
    finally:
        # Scoped test cleanup also covers the expected RED against old production code.
        if worker_pid is None and worker_pid_file.exists():
            worker_pid = int(worker_pid_file.read_text())
        if worker_pid is not None:
            try:
                os.kill(worker_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        unrelated.terminate()
        unrelated.wait(timeout=5)


@pytest.mark.django_db
def test_cleanup_error_preserves_failure_response_and_both_diagnostics(
    doctor, project_patient, export_settings, monkeypatch, caplog
):
    import shutil

    original_cleanup = shutil.rmtree

    def fail_docx(preview, output):
        output.write_bytes(b"partial docx")
        raise OSError("controlled original disk failure")

    def fail_cleanup(path):
        raise PermissionError("controlled cleanup failure")

    monkeypatch.setattr("apps.crf.views.export_preview_to_docx", fail_docx)
    monkeypatch.setattr("apps.crf.views.shutil.rmtree", fail_cleanup)
    before_count = CrfExport.objects.count()
    try:
        response = client_for(doctor).post(
            f"/api/crf/project-patients/{project_patient.id}/export/"
        )
        assert response.status_code == 503
        assert "导出失败" in response.data["detail"]
        assert CrfExport.objects.count() == before_count
        assert "controlled original disk failure" in caplog.text
        assert "controlled cleanup failure" in caplog.text
    finally:
        if export_settings.CRF_EXPORT_DIR.exists():
            original_cleanup(export_settings.CRF_EXPORT_DIR)
