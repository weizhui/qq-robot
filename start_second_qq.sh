#!/usr/bin/env bash
# 为第二个 QQ 号单独启动一个 QQ / NapCat 实例（独立数据目录），
# 不会动、也不会踢掉已经在运行的那个号。
#
# 背景：官方 NapCatShell 同一套环境下同一时间只允许登录一个 QQ 号，
# 所以第二个号要用自己的 --user-data-dir 单独启动。
#
# 用法：
#   ./start_second_qq.sh <QQ号>
#   ./start_second_qq.sh              # 读取私密配置里的 MENTION_BOT_QQ
#
# 启动后看二维码扫码：
#   tail -f ~/Napcat/log/napcat_<QQ号>.log
set -euo pipefail

QQ_NUMBER="${1:-}"
if [ -z "$QQ_NUMBER" ]; then
  ENV_FILE="${MENTION_ENV_FILE:-$HOME/.config/qq-mention-bot/env.sh}"
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  fi
  QQ_NUMBER="${MENTION_BOT_QQ:-}"
fi
if [ -z "$QQ_NUMBER" ]; then
  echo "用法: $0 <QQ号>" >&2
  exit 1
fi

QQ_EXECUTABLE="$HOME/Napcat/opt/QQ/qq"
DATA_DIR="$HOME/.config/QQ-$QQ_NUMBER"
SESSION="${SECOND_QQ_SESSION:-napcat_$QQ_NUMBER}"
LOG_DIR="$HOME/Napcat/log"
LOG_FILE="$LOG_DIR/napcat_$QQ_NUMBER.log"
API_PORT="${MENTION_API_PORT:-3001}"

if [ ! -x "$QQ_EXECUTABLE" ]; then
  echo "找不到 QQ 可执行文件：$QQ_EXECUTABLE" >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$DATA_DIR"

if screen -ls 2>/dev/null | grep -q "[.]${SESSION}[[:space:]]"; then
  echo "会话 $SESSION 已经在运行了。"
  echo "二维码 / 日志：tail -f '$LOG_FILE'"
  exit 0
fi

echo "启动第二个 QQ 实例"
echo "  账号    : $QQ_NUMBER"
echo "  数据目录: $DATA_DIR"
echo "  会话名  : $SESSION"
echo "  日志    : $LOG_FILE"

screen -dmS "$SESSION" bash -c \
  "xvfb-run -a '$QQ_EXECUTABLE' --no-sandbox -q '$QQ_NUMBER' --user-data-dir='$DATA_DIR' >>'$LOG_FILE' 2>&1"

sleep 2
echo
echo "下一步："
echo "  1) 看日志里的二维码并扫码登录："
echo "       tail -f '$LOG_FILE'"
echo "  2) 登录成功后确认 OneBot HTTP API 在监听："
echo "       curl --noproxy '*' http://127.0.0.1:${API_PORT}/get_status"
echo
echo "停止这个实例：screen -S '$SESSION' -X quit"
