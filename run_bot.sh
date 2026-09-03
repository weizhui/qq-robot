#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
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
