#!/usr/bin/env sh
set -eu

umask 077

fail() {
  printf '%s\n' "$1" >&2
  exit 1
}

if [ "$#" -ne 0 ]; then
  fail "用法: 将令牌摘要和自动建任务开关各占一行写入标准输入"
fi

IFS= read -r token_digest || fail "机器令牌摘要缺失"
IFS= read -r auto_enqueue || fail "自动建任务开关缺失"
unexpected_line=""
if IFS= read -r unexpected_line || [ -n "$unexpected_line" ]; then
  fail "标准输入包含多余内容"
fi

case "$auto_enqueue" in
  true|false) ;;
  *) fail "自动建任务开关无效" ;;
esac

case "$token_digest" in
  *[!0-9a-f]*) fail "机器令牌摘要格式无效" ;;
esac
[ "${#token_digest}" -eq 64 ] || fail "机器令牌摘要格式无效"

target=".env"
[ -f "$target" ] && [ ! -L "$target" ] || fail "生产环境文件无效"

temporary="$(mktemp ./.env.pp-mcare.XXXXXX)"
cleanup() {
  test -z "$temporary" || test ! -e "$temporary" || rm -f -- "$temporary"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

awk '
  !/^PP_MCARE_SERVICE_TOKEN_SHA256=/ &&
  !/^PP_MCARE_AUTO_ENQUEUE_ENABLED=/
' "$target" > "$temporary"
printf '%s\n' "PP_MCARE_SERVICE_TOKEN_SHA256=$token_digest" >> "$temporary"
printf '%s\n' "PP_MCARE_AUTO_ENQUEUE_ENABLED=$auto_enqueue" >> "$temporary"
chmod 0600 "$temporary"
mv -f -- "$temporary" "$target"
temporary=""
trap - EXIT HUP INT TERM
