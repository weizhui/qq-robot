#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

missing=()
for command in python3 screen curl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    missing+=("$command")
  fi
done

if [ "${#missing[@]}" -gt 0 ]; then
  echo "缺少必要命令：${missing[*]}" >&2
  echo "Debian / Ubuntu 可执行：sudo apt update && sudo apt install -y python3 screen curl" >&2
  exit 1
fi

mkdir -p runtime_cache

main_config_dir="${QQ_BOT_CONFIG_DIR:-${HOME}/.config/qq-bot}"
main_config_file="${QQ_BOT_ENV_FILE:-${main_config_dir}/env.sh}"
mkdir -p "$main_config_dir"

if [ ! -f "$main_config_file" ]; then
  cp .env.example "$main_config_file"
  chmod 600 "$main_config_file"
  echo "已创建主机器人配置：$main_config_file"
else
  chmod 600 "$main_config_file"
  echo "主机器人配置已存在：$main_config_file"
fi

if [ -f mention_bot.env.example ]; then
  mention_config_dir="${QQ_MENTION_BOT_CONFIG_DIR:-${HOME}/.config/qq-mention-bot}"
  mention_config_file="${QQ_MENTION_BOT_ENV_FILE:-${mention_config_dir}/env.sh}"
  mkdir -p "$mention_config_dir"
  if [ ! -f "$mention_config_file" ]; then
    cp mention_bot.env.example "$mention_config_file"
    chmod 600 "$mention_config_file"
    echo "已创建定时 @ 机器人配置：$mention_config_file"
  else
    chmod 600 "$mention_config_file"
    echo "定时 @ 机器人配置已存在：$mention_config_file"
  fi
fi

python3 -m py_compile main.py reply_interface.py memory_store.py mention_bot.py

echo
echo "本地准备完成。下一步："
echo "1. 编辑 $main_config_file，填入真实 QQ / 群号 / API 地址 / Token。"
echo "2. 配置 OneBot 事件上报到 http://<HOST>:<PORT>/onebot。"
echo "3. 前台调试：./run_bot.sh"
echo "4. 后台运行：screen -dmS qq_bot ./run_bot.sh"
