#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "${EUID}" -ne 0 ]]; then
  echo "必须以 root 执行" >&2
  exit 1
fi
if [[ "$#" -ne 2 ]]; then
  echo "用法: $0 COMMIT RUN_ID" >&2
  exit 2
fi

implementation_commit="$1"
run_id="$2"
analysis_root="/opt/motioncare-analysis"
video_path="${analysis_root}/input/IMG_0383_SDR_5min.mp4"
report_path="${analysis_root}/reports/pp-tinypose-smoke-${run_id}.json"
summary_path="${analysis_root}/reports/pp-tinypose-smoke-${run_id}.txt"

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

cleanup_input() {
  if [[ -e "${video_path}" && ! -L "${video_path}" ]]; then
    unlink "${video_path}"
  fi
}
trap cleanup_input EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

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
  --delete-input

printf '%s\n' "${report_path}" "${summary_path}"
