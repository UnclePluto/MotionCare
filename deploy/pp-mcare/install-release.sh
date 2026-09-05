#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly ANALYSIS_ROOT="/opt/motioncare-analysis"
readonly SERVICE_USER="motioncare-analysis"
readonly CONTRACT_WHEEL="motion_analysis_contract-0.1.0-py3-none-any.whl"
readonly WORKER_WHEEL="pp_mcare-0.1.0-py3-none-any.whl"

_fail() {
  printf '%s\n' "$1" >&2
  return 1
}

_require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    _fail "必须以 root 执行"
  fi
}

_validate_release_name() {
  local release_name="$1"
  if [[ ! "${release_name}" =~ ^[a-f0-9]{7,40}$ ]]; then
    printf '%s\n' "发布标识格式无效" >&2
    return 2
  fi
}

_validate_archive_members() {
  local archive_path="$1"
  python3.12 - "${archive_path}" <<'PY'
import os
import stat
import sys
import tarfile
from pathlib import PurePosixPath

archive_path = sys.argv[1]
identity = os.lstat(archive_path)
if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1:
    raise SystemExit("发布归档必须是单链接普通文件")

seen = set()
file_count = 0
expanded_size = 0
with tarfile.open(archive_path, mode="r:gz") as archive:
    for member in archive:
        path = PurePosixPath(member.name)
        if (
            not member.name
            or path.is_absolute()
            or ".." in path.parts
            or "." in path.parts
            or member.name in seen
            or not (member.isdir() or member.isreg())
        ):
            raise SystemExit("发布归档包含不安全成员")
        seen.add(member.name)
        file_count += 1
        expanded_size += member.size
        if file_count > 10_000 or expanded_size > 4 * 1024**3:
            raise SystemExit("发布归档超出安全上限")
PY
}

_extract_archive() {
  local archive_path="$1"
  local destination="$2"
  python3.12 - "${archive_path}" "${destination}" <<'PY'
import os
import stat
import sys
import tarfile
from pathlib import Path, PurePosixPath

archive_path, destination = sys.argv[1:]
root = Path(destination)
root_identity = root.lstat()
if not stat.S_ISDIR(root_identity.st_mode) or root.is_symlink():
    raise SystemExit("候选发布目录无效")

seen = set()
file_count = 0
expanded_size = 0
with tarfile.open(archive_path, mode="r:gz") as archive:
    members = archive.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if (
            not member.name
            or path.is_absolute()
            or ".." in path.parts
            or "." in path.parts
            or member.name in seen
            or not (member.isdir() or member.isreg())
        ):
            raise SystemExit("发布归档包含不安全成员")
        seen.add(member.name)
        file_count += 1
        expanded_size += member.size
        if file_count > 10_000 or expanded_size > 4 * 1024**3:
            raise SystemExit("发布归档超出安全上限")

    for member in members:
        target = root.joinpath(*PurePosixPath(member.name).parts)
        if member.isdir():
            target.mkdir(mode=0o750, parents=True, exist_ok=True)
            os.chmod(target, 0o750)
            continue
        target.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        source = archive.extractfile(member)
        if source is None:
            raise SystemExit("发布归档成员无法读取")
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        try:
            while chunk := source.read(1024 * 1024):
                view = memoryview(chunk)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise SystemExit("发布归档成员写入失败")
                    view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
            source.close()
PY
}

_validate_artifact_manifest() {
  local candidate="$1"
  local release_name="$2"
  python3.12 - "${candidate}" "${release_name}" "${CONTRACT_WHEEL}" "${WORKER_WHEEL}" <<'PY'
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

candidate, release_name, contract_name, worker_name = sys.argv[1:]
root = Path(candidate)
manifest_path = root / "artifact-manifest.json"
try:
    manifest_identity = manifest_path.lstat()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise SystemExit("构建产物清单无法读取") from exc
expected_keys = {"manifest_version", "git_commit", "artifacts"}
if (
    not stat.S_ISREG(manifest_identity.st_mode)
    or manifest_identity.st_nlink != 1
    or not isinstance(payload, dict)
    or set(payload) != expected_keys
    or payload["manifest_version"] != "1"
    or not isinstance(payload["git_commit"], str)
    or len(payload["git_commit"]) != 40
    or any(character not in "0123456789abcdef" for character in payload["git_commit"])
    or not payload["git_commit"].startswith(release_name)
    or set(payload["artifacts"] if isinstance(payload["artifacts"], dict) else {})
    != {contract_name, worker_name}
):
    raise SystemExit("构建产物清单无效")

for filename, expected_hash in payload["artifacts"].items():
    path = root / "artifacts" / filename
    identity = path.lstat()
    if (
        not stat.S_ISREG(identity.st_mode)
        or identity.st_nlink != 1
        or not isinstance(expected_hash, str)
        or len(expected_hash) != 64
        or any(character not in "0123456789abcdef" for character in expected_hash)
    ):
        raise SystemExit("构建产物身份无效")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_hash:
        raise SystemExit("构建产物哈希不匹配")
PY
}

_validate_current() {
  local current="${ANALYSIS_ROOT}/current"
  local resolved
  [[ ! -e "${current}" && ! -L "${current}" ]] && return 0
  [[ -L "${current}" ]] || _fail "current 不是符号链接"
  resolved="$(readlink -f -- "${current}")"
  [[ "${resolved}" == "${ANALYSIS_ROOT}/releases/"* && -d "${resolved}" ]] \
    || _fail "current 指向不受信任目标"
}

_write_release_manifest() {
  local candidate="$1"
  local release_name="$2"
  local worker_hash="$3"
  local contract_hash="$4"
  "${candidate}/.venv/bin/python" - "${candidate}" "${release_name}" \
    "${worker_hash}" "${contract_hash}" <<'PY'
import json
import os
import sys
from pathlib import Path

import pp_mcare
from pp_mcare.regression import _distribution_content_sha256

candidate, release_name, worker_hash, contract_hash = sys.argv[1:]
package_root = Path(pp_mcare.__file__).resolve().parent
payload = {
    "manifest_version": "1",
    "package_name": "pp-mcare",
    "package_version": "0.1.0",
    "installed_distribution_sha256": _distribution_content_sha256(package_root),
    "wheel_sha256": worker_hash,
    "contract_wheel_sha256": contract_hash,
    "git_commit": json.loads(
        (Path(candidate) / "artifact-manifest.json").read_text(encoding="utf-8")
    )["git_commit"],
    "release_name": release_name,
}
target = Path(candidate) / "release-manifest.json"
descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
with os.fdopen(descriptor, "w", encoding="utf-8") as output:
    json.dump(payload, output, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    output.write("\n")
    output.flush()
    os.fsync(output.fileno())
PY
}

_install_release() {
  local archive_path="$1"
  local release_name="$2"
  local candidate final failed link_next worker_hash contract_hash
  local archive_metadata archive_uid archive_mode archive_links

  _validate_release_name "${release_name}"
  _require_root
  [[ -f "${archive_path}" && ! -L "${archive_path}" ]] || _fail "发布归档无效"
  archive_metadata="$(stat -c '%u:%a:%h' -- "${archive_path}")"
  IFS=: read -r archive_uid archive_mode archive_links <<< "${archive_metadata}"
  [[ "${archive_uid}" == "0" && "${archive_links}" == "1" ]] \
    || _fail "发布归档所有权或链接数不安全"
  (( (8#${archive_mode} & 8#022) == 0 )) || _fail "发布归档不能由组或其他用户写入"
  _validate_archive_members "${archive_path}"
  _validate_current
  [[ -d "${ANALYSIS_ROOT}/releases" && ! -L "${ANALYSIS_ROOT}/releases" ]] \
    || _fail "发布根目录无效"

  final="${ANALYSIS_ROOT}/releases/${release_name}"
  [[ ! -e "${final}" && ! -L "${final}" ]] || _fail "该发布已存在"
  candidate="${ANALYSIS_ROOT}/releases/.${release_name}.candidate.$$"
  failed="${ANALYSIS_ROOT}/failed/${release_name}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
  link_next="${ANALYSIS_ROOT}/.current.next.$$"
  [[ ! -e "${candidate}" && ! -L "${candidate}" ]] || _fail "候选发布路径冲突"
  [[ ! -e "${failed}" && ! -L "${failed}" ]] || _fail "失败诊断路径冲突"
  [[ ! -e "${link_next}" && ! -L "${link_next}" ]] || _fail "current 临时路径冲突"
  install -d -m 0750 -o root -g "${SERVICE_USER}" "${candidate}"

  _preserve_failed_candidate() {
    if [[ -d "${candidate}" && ! -L "${candidate}" ]]; then
      mv -- "${candidate}" "${failed}"
    fi
    if [[ -L "${link_next}" ]]; then
      unlink -- "${link_next}"
    fi
  }
  trap _preserve_failed_candidate ERR INT TERM HUP

  _extract_archive "${archive_path}" "${candidate}"
  _validate_artifact_manifest "${candidate}" "${release_name}"
  chmod 0750 "${candidate}/deploy/pp-mcare/bootstrap.sh" \
    "${candidate}/deploy/pp-mcare/install-release.sh" \
    "${candidate}/deploy/pp-mcare/run-regression.sh"

  python3.12 -m venv "${candidate}/.venv"
  "${candidate}/.venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir \
    "${candidate}/artifacts/${CONTRACT_WHEEL}"
  "${candidate}/.venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir \
    "${candidate}/artifacts/${WORKER_WHEEL}[inference]"
  "${candidate}/.venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir \
    'pytest>=8,<9'

  PYTHONDONTWRITEBYTECODE=1 "${candidate}/.venv/bin/python" -c \
    'import cv2; import paddle; import paddlex; import pp_mcare; import motion_analysis_contract'
  PYTHONDONTWRITEBYTECODE=1 "${candidate}/.venv/bin/python" -m pytest -q \
    "${candidate}/packages/motion_analysis_contract/tests" \
    "${candidate}/services/pp_mcare/tests"

  worker_hash="$(sha256sum "${candidate}/artifacts/${WORKER_WHEEL}" | cut -d ' ' -f 1)"
  contract_hash="$(sha256sum "${candidate}/artifacts/${CONTRACT_WHEEL}" | cut -d ' ' -f 1)"
  _write_release_manifest "${candidate}" "${release_name}" "${worker_hash}" "${contract_hash}"

  chown -R root:"${SERVICE_USER}" "${candidate}"
  find "${candidate}" -type d -exec chmod 0750 {} +
  find "${candidate}" -type f -exec chmod 0640 {} +
  find "${candidate}/.venv/bin" -maxdepth 1 -type f -exec chmod 0750 {} +
  chmod 0750 "${candidate}/deploy/pp-mcare/bootstrap.sh" \
    "${candidate}/deploy/pp-mcare/install-release.sh" \
    "${candidate}/deploy/pp-mcare/run-regression.sh"
  mv -- "${candidate}" "${final}"
  ln -s "releases/${release_name}" "${link_next}"
  mv -T -- "${link_next}" "${ANALYSIS_ROOT}/current"
  trap - ERR INT TERM HUP
  printf '%s\n' "发布已安装并切换"
}

_install_release_main() {
  if [[ "$#" -ne 2 ]]; then
    printf '%s\n' "用法: install-release.sh ARCHIVE COMMIT_SHA" >&2
    exit 2
  fi
  _install_release "$1" "$2"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  _install_release_main "$@"
fi
