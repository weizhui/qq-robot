#!/usr/bin/env python3
import hashlib
import json
import logging
import os
import random
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

import xingmang_voice
from reply_interface import (
    build_ai_answer,
    build_anime_recommendation,
    build_reply,
    build_story_chain_result,
    daily_visual,
    ensure_daily_state,
    expire_story_game,
    today_nebula,
)


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
SCHEDULED_CONTENT_STATE_PATH = BASE_DIR / "runtime_cache" / "scheduled_content_state.json"
PROACTIVE_STATE_PATH = BASE_DIR / "runtime_cache" / "proactive_reply_state.json"
EXPRESSION_PACK_PATH = BASE_DIR / "runtime_cache" / "expression_pack.json"
NAPCAT_API_BASE = os.getenv("NAPCAT_API_BASE", "").rstrip("/")
NAPCAT_ACCESS_TOKEN = os.getenv("NAPCAT_ACCESS_TOKEN", "")
PROACTIVE_REPLY_ENABLED = os.getenv("PROACTIVE_REPLY_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
PROACTIVE_CHECK_SECONDS = int(os.getenv("PROACTIVE_CHECK_SECONDS", "900"))
PROACTIVE_REPLY_PROBABILITY = float(os.getenv("PROACTIVE_REPLY_PROBABILITY", "0.18"))
PROACTIVE_REPLY_COOLDOWN_SECONDS = int(os.getenv("PROACTIVE_REPLY_COOLDOWN_SECONDS", "7200"))
PROACTIVE_CONTEXT_MESSAGES = int(os.getenv("PROACTIVE_CONTEXT_MESSAGES", "5"))
PROACTIVE_MIN_MESSAGES = int(os.getenv("PROACTIVE_MIN_MESSAGES", "3"))
PROACTIVE_QUIET_START_HOUR = int(os.getenv("PROACTIVE_QUIET_START_HOUR", "1"))
PROACTIVE_QUIET_END_HOUR = int(os.getenv("PROACTIVE_QUIET_END_HOUR", "7"))
EXPRESSION_REFRESH_SECONDS = int(os.getenv("EXPRESSION_REFRESH_SECONDS", str(24 * 60 * 60)))
EXPRESSION_APPEND_PROBABILITY = float(os.getenv("EXPRESSION_APPEND_PROBABILITY", "0.32"))
EXPRESSION_SOURCE_URLS = [
    url.strip() for url in os.getenv(
        "EXPRESSION_SOURCE_URLS",
        "https://raw.githubusercontent.com/oclif/kaomoji/master/src/kaomoji.ts,"
        "https://gist.githubusercontent.com/uuz2333/7d976d46127de3ffd2c7c11365ce39d0/raw/kaomoji.dict.yaml",
    ).split(",") if url.strip()
]
CUTE_LINE_EMOJIS = ("✨", "🛸", "💫", "🥤", "🌟", "📡", "🌙", "₍ᐢ.ˬ.ᐢ₎", "(˶˃ ᵕ ˂˶)", "ฅ՞•ﻌ•՞ฅ")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


# 只在 0、6、12、18 点报时，其余整点保持安静。
TIME_CHIME_HOURS = (0, 6, 12, 18)

TIME_CHIME_LINES = (
    "整点信标已点亮，星芒触角准时敲钟。",
    "全息电子眼扫过表盘：时间没有偷懒。",
    "能量汽水冒了一个泡，提示大家换个姿势继续前进。",
    "深空频道发来整点回声，收到请眨眨眼。",
    "星芒把时间拎出来抖了抖：又是新的一小时。",
    "赛博小闹钟完成跃迁，准点抵达当前小时。",
    "宇宙钟摆轻轻一晃，整点到站。",
    "触角校时成功，大家的时间线仍然稳定。",
)

# 每个报时点附带对应的事件提醒。
TIME_CHIME_EVENTS = {
    0: (
        "🌙【星芒零点提醒】",
        "零点到站，深空频道切换到低功耗模式。记得照顾好自己的时间线 💫",
    ),
    6: (
        "🌅【星芒六点提醒】",
        "六点晨光抵达，触角完成校时。喝口水，慢慢把电量调回在线状态 🌟",
    ),
    12: (
        "🍚【星芒午间提醒】",
        "正午能量告急，该吃午饭啦。好好吃饭，饭后小憩一会儿，"
        "下午才有力气继续折腾。别忘了喝水 🥤",
    ),
    18: (
        "🌆【星芒收工提醒】",
        "十八点收工钟响，该下班啦。放下手头的事，"
        "去吃顿晚饭、散散步，把耗掉的电量慢慢补回来 🛸",
    ),
}


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("qq-bot")

RECENT_GROUP_MESSAGES = {}
RECENT_GROUP_LOCK = threading.Lock()
EXPRESSION_PACK = []
EXPRESSION_LOCK = threading.Lock()


FALLBACK_EXPRESSIONS = (
    "(˶˃ ᵕ ˂˶)", "₍ᐢ.ˬ.ᐢ₎", "ฅ՞•ﻌ•՞ฅ", "(๑•̀ㅂ•́)و✧", "(｡•̀ᴗ-)✧",
    "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧", "(っ˘ω˘ς)", "٩(ˊᗜˋ*)و", "( ´͈ ᵕ `͈ )◞♡", "꒰ঌ(˶˃ ᵕ ˂˶)໒꒱",
    "✧*｡٩(ˊᗜˋ*)و✧*｡", "╰(*°▽°*)╯", "＼(＾O＾)／", "(づ｡◕‿‿◕｡)づ", "(ღ˘⌣˘ღ)",
    "(✿◡‿◡)", "(*/ω＼*)", "(。﹏。*)", "(⊙﹏⊙)", "(◕ᴥ◕ʋ)",
    "=•ω•=", "^._.^", "(=^･ｪ･^=)", "(・3・)", "(☞ﾟ∀ﾟ)☞",
    "(｡･∀･)ﾉﾞ", "(≧▽≦)", "(๑˃ᴗ˂)ﻭ", "(๑>◡<๑)", "(੭ˊᵕˋ)੭",
    "(๑•̀ㅁ•́ฅ)", "(ง •̀_•́)ง", "ᕦ(òᴥó)ᕥ", "୧(▲ᴗ▲)ノ", "ヽ༼ຈل͜ຈ༽ﾉ",
    "╮(╯▽╰)╭", "(￣▽￣)~*", "(‾◡◝)", "(。・_・)/~~~", "(☞ﾟヮﾟ)☞",
    "(ಡ_ಡ)☞", "(◔_◔)", "ಠ_ಠ", "→_←", "←_←",
    "(－‸ლ)", "(°ー°〃)", "(⊙＿⊙')", "(´･ω･`)", "(´｡• ᵕ •｡`)",
    "(๑•́ ₃ •̀๑)", "(๑•́ ₃ •̀๑)੭", "(๑•̀ㅂ•́)و", "(˵ •̀ ᴗ - ˵ ) ✧", "(˶ᵔ ᵕ ᵔ˶)",
    "(˶ᵔ ᵕ ᵔ˶)ﾉ", "(˶ˊᵕˋ˵)", "(ﾉ´ヮ`)ﾉ*: ･ﾟ", "(｡･ω･｡)ﾉ♡", "(๑´ㅂ`๑)",
    "(๑˘︶˘๑)", "(˘︶˘).｡.:*♡", "(๑˃̵ᴗ˂̵)و", "(๑╹◡╹)ﾉ", "(๑•̀ㅁ•́ฅ✧",
    "(ฅ´ω`ฅ)", "ฅ( ̳• ◡ • ̳)ฅ", "ฅ^•ﻌ•^ฅ",
    "✨", "💫", "🌟", "🛸", "📡", "🪐", "🌙", "🥤", "🤖", "🫧",
    "⭐", "🌌", "🔭", "🎧", "🎮", "📚", "🎬", "🎴", "🧠", "💭",
)


def load_expression_pack():
    global EXPRESSION_PACK
    try:
        data = json.loads(EXPRESSION_PACK_PATH.read_text(encoding="utf-8"))
        expressions = data.get("expressions") if isinstance(data, dict) else data
        if isinstance(expressions, list):
            with EXPRESSION_LOCK:
                EXPRESSION_PACK = [str(item) for item in expressions if str(item).strip()]
    except (OSError, json.JSONDecodeError):
        with EXPRESSION_LOCK:
            EXPRESSION_PACK = list(FALLBACK_EXPRESSIONS)


def parse_expression_candidates(text):
    candidates = set()
    # Only accept complete quoted values from online sources. This avoids source-code
    # fragments such as "words: [" or partial kaomoji split by whitespace.
    for match in re.finditer(r'["\']([^"\'\n]{2,36})["\']', text):
        value = match.group(1).strip()
        if looks_like_expression(value):
            candidates.add(value)
    return candidates


def looks_like_expression(value):
    if not (2 <= len(value) <= 36):
        return False
    value = value.strip()
    banned_fragments = (
        "http", "function", "const", "Object.", "words", "dead", "pi", "gotit",
        "bearflip", "return", "export", "import", "=>", "};", "[{", "}]",
        "true", "false", "undefined",
    )
    if any(fragment in value for fragment in banned_fragments):
        return False
    if any(ch in value for ch in "{}[];:"):
        return False
    if re.search(r"[A-Za-z]{4,}", value):
        return False
    if value in {",", "<-", ">>", "♪♬", "\\(", "\\）"}:
        return False
    if value.count("(") != value.count(")"):
        return False
    if value.count("（") != value.count("）"):
        return False
    has_emoji = EMOJI_RE.search(value) is not None
    face_like = bool(re.search(r"[()（）].*[ω∀Д▽ᴗᵕ˃˂•̀́˘˶｡♡✧ฅﻌᐢﾉง٩وっ◕ヮㅂᵔ╹･].*[()（）]", value))
    cute_symbols = any(ch in value for ch in "♡☆✧꒰꒱ฅᐢ₍₎ﾉง٩وっღ༼༽╯╰ノヽᕦ୧ԅ☞✌")
    return has_emoji or (face_like and cute_symbols)


def refresh_expression_pack_once():
    collected = set()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for url in EXPRESSION_SOURCE_URLS:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "xingmang-expression-refresh"})
            with opener.open(request, timeout=12) as response:
                body = response.read().decode("utf-8", errors="replace")
            collected.update(parse_expression_candidates(body))
        except Exception:
            logger.exception("Failed to refresh expression source: %s", url)
    online = [item for item in sorted(collected) if item not in FALLBACK_EXPRESSIONS]
    random.shuffle(online)
    expressions = list(FALLBACK_EXPRESSIONS) + online[:40]
    EXPRESSION_PACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPRESSION_PACK_PATH.write_text(json.dumps({
        "updated_at": datetime.now(BEIJING_TZ).isoformat(),
        "sources": EXPRESSION_SOURCE_URLS,
        "expressions": expressions,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    with EXPRESSION_LOCK:
        EXPRESSION_PACK[:] = expressions
    logger.info("Expression pack refreshed: %s items", len(expressions))


def expression_refresh_worker():
    load_expression_pack()
    try:
        refresh_expression_pack_once()
    except Exception:
        logger.exception("Initial expression refresh failed")
    while True:
        time.sleep(max(3600, EXPRESSION_REFRESH_SECONDS))
        try:
            refresh_expression_pack_once()
        except Exception:
            logger.exception("Expression refresh failed")


def start_expression_refresh_worker():
    thread = threading.Thread(target=expression_refresh_worker, name="expression-refresh-worker", daemon=True)
    thread.start()


def pick_expression():
    with EXPRESSION_LOCK:
        pool = list(EXPRESSION_PACK or FALLBACK_EXPRESSIONS)
    return random.choice(pool) if pool else random.choice(FALLBACK_EXPRESSIONS)


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


# 本机调用不走任何代理：环境里可能存在 clash 之类的 http_proxy，
# 否则发往 127.0.0.1 的请求会被代理转发并失败（表现为 HTTP 502）。
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call_napcat(action, payload):
    url = f"{NAPCAT_API_BASE}/{action}"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if NAPCAT_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {NAPCAT_ACCESS_TOKEN}"

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _LOCAL_OPENER.open(request, timeout=10) as response:
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
    return message


def add_cute_emojis(message):
    lines = str(message).splitlines()
    enriched = []
    emoji_index = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("[CQ:"):
            enriched.append(line)
            continue
        if EMOJI_RE.search(line) and random.random() > EXPRESSION_APPEND_PROBABILITY:
            enriched.append(line)
            continue
        if random.random() < EXPRESSION_APPEND_PROBABILITY:
            suffix = pick_expression()
        else:
            suffix = CUTE_LINE_EMOJIS[emoji_index % len(CUTE_LINE_EMOJIS)]
        enriched.append(f"{line} {suffix}")
        emoji_index += 1
    return "\n".join(enriched).rstrip()


def send_group_reply(group_id, message):
    if not message:
        return
    text_message = add_cute_emojis(append_disclaimer(message))

    wants_voice = xingmang_voice.should_reply_with_voice()

    if wants_voice and xingmang_voice.async_enabled():
        call_napcat(
            "send_group_msg",
            {
                "group_id": int(group_id),
                "message": text_message,
            },
        )
        thread = threading.Thread(
            target=send_group_voice_reply,
            args=(group_id, message),
            daemon=True,
        )
        thread.start()
        return

    audio_ref = xingmang_voice.synthesize_reply(message) if wants_voice else ""
    if audio_ref:
        segments = [
            {
                "type": "record",
                "data": {
                    "file": xingmang_voice.onebot_record_file(audio_ref),
                },
            }
        ]
        if xingmang_voice.include_text():
            segments.append({"type": "text", "data": {"text": "\n" + text_message}})
        call_napcat(
            "send_group_msg",
            {
                "group_id": int(group_id),
                "message": segments,
            },
        )
        return

    call_napcat(
        "send_group_msg",
        {
            "group_id": int(group_id),
            "message": text_message,
        },
    )


def send_group_voice_reply(group_id, message):
    audio_ref = xingmang_voice.synthesize_reply(message)
    if not audio_ref:
        return
    try:
        call_napcat(
            "send_group_msg",
            {
                "group_id": int(group_id),
                "message": [
                    {
                        "type": "record",
                        "data": {
                            "file": xingmang_voice.onebot_record_file(audio_ref),
                        },
                    }
                ],
            },
        )
    except Exception:
        logger.exception("Failed to send async voice reply group=%s", group_id)


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


def next_beijing_chime(now=None):
    """返回下一个报时时刻（北京时间 0、6、12、18 点）。"""
    now = now or datetime.now(BEIJING_TZ)
    for hour in TIME_CHIME_HOURS:
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if target > now:
            return target
    return (now + timedelta(days=1)).replace(
        hour=TIME_CHIME_HOURS[0], minute=0, second=0, microsecond=0
    )


def build_time_chime(now=None):
    now = now or datetime.now(BEIJING_TZ)
    line = TIME_CHIME_LINES[now.hour % len(TIME_CHIME_LINES)]
    event_title, event_text = TIME_CHIME_EVENTS[now.hour]
    return f"""🕘【星芒整点报时】
北京时间 {now:%Y-%m-%d %H:00}

{line} 🛸✨

{event_title}
{event_text}"""


def time_chime_worker():
    while True:
        target = next_beijing_chime()
        logger.info("Next time chime at %s", target.isoformat())
        while True:
            sleep_seconds = (target - datetime.now(BEIJING_TZ)).total_seconds()
            if sleep_seconds <= 0:
                break
            time.sleep(sleep_seconds)

        now = datetime.now(BEIJING_TZ)
        if now.hour not in TIME_CHIME_HOURS:
            # 时钟被调整等异常情况下不误报，重新等下一个报时点。
            continue
        message = build_time_chime(now)
        for group_id in sorted(TARGET_GROUP_IDS):
            try:
                send_group_reply(group_id, message)
            except Exception:
                logger.exception("Failed to send time chime group=%s", group_id)


def start_time_chime_worker():
    thread = threading.Thread(target=time_chime_worker, name="time-chime-worker", daemon=True)
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


def load_proactive_state():
    try:
        data = json.loads(PROACTIVE_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_proactive_state(state):
    PROACTIVE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROACTIVE_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_observed_text(event):
    text = normalize_user_message(event)
    text = re.sub(r"\[CQ:[^\]]+\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


def observe_group_message(event):
    if str(event.get("user_id") or "") == BOT_QQ:
        return
    text = normalize_observed_text(event)
    if not text or len(text) < 2:
        return
    if message_mentions_bot(event):
        return
    group_id = int(event.get("group_id", 0))
    item = {
        "message_id": str(event.get("message_id") or event.get("message_seq") or ""),
        "user_id": str(event.get("user_id") or ""),
        "text": text,
        "at": datetime.now(BEIJING_TZ).isoformat(),
    }
    with RECENT_GROUP_LOCK:
        bucket = RECENT_GROUP_MESSAGES.setdefault(group_id, [])
        if item["message_id"] and any(old.get("message_id") == item["message_id"] for old in bucket):
            return
        bucket.append(item)
        del bucket[:-40]


def in_proactive_quiet_hours(now=None):
    now = now or datetime.now(BEIJING_TZ)
    start = PROACTIVE_QUIET_START_HOUR
    end = PROACTIVE_QUIET_END_HOUR
    if start == end:
        return False
    if start < end:
        return start <= now.hour < end
    return now.hour >= start or now.hour < end


def proactive_context_for_group(group_id):
    with RECENT_GROUP_LOCK:
        bucket = list(RECENT_GROUP_MESSAGES.get(group_id, []))
    if len(bucket) < PROACTIVE_MIN_MESSAGES:
        return [], ""
    recent = bucket[-max(1, PROACTIVE_CONTEXT_MESSAGES):]
    digest_src = "|".join(item.get("message_id") or item.get("text", "") for item in recent)
    digest = hashlib.sha256(digest_src.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return recent, digest


def build_local_proactive_reply(messages):
    text = " ".join(item.get("text", "") for item in messages)[-500:]
    expression = pick_expression()
    if any(word in text for word in ("累", "困", "睡", "熬夜", "作业", "考试", "ddl", "DDL")):
        choices = [
            f"星芒探测到疲惫信号，先把电量慢慢充回来吧 {expression}",
            f"深空频道建议：先喝水，再把任务拆小一点，别硬扛呀 {expression}",
        ]
    elif any(word in text for word in ("吃", "饭", "饿", "奶茶", "咖啡", "夜宵")):
        choices = [
            f"检测到食物话题，星芒的能量汽水也开始冒泡了 {expression}",
            f"这条时间线适合补充能量，吃饱一点再继续跃迁 {expression}",
        ]
    elif any(word in text for word in ("笑", "哈哈", "草", "乐", "绷", "好玩")):
        choices = [
            f"这段聊天的欢乐指数有点亮，星芒全息眼在闪 {expression}",
            f"群聊气氛已升温，触角网络收到快乐回声 {expression}",
        ]
    elif any(word in text for word in ("科幻", "星", "宇宙", "电影", "动漫", "小说", "游戏")):
        choices = [
            f"关键词触发星芒雷达：这话题有一点宇宙味道 {expression}",
            f"星芒路过并轻轻点亮一颗小星星：继续讲，我在听 {expression}",
        ]
    else:
        choices = [
            f"星芒短暂冒泡一下，群聊信号稳定，继续继续 {expression}",
            f"触角网络轻轻闪了一下，我路过听见啦 {expression}",
            f"星芒在线围观中，给这段聊天加一点星光 {expression}",
        ]
    return random.choice(choices)


def proactive_reply_worker():
    if not PROACTIVE_REPLY_ENABLED:
        logger.info("Proactive reply disabled")
        return
    while True:
        time.sleep(max(60, PROACTIVE_CHECK_SECONDS))
        if in_proactive_quiet_hours():
            continue
        state = load_proactive_state()
        now_ts = time.time()
        for group_id in sorted(TARGET_GROUP_IDS):
            group_state = state.setdefault(str(group_id), {})
            last_reply_at = float(group_state.get("last_reply_at") or 0)
            if now_ts - last_reply_at < PROACTIVE_REPLY_COOLDOWN_SECONDS:
                continue
            if random.random() > PROACTIVE_REPLY_PROBABILITY:
                continue
            messages, digest = proactive_context_for_group(group_id)
            if not messages or not digest:
                continue
            if digest == group_state.get("last_digest"):
                continue
            used = set(group_state.get("used_digests") or [])
            if digest in used:
                continue
            reply = build_local_proactive_reply(messages)
            try:
                send_group_reply(group_id, reply)
            except Exception:
                logger.exception("Proactive reply failed group=%s", group_id)
                continue
            used.add(digest)
            group_state.update({
                "last_reply_at": now_ts,
                "last_digest": digest,
                "used_digests": list(sorted(used))[-80:],
            })
            save_proactive_state(state)


def start_proactive_reply_worker():
    thread = threading.Thread(target=proactive_reply_worker, name="proactive-reply-worker", daemon=True)
    thread.start()


def load_scheduled_content_state():
    try:
        return json.loads(SCHEDULED_CONTENT_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_scheduled_content_state(state):
    SCHEDULED_CONTENT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULED_CONTENT_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


SCHEDULED_CONTENT_JOBS = (
    ("today_nebula", 8, "今日星芒"),
    ("star_map", 14, "今日星图"),
    ("anime", 20, "动漫推荐"),
)


def next_scheduled_content_time(now=None):
    now = now or datetime.now(BEIJING_TZ)
    candidates = []
    for key, hour, label in SCHEDULED_CONTENT_JOBS:
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        candidates.append((target, key, label))
    return min(candidates, key=lambda item: item[0])


def build_scheduled_content_message(job_key):
    if job_key == "today_nebula":
        return today_nebula(ensure_daily_state())
    if job_key == "star_map":
        return daily_visual(ensure_daily_state(), "star")
    if job_key == "anime":
        return build_anime_recommendation()
    return ""


def scheduled_content_worker():
    while True:
        target, job_key, label = next_scheduled_content_time()
        logger.info("Next scheduled content %s at %s", label, target.isoformat())
        while True:
            sleep_seconds = (target - datetime.now(BEIJING_TZ)).total_seconds()
            if sleep_seconds <= 0:
                break
            time.sleep(min(sleep_seconds, 3600))

        today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
        state = load_scheduled_content_state()
        sent_key = f"{job_key}:{today}"
        if state.get(sent_key):
            continue
        message = build_scheduled_content_message(job_key)
        if not message:
            continue
        sent_groups = []
        for group_id in sorted(TARGET_GROUP_IDS):
            try:
                send_group_reply(group_id, message)
                sent_groups.append(group_id)
            except Exception:
                logger.exception("Failed to push scheduled content=%s group=%s", job_key, group_id)
        if sent_groups:
            state[sent_key] = {"at": datetime.now(BEIJING_TZ).isoformat(), "groups": sent_groups}
            save_scheduled_content_state(state)


def start_scheduled_content_worker():
    thread = threading.Thread(target=scheduled_content_worker, name="scheduled-content-worker", daemon=True)
    thread.start()


def story_chain_timeout_worker():
    """每 5 分钟检查一次：接龙局超过 2 小时无人操作就自动结算。"""
    while True:
        time.sleep(300)
        try:
            expired = expire_story_game()
        except Exception:
            logger.exception("Story chain timeout check failed")
            continue
        if not expired:
            continue
        group_id, message = expired
        try:
            send_group_reply(int(group_id), message)
            logger.info("Story chain auto settled group=%s", group_id)
        except Exception:
            logger.exception("Failed to send story chain timeout notice group=%s", group_id)


def start_story_chain_timeout_worker():
    thread = threading.Thread(target=story_chain_timeout_worker,
                              name="story-chain-timeout-worker", daemon=True)
    thread.start()


def handle_event(event):
    if event.get("post_type") != "message":
        return
    if event.get("message_type") != "group":
        return
    event_group_id = int(event.get("group_id", 0))
    if event_group_id not in TARGET_GROUP_IDS:
        return

    observe_group_message(event)

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
        if reply.get("immediate"):
            send_group_reply(event_group_id, reply["immediate"])
        thread = threading.Thread(
            target=send_ai_answer,
            args=(event_group_id, reply["question"]),
            # 带上提问者身份，后台线程才能取到他的长期记忆
            kwargs={"user_id": reply.get("user_id")},
            daemon=True,
        )
        thread.start()
        return
    if isinstance(reply, dict) and reply.get("type") == "story_chain":
        send_group_reply(event_group_id, reply["immediate"])
        thread = threading.Thread(
            target=send_story_chain_reply,
            args=(event_group_id, reply["user_id"], reply["story"]),
            daemon=True,
        )
        thread.start()
        return
    send_group_reply(event_group_id, reply)


def send_ai_answer(group_id, question, user_id=None):
    logger.info("DeepSeek question started group=%s user=%s question=%r",
                group_id, user_id, question[:120])
    answer = build_ai_answer(question, user_id=user_id, group_id=group_id)
    send_group_reply(group_id, answer)
    logger.info("DeepSeek question finished group=%s", group_id)


def send_story_chain_reply(group_id, user_id, story_text):
    """后台线程：调用 DeepSeek 评分后把结果发回群里。"""
    logger.info("Story chain scoring started group=%s user=%s", group_id, user_id)
    try:
        message = build_story_chain_result(group_id, user_id, story_text)
    except Exception:
        logger.exception("Story chain scoring failed group=%s user=%s", group_id, user_id)
        message = "😵【星芒走神了】这次的故事没能评上分，再发一次试试吧 ✨"
    send_group_reply(group_id, message)
    logger.info("Story chain scoring finished group=%s user=%s", group_id, user_id)


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
    start_scheduled_content_worker()
    start_time_chime_worker()
    start_expression_refresh_worker()
    start_proactive_reply_worker()
    start_story_chain_timeout_worker()

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
