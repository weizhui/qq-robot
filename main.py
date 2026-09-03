#!/usr/bin/env python3
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
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from reply_interface import build_ai_answer, build_anime_recommendation, build_reply


BOT_QQ = str(os.getenv("BOT_QQ", "")).strip()
TARGET_GROUP_IDS = {
    int(group_id.strip())
    for group_id in os.getenv("TARGET_GROUP_IDS", os.getenv("TARGET_GROUP_ID", "")).split(",")
    if group_id.strip()
}
HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", "8080"))
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
BASE_DIR = Path(__file__).resolve().parent
ANIME_PUSH_STATE_PATH = BASE_DIR / "runtime_cache" / "anime_push_state.json"
NAPCAT_API_BASE = os.getenv("NAPCAT_API_BASE", "").rstrip("/")
NAPCAT_ACCESS_TOKEN = os.getenv("NAPCAT_ACCESS_TOKEN", "")
DISCLAIMER = "本项目仅供娱乐，不进行任何商业用处，如有侵权，请联系维护者进行删除。"
DISCLAIMER_REPLY_MARKERS = (
    "【星云·赛博帮助手册】",
    "【今日星云】",
    "【今日星图】",
    "【今日壁纸】",
    "【今日海报】",
)

CUTE_LINE_EMOJIS = ("✨", "🛸", "💫", "🥤", "🌟", "📡", "🌙")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


TIME_CHIME_LINES = (
    "整点信标已点亮，星云触角准时敲钟。",
    "全息电子眼扫过表盘：时间没有偷懒。",
    "能量汽水冒了一个泡，提示大家换个姿势继续前进。",
    "深空频道发来整点回声，收到请眨眨眼。",
    "星云把时间拎出来抖了抖：又是新的一小时。",
    "赛博小闹钟完成跃迁，准点抵达当前小时。",
    "宇宙钟摆轻轻一晃，整点到站。",
    "触角校时成功，大家的时间线仍然稳定。",
)


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("qq-bot")


def message_mentions_bot(event):
    message = event.get("message")
    if isinstance(message, list):
        for segment in message:
            if not isinstance(segment, dict):
                continue
            if segment.get("type") != "at":
                continue
            data = segment.get("data") or {}
            if str(data.get("qq")) in {BOT_QQ, "all"}:
                return True

    raw_message = str(event.get("raw_message") or event.get("message") or "")
    return f"[CQ:at,qq={BOT_QQ}]" in raw_message or "[CQ:at,qq=all]" in raw_message


def strip_bot_mentions(text):
    text = re.sub(rf"\[CQ:at,qq={re.escape(BOT_QQ)}\]", "", text)
    text = text.replace("[CQ:at,qq=all]", "")
    return text.strip()


def normalize_user_message(event):
    raw_message = str(event.get("raw_message") or "")
    if raw_message:
        return strip_bot_mentions(raw_message)

    message = event.get("message")
    if not isinstance(message, list):
        return strip_bot_mentions(str(message or ""))

    parts = []
    for segment in message:
        if not isinstance(segment, dict):
            continue
        segment_type = segment.get("type")
        data = segment.get("data") or {}
        if segment_type == "text":
            parts.append(str(data.get("text") or ""))
        elif segment_type != "at":
            parts.append(f"[{segment_type}]")
    return " ".join(part.strip() for part in parts if part).strip()


def call_napcat(action, payload):
    url = f"{NAPCAT_API_BASE}/{action}"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if NAPCAT_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {NAPCAT_ACCESS_TOKEN}"

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            if response_body:
                logger.debug("NapCat response: %s", response_body)
    except urllib.error.HTTPError as exc:
        logger.error("NapCat API returned HTTP %s for %s", exc.code, action)
        raise
    except urllib.error.URLError as exc:
        logger.error("Cannot reach NapCat API at %s: %s", url, exc)
        raise


def append_disclaimer(message):
    if not message:
        return message
    text = str(message).rstrip()
    if not any(marker in text for marker in DISCLAIMER_REPLY_MARKERS):
        return text
    if DISCLAIMER in text:
        return text
    return f"{text}\n\n{DISCLAIMER}"


def add_cute_emojis(message):
    lines = str(message).splitlines()
    enriched = []
    emoji_index = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("[CQ:") or EMOJI_RE.search(line):
            enriched.append(line)
            continue
        enriched.append(f"{line} {CUTE_LINE_EMOJIS[emoji_index % len(CUTE_LINE_EMOJIS)]}")
        emoji_index += 1
    return "\n".join(enriched).rstrip()


def send_group_reply(group_id, message):
    if not message:
        return
    message = add_cute_emojis(append_disclaimer(message))
    call_napcat(
        "send_group_msg",
        {
            "group_id": int(group_id),
            "message": message,
        },
    )


def load_anime_push_state():
    try:
        return json.loads(ANIME_PUSH_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_anime_push_state(state):
    ANIME_PUSH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ANIME_PUSH_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def next_beijing_8am(now=None):
    now = now or datetime.now(BEIJING_TZ)
    target = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target


def next_beijing_hour(now=None):
    now = now or datetime.now(BEIJING_TZ)
    target = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return target


def build_time_chime(now=None):
    now = now or datetime.now(BEIJING_TZ)
    line = TIME_CHIME_LINES[now.hour % len(TIME_CHIME_LINES)]
    return f"""🕘【星云整点报时】
北京时间 {now:%Y-%m-%d %H:00}

{line} 🛸✨"""


def hourly_time_chime_worker():
    while True:
        target = next_beijing_hour()
        sleep_seconds = max(1, (target - datetime.now(BEIJING_TZ)).total_seconds())
        logger.info("Next hourly time chime at %s", target.isoformat())
        time.sleep(sleep_seconds)

        now = datetime.now(BEIJING_TZ)
        message = build_time_chime(now)
        for group_id in sorted(TARGET_GROUP_IDS):
            try:
                send_group_reply(group_id, message)
            except Exception:
                logger.exception("Failed to send hourly time chime group=%s", group_id)


def start_hourly_time_chime_worker():
    thread = threading.Thread(target=hourly_time_chime_worker, name="hourly-time-chime-worker", daemon=True)
    thread.start()


def anime_daily_push_worker():
    while True:
        target = next_beijing_8am()
        sleep_seconds = max(1, (target - datetime.now(BEIJING_TZ)).total_seconds())
        logger.info("Next anime recommendation push at %s", target.isoformat())
        time.sleep(sleep_seconds)

        today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
        state = load_anime_push_state()
        if state.get("last_sent_date") == today:
            continue

        message = build_anime_recommendation()
        sent_groups = []
        for group_id in sorted(TARGET_GROUP_IDS):
            try:
                send_group_reply(group_id, message)
                sent_groups.append(group_id)
            except Exception:
                logger.exception("Failed to push anime recommendation group=%s", group_id)
        if sent_groups:
            save_anime_push_state({"last_sent_date": today, "groups": sent_groups})


def start_anime_daily_push_worker():
    thread = threading.Thread(target=anime_daily_push_worker, name="anime-daily-push-worker", daemon=True)
    thread.start()


def handle_event(event):
    if event.get("post_type") != "message":
        return
    if event.get("message_type") != "group":
        return
    event_group_id = int(event.get("group_id", 0))
    if event_group_id not in TARGET_GROUP_IDS:
        return
    if not message_mentions_bot(event):
        return

    incoming_text = normalize_user_message(event)
    logger.info(
        "Mention received group=%s user=%s text=%r",
        event.get("group_id"),
        event.get("user_id"),
        incoming_text,
    )

    reply = build_reply(
        message=incoming_text,
        event=event,
        bot_qq=BOT_QQ,
        group_id=event_group_id,
    )
    if isinstance(reply, dict) and reply.get("type") == "deepseek_question":
        send_group_reply(event_group_id, reply["immediate"])
        thread = threading.Thread(
            target=send_ai_answer,
            args=(event_group_id, reply["question"]),
            daemon=True,
        )
        thread.start()
        return
    send_group_reply(event_group_id, reply)


def send_ai_answer(group_id, question):
    logger.info("DeepSeek question started group=%s question=%r", group_id, question[:120])
    answer = build_ai_answer(question)
    send_group_reply(group_id, answer)
    logger.info("DeepSeek question finished group=%s", group_id)


class OneBotWebhookHandler(BaseHTTPRequestHandler):
    server_version = "QQBotWebhook/1.0"

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"ok": True})
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
                logger.info("Empty POST received path=%s headers=%s", self.path, dict(self.headers))
                self.send_json(200, {"ok": True})
                return

            text_body = body.decode("utf-8", errors="replace")
            content_type = self.headers.get("Content-Type", "")
            logger.info("POST path=%s content_type=%s body=%r", self.path, content_type, text_body[:500])

            if "application/x-www-form-urlencoded" in content_type:
                parsed = urllib.parse.parse_qs(text_body)
                payload = parsed.get("payload") or parsed.get("data") or parsed.get("event")
                if not payload:
                    logger.warning("Ignoring form POST without JSON payload: %r", text_body[:500])
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
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    logger.info("Bot QQ: %s", BOT_QQ)
    logger.info("Listening groups: %s", sorted(TARGET_GROUP_IDS))
    logger.info("Webhook path: /onebot host=%s port=%s", HOST, PORT)
    logger.info("NapCat API: %s", NAPCAT_API_BASE)
    start_anime_daily_push_worker()
    start_hourly_time_chime_worker()

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
