from __future__ import annotations

from base64 import urlsafe_b64encode
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

NAME = "motion-analysis-contract"
VERSION = "0.1.0"
DIST_INFO = f"motion_analysis_contract-{VERSION}.dist-info"
SRC_ROOT = Path(__file__).resolve().parent / "src"


def _metadata() -> str:
    return "\n".join(
        [
            "Metadata-Version: 2.1",
            f"Name: {NAME}",
            f"Version: {VERSION}",
            "Summary: Pure protocol objects for the MotionCare pp-mcare independent service",
            "",
        ]
    )


def _wheel() -> str:
    return "\n".join(
        [
            "Wheel-Version: 1.0",
            "Generator: motion_analysis_contract.build_backend",
            "Root-Is-Purelib: true",
            "Tag: py3-none-any",
            "",
        ]
    )


def _record_line(path: str, data: bytes) -> str:
    digest = urlsafe_b64encode(sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"{path},sha256={digest},{len(data)}"


def _build_wheel_archive(wheel_directory: str, editable: bool) -> str:
    wheel_name = f"motion_analysis_contract-{VERSION}-py3-none-any.whl"
    wheel_path = Path(wheel_directory) / wheel_name
    pth_name = "motion_analysis_contract.pth"
    pth_bytes = (str(SRC_ROOT) + "\n").encode("utf-8")
    metadata_bytes = _metadata().encode("utf-8")
    wheel_bytes = _wheel().encode("utf-8")
    top_level_bytes = b"motion_analysis_contract\n"

    files: list[tuple[str, bytes]] = [
        (pth_name, pth_bytes) if editable else (pth_name, b""),
        (f"{DIST_INFO}/METADATA", metadata_bytes),
        (f"{DIST_INFO}/WHEEL", wheel_bytes),
        (f"{DIST_INFO}/top_level.txt", top_level_bytes),
    ]
    if not editable:
        files.extend(
            (
                str(source.relative_to(SRC_ROOT)).replace("\\", "/"),
                source.read_bytes(),
            )
            for source in SRC_ROOT.rglob("*.py")
        )

    with ZipFile(wheel_path, "w", compression=ZIP_DEFLATED) as archive:
        for path, data in files:
            if path == pth_name and not editable:
                continue
            archive.writestr(path, data)
        record_lines = [
            _record_line(path, data)
            for path, data in files
            if path != pth_name or editable
        ]
        record_lines.append(f"{DIST_INFO}/RECORD,,")
        archive.writestr(f"{DIST_INFO}/RECORD", "\n".join(record_lines) + "\n")

    return wheel_name


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    return _build_wheel_archive(wheel_directory, editable=False)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    return _build_wheel_archive(wheel_directory, editable=True)


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_editable(config_settings=None):
    return []


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    dist_info = Path(metadata_directory) / DIST_INFO
    dist_info.mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_text(_metadata(), encoding="utf-8")
    (dist_info / "WHEEL").write_text(_wheel(), encoding="utf-8")
    (dist_info / "top_level.txt").write_text("motion_analysis_contract\n", encoding="utf-8")
    (dist_info / "RECORD").write_text("", encoding="utf-8")
    return DIST_INFO


def prepare_metadata_for_build_editable(metadata_directory, config_settings=None):
    return prepare_metadata_for_build_wheel(metadata_directory, config_settings)
