#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "必须以 root 执行" >&2
  exit 1
fi

analysis_root="${MOTIONCARE_ANALYSIS_ROOT:-/opt/motioncare-analysis}"
service_user="motioncare-analysis"
swap_path="/swapfile"

if [[ "${analysis_root}" != "/opt/motioncare-analysis" ]]; then
  echo "本次冒烟只允许 /opt/motioncare-analysis" >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates ffmpeg python3 python3-venv python3-pip

if ! id "${service_user}" >/dev/null 2>&1; then
  useradd --system \
    --home-dir "${analysis_root}" \
    --create-home \
    --shell /usr/sbin/nologin \
    "${service_user}"
fi

install -d -m 0750 -o root -g "${service_user}" "${analysis_root}"
install -d -m 0750 -o root -g "${service_user}" "${analysis_root}/app"
install -d -m 0700 -o "${service_user}" -g "${service_user}" \
  "${analysis_root}/model-cache" \
  "${analysis_root}/input" \
  "${analysis_root}/tmp" \
  "${analysis_root}/reports" \
  "${analysis_root}/logs"

if [[ ! -e "${swap_path}" ]]; then
  fallocate -l 4G "${swap_path}"
  chmod 0600 "${swap_path}"
  mkswap "${swap_path}"
fi
if [[ "$(stat -c '%s' "${swap_path}")" -ne 4294967296 ]]; then
  echo "/swapfile 已存在但不是 4 GiB，停止以避免覆盖" >&2
  exit 1
fi
if ! swapon --show=NAME --noheadings --raw | grep -Fxq "${swap_path}"; then
  swapon "${swap_path}"
fi
if ! grep -Eq '^/swapfile[[:space:]]+none[[:space:]]+swap[[:space:]]+sw' /etc/fstab; then
  printf '%s\n' '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if [[ ! -e "${analysis_root}/venv" ]]; then
  install -d -m 0700 -o "${service_user}" -g "${service_user}" \
    "${analysis_root}/venv"
fi
if [[ ! -x "${analysis_root}/venv/bin/python" ]]; then
  runuser -u "${service_user}" -- python3 -m venv "${analysis_root}/venv"
fi

test "$(stat -c '%a' "${analysis_root}/input")" = "700"
test "$(stat -c '%a' "${swap_path}")" = "600"
swapon --show "${swap_path}"
