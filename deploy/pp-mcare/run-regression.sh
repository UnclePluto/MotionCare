#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly ANALYSIS_ROOT="/opt/motioncare-analysis"
readonly SERVICE_USER="motioncare-analysis"
readonly EXPECTED_VIDEO_SHA256="f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd"
_cleanup_video_path=""

_fail() {
  printf '%s\n' "$1" >&2
  return 1
}

_require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    _fail "必须以 root 执行"
  fi
}

_cleanup_regression_input() {
  local video_path="${_cleanup_video_path}"
  if [[ -n "${video_path}" && -f "${video_path}" && ! -L "${video_path}" ]]; then
    unlink -- "${video_path}"
  fi
}

_run_regression() {
  local video_path="$1"
  local implementation_commit="$2"
  local run_id="$3"
  local report_path actual_hash metadata

  [[ "${implementation_commit}" =~ ^[a-f0-9]{7,40}$ ]] || return 2
  [[ "${run_id}" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || return 2
  [[ "${video_path}" == "${ANALYSIS_ROOT}/input/pp-mcare-${run_id}.mp4" ]] \
    || _fail "回归输入路径无效"
  [[ -f "${video_path}" && ! -L "${video_path}" ]] || _fail "回归输入不是普通文件"
  metadata="$(stat -c '%U:%G:%a:%h' -- "${video_path}")"
  [[ "${metadata}" == "${SERVICE_USER}:${SERVICE_USER}:600:1" ]] \
    || _fail "回归输入权限不安全"

  report_path="${ANALYSIS_ROOT}/reports/pp-mcare-v2-${implementation_commit}-${run_id}.json"
  [[ ! -e "${report_path}" && ! -L "${report_path}" ]] || _fail "回归报告已存在"
  actual_hash="$(sha256sum "${video_path}" | cut -d ' ' -f 1)"
  [[ "${actual_hash}" == "${EXPECTED_VIDEO_SHA256}" ]] || _fail "回归输入 SHA-256 不匹配"

  python3.12 - "${ANALYSIS_ROOT}/current/release-manifest.json" "${implementation_commit}" <<'PY'
import json
import sys
from pathlib import Path

manifest_path, release_name = sys.argv[1:]
payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
if payload.get("manifest_version") != "1" or not payload.get("git_commit", "").startswith(release_name):
    raise SystemExit("发布清单与回归标识不匹配")
PY

  _cleanup_video_path="${video_path}"
  trap _cleanup_regression_input EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM HUP
  (
    cd -- "${ANALYSIS_ROOT}/current"
    runuser -u "${SERVICE_USER}" -- env \
      PYTHONDONTWRITEBYTECODE=1 \
      PADDLE_PDX_CACHE_HOME="${ANALYSIS_ROOT}/model-cache" \
      TMPDIR="${ANALYSIS_ROOT}/tmp" \
      "${ANALYSIS_ROOT}/current/.venv/bin/python" -m pp_mcare regression \
      --video "${video_path}" \
      --manual-total-count 90 \
      --report "${report_path}"
  )
  printf '%s\n' "${report_path}"
}

_run_regression_main() {
  if [[ "$#" -ne 3 ]]; then
    printf '%s\n' "用法: run-regression.sh VIDEO COMMIT_SHA RUN_ID" >&2
    exit 2
  fi
  _require_root
  _run_regression "$1" "$2" "$3"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  _run_regression_main "$@"
fi
