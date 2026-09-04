#!/usr/bin/env bash
set -euo pipefail

_validate_existing_directory() {
  local path="$1"
  local expected_realpath="$2"
  local expected_uid="$3"
  local expected_gid="$4"
  local expected_mode="$5"
  local label="$6"
  local actual_realpath metadata actual_uid actual_gid actual_mode

  if [[ -L "${path}" || ( -e "${path}" && ! -d "${path}" ) ]]; then
    echo "${label} 已存在但不是普通目录，或是符号链接" >&2
    return 1
  fi
  if [[ ! -e "${path}" ]]; then
    return 0
  fi

  actual_realpath="$(readlink -f -- "${path}")" || {
    echo "${label} 无法解析真实路径" >&2
    return 1
  }
  if [[ "${actual_realpath}" != "${expected_realpath}" ]]; then
    echo "${label} 的真实路径超出固定分析根目录" >&2
    return 1
  fi

  metadata="$(stat -c '%u:%g:%a' -- "${path}")" || {
    echo "${label} 无法读取安全属性" >&2
    return 1
  }
  IFS=: read -r actual_uid actual_gid actual_mode <<< "${metadata}"
  if [[ "${actual_uid}" != "${expected_uid}" \
    || "${actual_gid}" != "${expected_gid}" \
    || "${actual_mode}" != "${expected_mode}" ]]; then
    echo "${label} 的所有权或权限不符合要求，停止且不自动修补" >&2
    return 1
  fi
}

_validate_existing_swap() {
  local swap_path="$1"
  local metadata owner_uid owner_gid mode link_count size

  if [[ -L "${swap_path}" || ( -e "${swap_path}" && ! -f "${swap_path}" ) ]]; then
    echo "swap 路径已存在但不是普通文件，或是符号链接" >&2
    return 1
  fi
  if [[ ! -e "${swap_path}" ]]; then
    return 0
  fi

  metadata="$(stat -c '%u:%g:%a:%h:%s' -- "${swap_path}")" || {
    echo "swap 文件无法读取安全属性" >&2
    return 1
  }
  IFS=: read -r owner_uid owner_gid mode link_count size <<< "${metadata}"
  if [[ "${owner_uid}" != "0" || "${owner_gid}" != "0" ]]; then
    echo "swap 文件必须由 root:root 所有，停止且不自动修补" >&2
    return 1
  fi
  if [[ "${mode}" != "600" ]]; then
    echo "swap 文件权限不是 0600，停止且不自动修补" >&2
    return 1
  fi
  if [[ "${link_count}" != "1" ]]; then
    echo "swap 文件存在额外硬链接，停止以避免启用不安全文件" >&2
    return 1
  fi
  if [[ "${size}" != "4294967296" ]]; then
    echo "swap 文件不是 4 GiB，停止且不自动修补" >&2
    return 1
  fi
}

_validate_existing_paths() {
  local analysis_root="$1"
  local swap_path="$2"
  local service_uid="$3"
  local service_gid="$4"
  local child

  _validate_existing_swap "${swap_path}"

  if [[ -e "${analysis_root}" || -L "${analysis_root}" ]]; then
    if [[ -z "${service_uid}" || -z "${service_gid}" ]]; then
      echo "服务账号不存在但分析根目录已存在，停止且不自动修补" >&2
      return 1
    fi
  fi

  _validate_existing_directory \
    "${analysis_root}" "${analysis_root}" "0" "${service_gid}" "750" "分析根目录"
  _validate_existing_directory \
    "${analysis_root}/app" "${analysis_root}/app" \
    "0" "${service_gid}" "750" "应用目录"
  for child in model-cache input tmp reports logs venv; do
    _validate_existing_directory \
      "${analysis_root}/${child}" "${analysis_root}/${child}" \
      "${service_uid}" "${service_gid}" "700" "受管目录 ${child}"
  done
}

_read_login_def_value() {
  local key="$1"
  local login_defs="$2"
  local fallback="$3"
  local value

  value="$(
    awk -v expected_key="${key}" \
      '$1 == expected_key && $2 ~ /^[0-9]+$/ { value = $2 } END { print value }' \
      "${login_defs}" 2>/dev/null || true
  )"
  printf '%s\n' "${value:-${fallback}}"
}

_validate_existing_service_account() {
  local passwd_entry="$1"
  local service_user="$2"
  local expected_home="$3"
  local login_defs="$4"
  local account_name password uid gid gecos account_home account_shell
  local system_uid_min system_uid_max

  if [[ -z "${passwd_entry}" ]]; then
    return 0
  fi
  if [[ "${passwd_entry}" == *$'\n'* ]]; then
    echo "服务账号信息不唯一，停止以避免复用错误账号" >&2
    return 1
  fi

  IFS=: read -r \
    account_name password uid gid gecos account_home account_shell \
    <<< "${passwd_entry}"
  system_uid_min="$(_read_login_def_value "SYS_UID_MIN" "${login_defs}" "100")"
  system_uid_max="$(_read_login_def_value "SYS_UID_MAX" "${login_defs}" "999")"

  if [[ ! "${uid}" =~ ^[0-9]+$ ]] \
    || (( uid < system_uid_min || uid > system_uid_max )) \
    || [[ "${account_name}" != "${service_user}" ]] \
    || [[ "${account_home}" != "${expected_home}" ]] \
    || [[ "${account_shell}" != "/usr/sbin/nologin" ]]; then
    echo "同名服务账号属性不符合要求，停止以避免复用" >&2
    return 1
  fi
}

_create_swap_file() {
  local swap_path="$1"

  _swap_temporary_path="$(mktemp "${swap_path}.tmp.XXXXXX")"
  cleanup_swap_temporary() {
    if [[ -n "${_swap_temporary_path:-}" && -e "${_swap_temporary_path}" ]]; then
      unlink "${_swap_temporary_path}"
    fi
  }
  trap cleanup_swap_temporary EXIT

  chmod 0600 "${_swap_temporary_path}"
  fallocate -l 4G "${_swap_temporary_path}"
  mkswap "${_swap_temporary_path}"
  if ! ln "${_swap_temporary_path}" "${swap_path}"; then
    echo "swap 路径在创建期间已出现，停止以避免覆盖" >&2
    return 1
  fi
  unlink "${_swap_temporary_path}"
  _swap_temporary_path=""
  trap - EXIT
}

_bootstrap_after_root_gate() {
  local analysis_root="$1"
  local swap_path="$2"
  local login_defs="$3"
  local service_user="motioncare-analysis"
  local passwd_entry account_name password service_uid service_gid
  local gecos account_home account_shell

  passwd_entry="$(getent passwd "${service_user}" || true)"
  _validate_existing_service_account \
    "${passwd_entry}" \
    "${service_user}" \
    "${analysis_root}" \
    "${login_defs}"
  service_uid=""
  service_gid=""
  if [[ -n "${passwd_entry}" ]]; then
    IFS=: read -r \
      account_name password service_uid service_gid gecos account_home account_shell \
      <<< "${passwd_entry}"
  fi
  _validate_existing_paths \
    "${analysis_root}" "${swap_path}" "${service_uid}" "${service_gid}"

  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates ffmpeg python3 python3-venv python3-pip

  if [[ -z "${passwd_entry}" ]]; then
    useradd --system \
      --home-dir "${analysis_root}" \
      --no-create-home \
      --shell /usr/sbin/nologin \
      "${service_user}"
    passwd_entry="$(getent passwd "${service_user}")"
    _validate_existing_service_account \
      "${passwd_entry}" \
      "${service_user}" \
      "${analysis_root}" \
      "${login_defs}"
    IFS=: read -r \
      account_name password service_uid service_gid gecos account_home account_shell \
      <<< "${passwd_entry}"
  fi

  _validate_existing_paths \
    "${analysis_root}" "${swap_path}" "${service_uid}" "${service_gid}"

  install -d -m 0750 -o root -g "${service_user}" "${analysis_root}"
  install -d -m 0750 -o root -g "${service_user}" "${analysis_root}/app"
  install -d -m 0700 -o "${service_user}" -g "${service_user}" \
    "${analysis_root}/model-cache" \
    "${analysis_root}/input" \
    "${analysis_root}/tmp" \
    "${analysis_root}/reports" \
    "${analysis_root}/logs"

  if [[ ! -e "${swap_path}" ]]; then
    _create_swap_file "${swap_path}"
  fi
  _validate_existing_swap "${swap_path}"
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

  _validate_existing_paths \
    "${analysis_root}" "${swap_path}" "${service_uid}" "${service_gid}"
  swapon --show "${swap_path}"
}

_bootstrap_main() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "必须以 root 执行" >&2
    exit 1
  fi

  analysis_root="${MOTIONCARE_ANALYSIS_ROOT:-/opt/motioncare-analysis}"
  if [[ "${analysis_root}" != "/opt/motioncare-analysis" ]]; then
    echo "本次冒烟只允许 /opt/motioncare-analysis" >&2
    exit 1
  fi
  _bootstrap_after_root_gate "${analysis_root}" "/swapfile" "/etc/login.defs"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  _bootstrap_main "$@"
fi
