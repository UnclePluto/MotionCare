"""Convert the filled original CRF, with an isolated bounded LibreOffice process."""

import os
from pathlib import Path
import signal
import shutil
import subprocess
from tempfile import TemporaryDirectory

from django.conf import settings


class CrfPdfConversionError(RuntimeError):
    pass


def _terminate_process_group(process: subprocess.Popen) -> None:
    # start_new_session makes this request's leader PID its private process-group ID.
    # Give the launcher a bounded chance to reap workers, then kill any survivors.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def convert_docx_to_pdf(docx_path: Path, output_dir: Path, *, timeout_seconds: int = 120) -> Path:
    docx_path = Path(docx_path)
    output_dir = Path(output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".crf-pdf-", dir=output_dir) as temporary:
            work_dir = Path(temporary)
            source = work_dir / docx_path.name
            shutil.copyfile(docx_path, source)
            converted_dir = work_dir / "converted"
            converted_dir.mkdir()
            command = [
                settings.CRF_LIBREOFFICE_BINARY,
                f"-env:UserInstallation={(work_dir / 'profile').as_uri()}",
                "--headless",
                "--convert-to",
                "pdf:writer_pdf_Export",
                "--outdir",
                str(converted_dir),
                str(source),
            ]
            process = subprocess.Popen(
                command,
                cwd=work_dir,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                # Stop/reap the whole private group before TemporaryDirectory cleanup.
                _terminate_process_group(process)
                raise CrfPdfConversionError("PDF 转换超时，请稍后重试") from exc
            converted = converted_dir / source.with_suffix(".pdf").name
            if returncode != 0 or not converted.is_file():
                raise CrfPdfConversionError("PDF 转换失败，未生成有效文件")
            with converted.open("rb") as handle:
                if handle.read(5) != b"%PDF-":
                    raise CrfPdfConversionError("PDF 转换未生成有效文件")
            output = output_dir / converted.name
            converted.replace(output)
            return output
    except OSError as exc:
        raise CrfPdfConversionError("PDF 转换服务暂不可用") from exc
