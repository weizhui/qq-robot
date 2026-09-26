#!/usr/bin/env python3
"""定时 @ 提醒机器人（独立实例，与 main.py 互不影响）。

只做两件事，全部命令都必须由「指定用户」在「指定群」里发出：

    !N秒@某人    (N > 0)  每 N 秒 @ 一次该成员，直到被停止
    !0秒@某人             停止 @ 该成员

其它任何消息、任何群、任何用户一律忽略（机器人不会回复、不会插话）。

接入方式与 main.py 相同：NapCat(OneBot) 把群消息 POST 到本进程的 Webhook，
本进程再用 OneBot 的 send_group_msg 接口发 @ 消息。

真实 QQ 号/群号不写进代码，全部走环境变量（见 mention_bot.env.example）：
    MENTION_BOT_QQ            机器人的 QQ 号（必填）
    MENTION_GROUP_ID          只监听这个群（必填）
    MENTION_ALLOWED_USER_ID   只有这个 QQ 号能下命令（必填）
    MENTION_HOST / MENTION_PORT           Webhook 监听地址，默认 127.0.0.1:18081
    MENTION_NAPCAT_API_BASE   OneBot HTTP API，默认 http://127.0.0.1:3001
    MENTION_NAPCAT_ACCESS_TOKEN           OneBot 鉴权 token，默认空
    MENTION_MIN_INTERVAL      允许的最小间隔秒数，默认 5（防止刷屏/风控）
    MENTION_MAX_INTERVAL      允许的最大间隔秒数，默认 86400
    MENTION_TEXT              每次 @ 后面附带的话，默认 "🔔"，设为空则只 @ 人
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _env_int(name, default=None, required=False):
    """读取整数环境变量；缺失或非法时给出清晰提示。"""
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        if required:
            raise SystemExit(
                f"缺少必需的环境变量 {name}，请参考 mention_bot.env.example 配置后再启动。"
            )
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"环境变量 {name} 必须是整数，当前值：{raw!r}")


BOT_QQ = str(_env_int("MENTION_BOT_QQ", required=True))
TARGET_GROUP_ID = _env_int("MENTION_GROUP_ID", required=True)
ALLOWED_USER_ID = _env_int("MENTION_ALLOWED_USER_ID", required=True)
HOST = os.getenv("MENTION_HOST", "127.0.0.1")
PORT = _env_int("MENTION_PORT", 18081)
NAPCAT_API_BASE = os.getenv("MENTION_NAPCAT_API_BASE", "http://127.0.0.1:3001").rstrip("/")
NAPCAT_ACCESS_TOKEN = os.getenv("MENTION_NAPCAT_ACCESS_TOKEN", "")
MIN_INTERVAL = max(1, _env_int("MENTION_MIN_INTERVAL", 5))
MAX_INTERVAL = max(MIN_INTERVAL, _env_int("MENTION_MAX_INTERVAL", 86400))
MENTION_TEXT = os.getenv("MENTION_TEXT", "🔔")

# 命令：!5秒 / ！5秒 / !5s / ! 5 秒
COMMAND_RE = re.compile(r"^[!！]\s*(\d{1,6})\s*(?:秒|s|S)$")
# OneBot 原始消息里的 @ 片段
AT_CQ_RE = re.compile(r"\[CQ:at,qq=([^,\]]+)\]")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("mention-bot")

# 本机调用不走任何代理（环境里可能有 clash 之类的 http_proxy）。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call_napcat(action, payload, timeout=10):
    """调用 OneBot HTTP API。"""
    url = f"{NAPCAT_API_BASE}/{action}"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if NAPCAT_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {NAPCAT_ACCESS_TOKEN}"

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        logger.error("NapCat API returned HTTP %s for %s", exc.code, action)
        raise
    except urllib.error.URLError as exc:
        logger.error("Cannot reach NapCat API at %s: %s", url, exc)
        raise


def send_mention(target_qq):
    """在目标群 @ 指定成员。"""
    message = f"[CQ:at,qq={int(target_qq)}]"
    if MENTION_TEXT:
        message = f"{message} {MENTION_TEXT}"
    call_napcat(
        "send_group_msg",
        {
            "group_id": int(TARGET_GROUP_ID),
            "message": message,
        },
    )
    logger.info("Mentioned qq=%s in group=%s", target_qq, TARGET_GROUP_ID)


def extract_text_and_targets(event):
    """从 OneBot 事件里取出纯文本和被 @ 的 QQ 号列表。"""
    targets = []

    def add_target(raw_qq):
        qq = str(raw_qq).strip()
        if qq.isdigit() and qq != BOT_QQ and int(qq) != 0:
            targets.append(int(qq))

    raw_message = str(event.get("raw_message") or "")
    if raw_message:
        text = AT_CQ_RE.sub(" ", raw_message)
        for qq in AT_CQ_RE.findall(raw_message):
            add_target(qq)
    else:
        message = event.get("message")
        text_parts = []
        if isinstance(message, list):
            for segment in message:
                if not isinstance(segment, dict):
                    continue
                segment_type = segment.get("type")
                data = segment.get("data") or {}
                if segment_type == "text":
                    text_parts.append(str(data.get("text") or ""))
                elif segment_type == "at":
                    add_target(data.get("qq"))
        else:
            text_parts.append(str(message or ""))
        text = " ".join(part for part in text_parts if part)

    # 保序去重
    return text.strip(), list(dict.fromkeys(targets))


class MentionManager:
    """管理「谁、每隔几秒 @ 一次」，用一个后台线程统一计时。"""

    def __init__(self, interval_min, interval_max):
        self.interval_min = interval_min
        self.interval_max = interval_max
        self._lock = threading.Lock()
        # target_qq -> {"interval": int, "next_at": monotonic 秒}
        self._tasks = {}
        self._wakeup = threading.Event()

    def start(self, target_qq, interval):
        target_qq = int(target_qq)
        interval = min(max(int(interval), self.interval_min), self.interval_max)
        with self._lock:
            self._tasks[target_qq] = {
                "interval": interval,
                "next_at": time.monotonic() + interval,
            }
        self._wakeup.set()
        return interval

    def stop(self, target_qq):
        with self._lock:
            existed = self._tasks.pop(int(target_qq), None) is not None
        self._wakeup.set()
        return existed

    def snapshot(self):
        now = time.monotonic()
        with self._lock:
            return {
                str(qq): {
                    "interval": task["interval"],
                    "next_in": round(max(0.0, task["next_at"] - now), 1),
                }
                for qq, task in self._tasks.items()
            }

    def run(self):
        while True:
            self._wakeup.clear()
            now = time.monotonic()
            with self._lock:
                due = [
                    (qq, task["interval"])
                    for qq, task in self._tasks.items()
                    if task["next_at"] <= now
                ]
                next_at = min(
                    (task["next_at"] for task in self._tasks.values()), default=None
                )

            if not due:
                timeout = None if next_at is None else max(0.05, next_at - time.monotonic())
                self._wakeup.wait(timeout)
                continue

            for target_qq, interval in due:
                try:
                    send_mention(target_qq)
                except Exception:
                    logger.exception("Failed to mention qq=%s", target_qq)
                # 发送期间可能被 !0秒 停掉，重新确认一下再排下一次。
                with self._lock:
                    task = self._tasks.get(target_qq)
                    if task is not None and task["interval"] == interval:
                        task["next_at"] = time.monotonic() + interval


MANAGER = MentionManager(MIN_INTERVAL, MAX_INTERVAL)


def apply_command(target_qq, seconds):
    """执行一条已解析出来的命令。"""
    if target_qq == int(BOT_QQ):
        return
    if seconds == 0:
        removed = MANAGER.stop(target_qq)
        logger.info("Stop mention qq=%s changed=%s", target_qq, removed)
        return
    if seconds < MIN_INTERVAL:
        logger.warning(
            "Interval %ss below minimum, clamped to %ss (qq=%s)",
            seconds,
            MIN_INTERVAL,
            target_qq,
        )
    interval = MANAGER.start(target_qq, seconds)
    if seconds > MAX_INTERVAL:
        logger.warning(
            "Interval %ss above maximum, clamped to %ss (qq=%s)",
            seconds,
            MAX_INTERVAL,
            target_qq,
        )
    logger.info("Start mention qq=%s every %ss", target_qq, interval)


def handle_event(event):
    if event.get("post_type") != "message":
        return
    if event.get("message_type") != "group":
        return

    try:
        group_id = int(event.get("group_id", 0))
        user_id = int(event.get("user_id", 0))
    except (TypeError, ValueError):
        return

    # 只认这一个群、这一个用户，其它一律安静忽略。
    if group_id != TARGET_GROUP_ID or user_id != ALLOWED_USER_ID:
        return

    text, targets = extract_text_and_targets(event)
    match = COMMAND_RE.match(text)
    if not match:
        return

    seconds = int(match.group(1))
    if not targets:
        logger.info("Command without target ignored user=%s text=%r", user_id, text)
        return

    logger.info(
        "Command from user=%s group=%s text=%r targets=%s",
        user_id,
        group_id,
        text,
        targets,
    )
    for target_qq in targets:
        apply_command(target_qq, seconds)


class OneBotWebhookHandler(BaseHTTPRequestHandler):
    server_version = "MentionBotWebhook/1.0"

    def do_GET(self):
        if self.path == "/health":
            self.send_json(
                200,
                {
                    "ok": True,
                    "bot_qq": BOT_QQ,
                    "group_id": TARGET_GROUP_ID,
                    "allowed_user_id": ALLOWED_USER_ID,
                    "mentions": MANAGER.snapshot(),
                },
            )
            return
        self.send_json(404, {"ok": False, "message": "not found"})

    def read_request_body(self):
        transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
        if "chunked" not in transfer_encoding:
            length = int(self.headers.get("Content-Length", "0"))
            return self.rfile.read(length)

        chunks = []
        while True:
            size_line = self.rfile.readline().strip()
            if not size_line:
                break
            size = int(size_line.split(b";", 1)[0], 16)
            if size == 0:
                self.rfile.readline()
                break
            chunks.append(self.rfile.read(size))
            self.rfile.readline()
        return b"".join(chunks)

    def do_POST(self):
        body = self.read_request_body()
        try:
            if not body:
                self.send_json(200, {"ok": True})
                return

            text_body = body.decode("utf-8", errors="replace")
            content_type = self.headers.get("Content-Type", "")
            if "application/x-www-form-urlencoded" in content_type:
                parsed = urllib.parse.parse_qs(text_body)
                payload = parsed.get("payload") or parsed.get("data") or parsed.get("event")
                if not payload:
                    logger.warning("Ignoring form POST without JSON payload")
                    self.send_json(200, {"ok": True})
                    return
                event = json.loads(payload[0])
            else:
                event = json.loads(text_body)

            handle_event(event)
        except Exception:
            logger.exception("Failed to handle OneBot event body=%r", body[:500])
            self.send_json(200, {"ok": False})
            return

        self.send_json(200, {"ok": True})

    def log_message(self, fmt, *args):
        logger.debug("%s - %s", self.address_string(), fmt % args)

    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    logger.info("Mention bot QQ: %s", BOT_QQ)
    logger.info("Watching group: %s  allowed user: %s", TARGET_GROUP_ID, ALLOWED_USER_ID)
    logger.info("Webhook: http://%s:%s (POST any path, GET /health)", HOST, PORT)
    logger.info("NapCat API: %s", NAPCAT_API_BASE)
    logger.info(
        "Interval range: %ss ~ %ss  min guard enabled", MIN_INTERVAL, MAX_INTERVAL
    )

    worker = threading.Thread(target=MANAGER.run, name="mention-worker", daemon=True)
    worker.start()

    try:
        server = ThreadingHTTPServer((HOST, PORT), OneBotWebhookHandler)
    except OSError as exc:
        logger.error("Cannot start server on %s:%s: %s", HOST, PORT, exc)
        return 1

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping")
        return 0


if __name__ == "__main__":
    sys.exit(main())
