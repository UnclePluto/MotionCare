#!/usr/bin/env bash
set -euo pipefail
umask 077

cleanup_input() {
  if [[ -e "${video_path}" && ! -L "${video_path}" ]]; then
    unlink "${video_path}"
  fi
}

_run_benchmark_after_root_gate() {
  analysis_root="$1"
  shift
  video_path="${analysis_root}/input/IMG_0383_SDR_5min.mp4"

  trap cleanup_input EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM HUP

  if [[ "$#" -ne 2 ]]; then
    echo "用法: $0 COMMIT RUN_ID" >&2
    exit 2
  fi

  implementation_commit="$1"
  run_id="$2"
  report_path="${analysis_root}/reports/pp-tinypose-v2-${run_id}.json"
  summary_path="${analysis_root}/reports/pp-tinypose-v2-${run_id}.txt"

  if [[ ! "${implementation_commit}" =~ ^[a-f0-9]{7,40}$ ]]; then
    echo "COMMIT 格式无效" >&2
    exit 2
  fi
  if [[ ! "${run_id}" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
    echo "RUN_ID 格式无效" >&2
    exit 2
  fi
  if [[ ! -f "${video_path}" || -L "${video_path}" ]]; then
    echo "输入视频不存在或不是普通文件" >&2
    exit 1
  fi

  cd "${analysis_root}/app/backend"
  runuser -u motioncare-analysis -- env \
    PADDLE_PDX_CACHE_HOME="${analysis_root}/model-cache" \
    TMPDIR="${analysis_root}/tmp" \
    "${analysis_root}/venv/bin/python" \
    "${analysis_root}/app/backend/manage.py" \
    run_pose_smoke_benchmark \
    --video "${video_path}" \
    --report "${report_path}" \
    --summary "${summary_path}" \
    --expected-sha256 f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd \
    --git-commit "${implementation_commit}" \
    --manual-total-count 90 \
    --delete-input

  printf '%s\n' "${report_path}" "${summary_path}"
}

_run_benchmark_main() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "必须以 root 执行" >&2
    exit 1
  fi
  _run_benchmark_after_root_gate "/opt/motioncare-analysis" "$@"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  _run_benchmark_main "$@"
fi
