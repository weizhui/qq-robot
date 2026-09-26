#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# 私有配置放在仓库外（600 权限），这样在新终端裸重启也不会丢配置。
# 可用 QQ_BOT_ENV_FILE 指定其它配置文件。
ENV_FILE="${QQ_BOT_ENV_FILE:-${HOME:-}/.config/qq-bot/env.sh}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  echo "已加载配置：$ENV_FILE"
else
  echo "提示：未找到 $ENV_FILE，将只使用当前环境里已有的变量" >&2
fi

# 本机 NapCat API 调用不走代理（环境里可能有 clash 之类的 http_proxy，
# 否则发往 127.0.0.1 的请求会被代理转发并失败）。外部 API 仍走代理。
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"

export BOT_QQ="${BOT_QQ:-}"
export TARGET_GROUP_IDS="${TARGET_GROUP_IDS:-}"
export HOST="${HOST:-localhost}"
export PORT="${PORT:-8080}"
export NAPCAT_API_BASE="${NAPCAT_API_BASE:-}"
export NAPCAT_ACCESS_TOKEN="${NAPCAT_ACCESS_TOKEN:-}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
export DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-chat}"
export DEEPSEEK_API_URL="${DEEPSEEK_API_URL:-}"
export JIKAN_API_BASE="${JIKAN_API_BASE:-}"
export ANILIST_API_URL="${ANILIST_API_URL:-}"

exec python3 main.py
