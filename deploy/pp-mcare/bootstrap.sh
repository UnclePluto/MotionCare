#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly ANALYSIS_ROOT="/opt/motioncare-analysis"
readonly SERVICE_USER="motioncare-analysis"
readonly SWAP_PATH="/swapfile"
readonly SWAP_SIZE_BYTES="4294967296"

_fail() {
  printf '%s\n' "$1" >&2
  return 1
}

_require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    _fail "必须以 root 执行"
  fi
}

_read_login_def_value() {
  local key="$1"
  local fallback="$2"
  local value
  value="$(awk -v key="${key}" '$1 == key && $2 ~ /^[0-9]+$/ { value=$2 } END { print value }' /etc/login.defs 2>/dev/null || true)"
  printf '%s\n' "${value:-${fallback}}"
}

_validate_service_account() {
  local entry="$1"
  local name password uid gid gecos home shell
  local uid_min uid_max
  [[ -z "${entry}" ]] && return 0
  [[ "${entry}" != *$'\n'* ]] || _fail "服务账号记录不唯一"
  IFS=: read -r name password uid gid gecos home shell <<< "${entry}"
  uid_min="$(_read_login_def_value SYS_UID_MIN 100)"
  uid_max="$(_read_login_def_value SYS_UID_MAX 999)"
  [[ "${name}" == "${SERVICE_USER}" ]] || _fail "服务账号名称不匹配"
  [[ "${uid}" =~ ^[0-9]+$ ]] || _fail "服务账号 UID 无效"
  (( uid >= uid_min && uid <= uid_max )) || _fail "服务账号不是系统账号"
  [[ "${home}" == "${ANALYSIS_ROOT}" ]] || _fail "服务账号 home 不匹配"
  [[ "${shell}" == "/usr/sbin/nologin" ]] || _fail "服务账号 shell 不安全"
}

_validate_directory() {
  local path="$1"
  local owner="$2"
  local group="$3"
  local mode="$4"
  local metadata actual_owner actual_group actual_mode
  [[ ! -L "${path}" ]] || _fail "受管目录不能是符号链接"
  [[ ! -e "${path}" || -d "${path}" ]] || _fail "受管路径不是目录"
  [[ ! -e "${path}" ]] && return 0
  [[ "$(readlink -f -- "${path}")" == "${path}" ]] || _fail "受管目录真实路径不匹配"
  metadata="$(stat -c '%U:%G:%a' -- "${path}")"
  IFS=: read -r actual_owner actual_group actual_mode <<< "${metadata}"
  [[ "${actual_owner}" == "${owner}" ]] || _fail "受管目录所有者不匹配"
  [[ "${actual_group}" == "${group}" ]] || _fail "受管目录组不匹配"
  [[ "${actual_mode}" == "${mode}" ]] || _fail "受管目录权限不匹配"
}

_validate_swap() {
  local metadata uid gid mode links size
  [[ ! -L "${SWAP_PATH}" ]] || _fail "Swap 不能是符号链接"
  [[ ! -e "${SWAP_PATH}" || -f "${SWAP_PATH}" ]] || _fail "Swap 路径不是普通文件"
  [[ ! -e "${SWAP_PATH}" ]] && return 0
  metadata="$(stat -c '%u:%g:%a:%h:%s' -- "${SWAP_PATH}")"
  IFS=: read -r uid gid mode links size <<< "${metadata}"
  [[ "${uid}:${gid}:${mode}:${links}:${size}" == "0:0:600:1:${SWAP_SIZE_BYTES}" ]] \
    || _fail "既有 Swap 的所有权、权限、链接数或大小不安全"
}

_create_swap() {
  local temporary
  temporary="$(mktemp "${SWAP_PATH}.tmp.XXXXXX")"
  trap '[[ ! -e "${temporary:-}" ]] || unlink -- "${temporary}"' RETURN
  chmod 0600 "${temporary}"
  fallocate -l 4G "${temporary}"
  mkswap "${temporary}" >/dev/null
  ln "${temporary}" "${SWAP_PATH}"
  unlink "${temporary}"
  temporary=""
  trap - RETURN
}

_validate_environment_file() {
  local path="/etc/pp-mcare.env"
  local metadata
  [[ ! -L "${path}" ]] || _fail "worker 环境文件不能是符号链接"
  [[ ! -e "${path}" || -f "${path}" ]] || _fail "worker 环境路径不是普通文件"
  [[ ! -e "${path}" ]] && return 0
  metadata="$(stat -c '%u:%g:%a:%h' -- "${path}")"
  [[ "${metadata}" == "0:0:600:1" ]] || _fail "worker 环境文件权限不安全"
}

_bootstrap_after_root_gate() {
  local script_root="$1"
  local entry

  entry="$(getent passwd "${SERVICE_USER}" || true)"
  _validate_service_account "${entry}"
  if [[ -e "${ANALYSIS_ROOT}" && -z "${entry}" ]]; then
    _fail "分析根目录已存在但服务账号不存在"
  fi

  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates ffmpeg python3.12 python3.12-venv python3-pip

  if [[ -z "${entry}" ]]; then
    useradd --system --home-dir "${ANALYSIS_ROOT}" --no-create-home \
      --shell /usr/sbin/nologin "${SERVICE_USER}"
    entry="$(getent passwd "${SERVICE_USER}")"
    _validate_service_account "${entry}"
  fi

  _validate_directory "${ANALYSIS_ROOT}" root "${SERVICE_USER}" 750
  for path in releases failed; do
    _validate_directory "${ANALYSIS_ROOT}/${path}" root "${SERVICE_USER}" 750
  done
  for path in model-cache input tmp reports logs; do
    _validate_directory "${ANALYSIS_ROOT}/${path}" "${SERVICE_USER}" "${SERVICE_USER}" 700
  done
  _validate_directory "${ANALYSIS_ROOT}/tmp/jobs" \
    "${SERVICE_USER}" "${SERVICE_USER}" 700
  _validate_swap
  _validate_environment_file

  install -d -m 0750 -o root -g "${SERVICE_USER}" \
    "${ANALYSIS_ROOT}" "${ANALYSIS_ROOT}/releases" "${ANALYSIS_ROOT}/failed"
  install -d -m 0700 -o "${SERVICE_USER}" -g "${SERVICE_USER}" \
    "${ANALYSIS_ROOT}/model-cache" "${ANALYSIS_ROOT}/input" \
    "${ANALYSIS_ROOT}/tmp" "${ANALYSIS_ROOT}/reports" \
    "${ANALYSIS_ROOT}/logs" "${ANALYSIS_ROOT}/tmp/jobs"

  if [[ ! -e "${SWAP_PATH}" ]]; then
    _create_swap
  fi
  _validate_swap
  if ! swapon --show=NAME --noheadings --raw | grep -Fxq "${SWAP_PATH}"; then
    swapon "${SWAP_PATH}"
  fi
  if ! awk '$1 == "/swapfile" && $3 == "swap" { found=1 } END { exit !found }' /etc/fstab; then
    printf '%s\n' '/swapfile none swap sw 0 0' >> /etc/fstab
  fi

  if [[ ! -e /etc/pp-mcare.env ]]; then
    install -m 0600 -o root -g root "${script_root}/env.example" /etc/pp-mcare.env
  fi
  _validate_environment_file
  install -m 0644 -o root -g root \
    "${script_root}/pp-mcare.service" /etc/systemd/system/pp-mcare.service

  _validate_directory "${ANALYSIS_ROOT}" root "${SERVICE_USER}" 750
  for path in releases failed; do
    _validate_directory "${ANALYSIS_ROOT}/${path}" root "${SERVICE_USER}" 750
  done
  for path in model-cache input tmp reports logs; do
    _validate_directory "${ANALYSIS_ROOT}/${path}" "${SERVICE_USER}" "${SERVICE_USER}" 700
  done
  _validate_directory "${ANALYSIS_ROOT}/tmp/jobs" \
    "${SERVICE_USER}" "${SERVICE_USER}" 700
  systemctl daemon-reload
  swapon --show "${SWAP_PATH}"
}

_bootstrap_main() {
  local script_root
  _require_root
  script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  [[ -f "${script_root}/env.example" && -f "${script_root}/pp-mcare.service" ]] \
    || _fail "部署文件不完整"
  _bootstrap_after_root_gate "${script_root}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  _bootstrap_main "$@"
fi
