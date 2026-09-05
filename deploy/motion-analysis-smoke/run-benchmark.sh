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

  cd "${analysis_root}/app"
  runuser -u motioncare-analysis -- env \
    PADDLE_PDX_CACHE_HOME="${analysis_root}/model-cache" \
    TMPDIR="${analysis_root}/tmp" \
    "${analysis_root}/venv/bin/python" \
    -m pp_mcare regression \
    --video "${video_path}" \
    --report "${report_path}" \
    --manual-total-count 90

  printf '%s\n' "${report_path}"
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
