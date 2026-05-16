#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
RUNTIME_DIR="${RUNTIME_DIR:-$ROOT_DIR/.runtime}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
PID_FILE="${PID_FILE:-$RUNTIME_DIR/backend.pid}"
LOG_FILE="${LOG_FILE:-$RUNTIME_DIR/backend.log}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
COMMAND="${1:-start}"
RUNSERVER_ARGS=("$HOST:$PORT")

if [[ "${DJANGO_RELOAD:-0}" != "1" ]]; then
  RUNSERVER_ARGS+=("--noreload")
fi

mkdir -p "$RUNTIME_DIR"

read_pid() {
  if [[ -f "$PID_FILE" ]]; then
    tr -d '[:space:]' < "$PID_FILE"
  fi
}

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

tcp_listen_pid() {
  local port="$1"
  lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

port_pid() {
  tcp_listen_pid "$PORT"
}

pid_command() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null || true
}

pid_cwd() {
  local pid="$1"
  lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true
}

is_project_runserver() {
  local pid="$1"
  local command cwd
  command="$(pid_command "$pid")"
  cwd="$(pid_cwd "$pid")"

  [[ "$command" == *"manage.py runserver"* ]] || return 1
  [[ "$command" == *"$HOST:$PORT"* || "$command" == *"0.0.0.0:$PORT"* ]] || return 1

  case "$cwd" in
    "$ROOT_DIR"|"$ROOT_DIR"/*) return 0 ;;
    *) return 1 ;;
  esac
}

runserver_root_pid() {
  local pid="$1"
  local ppid
  ppid="$(ps -p "$pid" -o ppid= 2>/dev/null | tr -d '[:space:]' || true)"
  if is_running "$ppid" && is_project_runserver "$ppid"; then
    echo "$ppid"
  else
    echo "$pid"
  fi
}

stop_process_tree() {
  local pid="$1"
  local children
  children="$(pgrep -P "$pid" 2>/dev/null || true)"

  for child in $children; do
    stop_process_tree "$child"
  done

  kill "$pid" 2>/dev/null || true
}

wait_stopped() {
  local pid="$1"
  for _ in {1..20}; do
    if ! is_running "$pid"; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

ensure_infra() {
  if [[ "${START_INFRA:-1}" != "1" ]]; then
    echo "跳过 Docker 依赖启动：START_INFRA=$START_INFRA"
    return 0
  fi

  cd "$ROOT_DIR"
  if docker compose up -d postgres redis; then
    if [[ -n "$(tcp_listen_pid 5432)" ]] && [[ -n "$(tcp_listen_pid 6379)" ]]; then
      return 0
    fi

    echo "Docker 容器已启动，但本机 5432/6379 未监听，无法连接后端依赖。"
    return 1
  fi

  if [[ "${USE_EXISTING_INFRA:-1}" == "1" ]] \
    && [[ -n "$(tcp_listen_pid 5432)" ]] \
    && [[ -n "$(tcp_listen_pid 6379)" ]]; then
    echo "检测到本机 5432/6379 已有服务在监听，继续使用现有 Postgres/Redis。"
    echo "如需强制使用本项目 Docker 容器，请先释放 5432/6379 或设置 USE_EXISTING_INFRA=0。"
    return 0
  fi

  echo "Docker 依赖启动失败，且没有可复用的 5432/6379 服务。"
  return 1
}

start_backend() {
  local existing_pid holder_pid
  existing_pid="$(read_pid || true)"

  if is_running "$existing_pid"; then
    echo "后端已在后台运行：PID $existing_pid"
    echo "地址：http://$HOST:$PORT"
    echo "日志：$LOG_FILE"
    return 0
  fi

  rm -f "$PID_FILE"

  holder_pid="$(port_pid)"
  if is_running "$holder_pid"; then
    if is_project_runserver "$holder_pid"; then
      holder_pid="$(runserver_root_pid "$holder_pid")"
      echo "$holder_pid" > "$PID_FILE"
      echo "后端已在后台运行：PID $holder_pid"
      echo "地址：http://$HOST:$PORT"
      echo "日志：$LOG_FILE"
      return 0
    fi

    echo "端口 $PORT 已被其他进程占用，无法启动后端："
    ps -p "$holder_pid" -o pid=,command= || true
    echo "可改用 PORT=8001 $0 start，或先释放端口 $PORT。"
    return 1
  fi

  ensure_infra

  cd "$BACKEND_DIR"
  if [[ ! -d .venv ]]; then
    "$PYTHON_BIN" -m venv .venv
  fi

  # shellcheck disable=SC1091
  source .venv/bin/activate

  if [[ "${INSTALL_DEPS:-0}" == "1" ]] || ! python -c "import django" >/dev/null 2>&1; then
    pip install -e ".[dev]"
  fi

  if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
    python manage.py migrate
  fi

  if [[ "${SEED_DEMO:-0}" == "1" ]]; then
    python manage.py seed_demo
  fi

  nohup python manage.py runserver "${RUNSERVER_ARGS[@]}" > "$LOG_FILE" 2>&1 < /dev/null &
  local pid="$!"
  echo "$pid" > "$PID_FILE"

  for _ in {1..50}; do
    holder_pid="$(port_pid)"
    if is_running "$holder_pid" && is_project_runserver "$holder_pid"; then
      holder_pid="$(runserver_root_pid "$holder_pid")"
      echo "$holder_pid" > "$PID_FILE"
      echo "后端已启动：PID $holder_pid"
      echo "地址：http://$HOST:$PORT"
      echo "日志：$LOG_FILE"
      return 0
    fi

    if ! is_running "$pid"; then
      break
    fi

    sleep 0.2
  done

  if ! is_running "$pid"; then
    echo "后端启动失败，最近日志如下："
    tail -n 80 "$LOG_FILE" || true
    rm -f "$PID_FILE"
    return 1
  fi

  echo "后端进程已启动但端口 $PORT 尚未监听，最近日志如下："
  tail -n 80 "$LOG_FILE" || true
  return 1
}

stop_backend() {
  local pid holder_pid
  pid="$(read_pid || true)"

  if ! is_running "$pid"; then
    holder_pid="$(port_pid)"
    if is_running "$holder_pid" && is_project_runserver "$holder_pid"; then
      pid="$(runserver_root_pid "$holder_pid")"
    else
      echo "后端未运行"
      rm -f "$PID_FILE"
      return 0
    fi
  fi

  stop_process_tree "$pid"
  if wait_stopped "$pid"; then
    rm -f "$PID_FILE"
    echo "后端已停止：PID $pid"
    return 0
  fi

  kill -9 "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "后端已强制停止：PID $pid"
}

status_backend() {
  local pid holder_pid
  pid="$(read_pid || true)"

  if is_running "$pid"; then
    echo "后端运行中：PID $pid"
    echo "地址：http://$HOST:$PORT"
    echo "日志：$LOG_FILE"
  else
    holder_pid="$(port_pid)"
    if is_running "$holder_pid" && is_project_runserver "$holder_pid"; then
      holder_pid="$(runserver_root_pid "$holder_pid")"
      echo "后端运行中：PID $holder_pid"
      echo "地址：http://$HOST:$PORT"
      echo "日志：$LOG_FILE"
      echo "$holder_pid" > "$PID_FILE"
    else
      echo "后端未运行"
      rm -f "$PID_FILE"
    fi
  fi
}

case "$COMMAND" in
  start)
    start_backend
    ;;
  stop)
    stop_backend
    ;;
  restart)
    stop_backend
    start_backend
    ;;
  status)
    status_backend
    ;;
  logs)
    touch "$LOG_FILE"
    tail -f "$LOG_FILE"
    ;;
  *)
    echo "用法：$0 [start|stop|restart|status|logs]"
    exit 2
    ;;
esac
