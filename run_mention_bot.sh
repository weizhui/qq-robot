#!/usr/bin/env bash
# 启动「定时 @ 提醒」机器人（独立于 run_bot.sh 里的原机器人，互不影响）。
#
# 真实 QQ 号 / 群号 / 端口等配置放在仓库外的私密文件里，避免提交到公开仓库：
#   ~/.config/qq-mention-bot/env.sh   （权限建议 600，模板见 mention_bot.env.example）
# 也可以用 MENTION_ENV_FILE 指定别的路径。
set -euo pipefail

cd "$(dirname "$0")"

ENV_FILE="${MENTION_ENV_FILE:-$HOME/.config/qq-mention-bot/env.sh}"
if [ ! -f "$ENV_FILE" ]; then
  echo "找不到配置文件：$ENV_FILE" >&2
  echo "请参考 mention_bot.env.example 创建后再启动。" >&2
  exit 1
fi
# set -a：让配置文件里的变量自动 export 给 python 子进程
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# 本机调用不走代理
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

exec python3 mention_bot.py
