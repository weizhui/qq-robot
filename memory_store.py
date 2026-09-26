#!/usr/bin/env python3
"""星芒的长期记忆：用户画像 + 群内对话上下文。

存储位置：runtime_cache/memory.json（运行缓存，已被 .gitignore 排除）。

只记三类东西，不多采集：
1. 群里 @ 星芒 时发来的文本；
2. 星芒自己回过的内容；
3. 从这些文本里统计出的偏好、身份、语气和活跃时段。

隐私开关（普通群友就能用，不占每日配额）：
    /我的画像   查看星芒记住了什么
    /忘记我     一键清空自己的全部记忆

环境变量：
    MEMORY_ENABLED        默认 1，设为 0 可整体关闭记忆功能
    MEMORY_PATH           记忆文件路径，默认 runtime_cache/memory.json
    MEMORY_MAX_USERS      最多保留多少位用户画像，默认 500（超出按最后活跃时间淘汰）
    MEMORY_HISTORY_TURNS  每个群保留最近多少轮对话，默认 6（0 表示不留上下文）
    MEMORY_MIN_SAMPLES    攒够多少条发言才启用语气画像，默认 3
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "runtime_cache"
MEMORY_PATH = Path(os.getenv("MEMORY_PATH", str(CACHE_DIR / "memory.json")))


def _env_flag(name, default=True):
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def _env_int(name, default):
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


MEMORY_ENABLED = _env_flag("MEMORY_ENABLED", True)
MEMORY_MAX_USERS = max(10, _env_int("MEMORY_MAX_USERS", 500))
MEMORY_HISTORY_TURNS = max(0, _env_int("MEMORY_HISTORY_TURNS", 6))
MEMORY_MIN_SAMPLES = max(1, _env_int("MEMORY_MIN_SAMPLES", 3))

MAX_NOTES = 20
MAX_LABELS = 4

_LOCK = threading.RLock()


# ---------------------------------------------------------------- 文本特征

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
LAUGH_RE = re.compile(r"哈哈|嘿嘿|嘻嘻|hhh+|233|www|笑死|草", re.I)
CUTE_RE = re.compile(r"[呀啦哦嘛耶呗诶]|~|～")
QUESTION_RE = re.compile(r"[?？]")
EXCLAIM_RE = re.compile(r"[!！]")
CLEAN_RE = re.compile(r"\s+")

# 话题关键词表：命中即给对应话题 +1，用于个性化推荐和画像展示
TOPIC_KEYWORDS = {
    "天文航天": (
        "黑洞", "星系", "宇宙", "星云", "行星", "恒星", "月球", "火星", "金星", "木星",
        "土星", "银河", "天文", "望远镜", "空间站", "飞船", "火箭", "NASA", "星图",
    ),
    "科幻小说": ("小说", "荐书", "读书", "科幻", "三体", "刘慈欣", "阿西莫夫", "书单", "特德·姜"),
    "电影": ("电影", "荐影", "影片", "影院", "看片", "银翼杀手", "星际穿越"),
    "动漫": ("动漫", "动画", "番剧", "漫画", "anime", "追番"),
    "游戏": ("游戏", "开黑", "主机", "steam", "手游", "电竞"),
    "编程技术": ("代码", "编程", "程序", "算法", "服务器", "部署", "python", "bug", "接口"),
    "学习生活": ("考试", "作业", "上课", "论文", "实验", "复习", "ddl", "毕业", "社团"),
    "情绪吐槽": ("累", "emo", "难过", "开心", "吐槽", "崩溃", "焦虑", "烦"),
}

# 指令 → 话题，让「常用指令」也能喂给推荐
COMMAND_TOPIC = {
    "荐书": "科幻小说",
    "荐影": "电影",
    "动漫": "动漫",
    "冷知识": "天文航天",
    "星图": "天文航天",
    "壁纸": "天文航天",
    "海报": "天文航天",
}

# 自我描述类抽取，只认最明确的几种说法，避免误记
IDENTITY_RES = (
    re.compile(r"我(?:是|叫)\s*([^\s，。！？,.!?；;：:]{2,16})"),
    re.compile(r"叫我\s*([^\s，。！？,.!?；;：:]{1,16})"),
)
LIKE_RE = re.compile(r"我(?:最|很|超|挺)?(?:喜欢|爱看|爱听|爱玩|爱|偏好)\s*([^\s，。！？,.!?；;：:]{1,16})")
# 否定必须显式出现，否则「我喜欢《三体》」会被误判成不喜欢
DISLIKE_RE = re.compile(
    r"我(?:不太|不|最不|特别不|超不)(?:喜欢|爱看|爱听|爱玩|爱)\s*([^\s，。！？,.!?；;：:]{1,16})"
    r"|我(?:很|超|特别|最)?(?:讨厌|烦)\s*([^\s，。！？,.!?；;：:]{1,16})"
)
NOTE_RE = re.compile(r"记住\s*[:：]?\s*(.{2,40})")

_DROP_PREFIX_RE = re.compile(r"^(?:个|一名|一个|位|那种|这种)")


# ---------------------------------------------------------------- 读写

def _now():
    return datetime.now(BEIJING_TZ)


def _clean(text):
    return CLEAN_RE.sub(" ", str(text or "")).strip()


def _truncate(text, limit):
    text = _clean(text)
    return text if len(text) <= limit else text[:limit] + "…"


def _empty_user(uid):
    return {
        "user_id": uid,
        "nickname": "",
        "group_ids": [],
        "first_seen": "",
        "last_seen": "",
        "message_count": 0,
        "command_counts": {},
        "topics": {},
        "active_hours": {},
        "likes": [],
        "dislikes": [],
        "identities": [],
        "notes": [],
        "tone": {
            "samples": 0, "total_len": 0, "emoji": 0,
            "laugh": 0, "cute": 0, "question": 0, "exclaim": 0, "long": 0,
        },
        "history": {},
    }


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _str_map(raw):
    if not isinstance(raw, dict):
        return {}
    return {str(k): _int(v) for k, v in raw.items() if _int(v) > 0}


def _str_list(raw, limit=MAX_NOTES):
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        text = _clean(item)[:40]
        if text and text not in result:
            result.append(text)
    return result[-limit:]


def _normalize_user(raw, uid):
    user = _empty_user(uid)
    if not isinstance(raw, dict):
        return user
    user["nickname"] = _clean(raw.get("nickname"))[:32]
    user["group_ids"] = [str(g) for g in _str_list(raw.get("group_ids"), 10)]
    user["first_seen"] = str(raw.get("first_seen") or "")
    user["last_seen"] = str(raw.get("last_seen") or "")
    user["message_count"] = max(0, _int(raw.get("message_count")))
    user["command_counts"] = _str_map(raw.get("command_counts"))
    user["topics"] = _str_map(raw.get("topics"))
    user["active_hours"] = _str_map(raw.get("active_hours"))
    user["likes"] = _str_list(raw.get("likes"))
    user["dislikes"] = _str_list(raw.get("dislikes"))
    user["identities"] = _str_list(raw.get("identities"), 5)
    user["notes"] = _str_list(raw.get("notes"))
    tone = raw.get("tone")
    if isinstance(tone, dict):
        for key in user["tone"]:
            user["tone"][key] = max(0, _int(tone.get(key)))
    history = raw.get("history")
    if isinstance(history, dict):
        for gid, turns in history.items():
            if not isinstance(turns, list):
                continue
            clean_turns = []
            for turn in turns:
                if not isinstance(turn, dict):
                    continue
                role = "assistant" if turn.get("role") == "assistant" else "user"
                content = _clean(turn.get("content"))
                if content:
                    clean_turns.append({"role": role, "content": content, "at": str(turn.get("at") or "")})
            if clean_turns:
                user["history"][str(gid)] = clean_turns[-MEMORY_HISTORY_TURNS * 2:] if MEMORY_HISTORY_TURNS else []
    return user


def _load():
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    users = data.get("users")
    if not isinstance(users, dict):
        users = {}
    return {"version": 1, "users": users}


def _save(data):
    try:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = MEMORY_PATH.with_name(MEMORY_PATH.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, MEMORY_PATH)
    except OSError:
        pass


def _get_user(data, uid):
    users = data["users"]
    user = _normalize_user(users.get(uid), uid)
    users[uid] = user
    return user


def _evict(data):
    users = data["users"]
    if len(users) <= MEMORY_MAX_USERS:
        return
    ordered = sorted(users.items(), key=lambda kv: str((kv[1] or {}).get("last_seen") or ""))
    for uid, _ in ordered[: len(users) - MEMORY_MAX_USERS]:
        users.pop(uid, None)


# ---------------------------------------------------------------- 写入记忆

def _add_label(bucket, value):
    value = _DROP_PREFIX_RE.sub("", _clean(value)).strip()
    if len(value) < 2:
        return
    deduped = [item for item in bucket if item != value and value not in item]
    deduped.append(value)
    bucket[:] = deduped[-MAX_NOTES:]


def _detect_topics(text):
    hits = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            hits.append(topic)
    return hits


def _extract_facts(text, user):
    for match in DISLIKE_RE.finditer(text):
        _add_label(user["dislikes"], match.group(1) or match.group(2))
    for match in LIKE_RE.finditer(text):
        _add_label(user["likes"], match.group(1))
    for pattern in IDENTITY_RES:
        for match in pattern.finditer(text):
            _add_label(user["identities"], match.group(1))
    for match in NOTE_RE.finditer(text):
        _add_label(user["notes"], match.group(1))
    for key in ("likes", "dislikes"):
        user[key] = [item for item in user[key] if item not in user["identities"]]


def _update_tone(text, tone):
    tone["samples"] += 1
    tone["total_len"] += len(text)
    if EMOJI_RE.search(text):
        tone["emoji"] += 1
    if LAUGH_RE.search(text):
        tone["laugh"] += 1
    if CUTE_RE.search(text):
        tone["cute"] += 1
    if QUESTION_RE.search(text):
        tone["question"] += 1
    if EXCLAIM_RE.search(text):
        tone["exclaim"] += 1
    if len(text) >= 30:
        tone["long"] += 1


def _append_turn(user, gid, role, content):
    if MEMORY_HISTORY_TURNS <= 0 or not gid:
        return
    history = user["history"].setdefault(gid, [])
    history.append({
        "role": role,
        "content": _truncate(content, 200 if role == "user" else 400),
        "at": _now().isoformat(),
    })
    limit = MEMORY_HISTORY_TURNS * 2
    if len(history) > limit:
        del history[:-limit]


def identity_from_event(event):
    """从 OneBot 事件里取出「怎么称呼他」。群名片优先，其次昵称。"""
    sender = (event or {}).get("sender")
    if not isinstance(sender, dict):
        sender = {}
    return _clean(sender.get("card") or sender.get("nickname"))[:32]


def remember_message(user_id, group_id, text, nickname="", command=""):
    """记下一条群友发言，并更新偏好 / 身份 / 语气 / 活跃时段。"""
    if not MEMORY_ENABLED:
        return
    uid = str(user_id or "").strip()
    text = _clean(text)
    if not uid or not text:
        return

    now = _now()
    gid = str(group_id or "")
    with _LOCK:
        data = _load()
        user = _get_user(data, uid)
        if nickname:
            user["nickname"] = nickname
        if gid and gid not in user["group_ids"]:
            user["group_ids"] = (user["group_ids"] + [gid])[-10:]
        if not user["first_seen"]:
            user["first_seen"] = now.isoformat()
        user["last_seen"] = now.isoformat()
        user["message_count"] += 1

        hour = str(now.hour)
        user["active_hours"][hour] = _int(user["active_hours"].get(hour)) + 1

        if command:
            user["command_counts"][command] = _int(user["command_counts"].get(command)) + 1
            topic = COMMAND_TOPIC.get(command)
            if topic:
                user["topics"][topic] = _int(user["topics"].get(topic)) + 1

        for topic in _detect_topics(text):
            user["topics"][topic] = _int(user["topics"].get(topic)) + 1

        _extract_facts(text, user)
        _update_tone(text, user["tone"])
        _append_turn(user, gid, "user", text)

        _evict(data)
        _save(data)


def remember_reply(user_id, group_id, text):
    """记下星芒自己回过的内容，供同一用户的多轮对话使用。"""
    if not MEMORY_ENABLED:
        return
    uid = str(user_id or "").strip()
    text = _clean(text)
    if not uid or not text:
        return
    with _LOCK:
        data = _load()
        users = data["users"]
        if uid not in users:
            return
        user = _get_user(data, uid)
        user["last_seen"] = _now().isoformat()
        _append_turn(user, str(group_id or ""), "assistant", text)
        _save(data)


def forget_user(user_id):
    """清空某位用户的全部记忆。返回是否真的删掉了东西。"""
    uid = str(user_id or "").strip()
    if not uid:
        return False
    with _LOCK:
        data = _load()
        removed = data["users"].pop(uid, None) is not None
        if removed:
            _save(data)
        return removed


# ---------------------------------------------------------------- 读取记忆

def get_profile(user_id):
    """取一份用户画像快照（字典），没有记忆时返回 None。"""
    uid = str(user_id or "").strip()
    if not MEMORY_ENABLED or not uid:
        return None
    with _LOCK:
        users = _load()["users"]
        if uid not in users:
            return None
        return _normalize_user(users.get(uid), uid)


def recent_turns(user_id, group_id, limit=None):
    """最近几轮对话，返回 [{"role", "content"}, ...]。"""
    profile = get_profile(user_id)
    if not profile:
        return []
    turns = list((profile.get("history") or {}).get(str(group_id or "")) or [])
    if limit is not None and limit >= 0:
        turns = turns[-limit:]
    return [{"role": t["role"], "content": t["content"]} for t in turns]


def _top_labels(mapping, limit=MAX_LABELS):
    items = [(k, _int(v)) for k, v in (mapping or {}).items() if _int(v) > 0]
    items.sort(key=lambda kv: (-kv[1], kv[0]))
    return items[:limit]


def _avg(tone, key, samples):
    return tone[key] / samples if samples else 0.0


def _peak_hour(profile):
    hours = _top_labels(profile.get("active_hours"), 1)
    if not hours or hours[0][1] < MEMORY_MIN_SAMPLES:
        return ""
    return f"{int(hours[0][0]):02d} 点前后最常出现"


def style_hint(profile):
    """把语气习惯翻译成一句给模型看的行为指令。样本太少时不表态。"""
    if not profile:
        return ""
    tone = profile.get("tone") or {}
    samples = _int(tone.get("samples"))
    if samples < MEMORY_MIN_SAMPLES:
        return ""

    hints = []
    avg_len = _avg(tone, "total_len", samples)
    if avg_len <= 10:
        hints.append("他习惯短句，回答压在两三句内，先给结论")
    elif avg_len >= 30:
        hints.append("他能看长一点的回答，可以多讲些细节")

    emoji_rate = _avg(tone, "emoji", samples)
    if emoji_rate >= 0.4:
        hints.append("他爱用 emoji，可以放开一点")
    elif emoji_rate <= 0.05:
        hints.append("他几乎不用 emoji，回答收着点，别堆表情")

    if _avg(tone, "laugh", samples) >= 0.3:
        hints.append("他爱开玩笑，可以接梗、别太正经")
    if _avg(tone, "cute", samples) >= 0.3:
        hints.append("他语气软，可以用可爱一点的语气词")
    if _avg(tone, "question", samples) >= 0.5:
        hints.append("他常提问，先说结论再补解释")
    return "；".join(hints)


def tone_labels(profile):
    """给 /我的画像 用的人类可读语气标签。"""
    if not profile:
        return []
    tone = profile.get("tone") or {}
    samples = _int(tone.get("samples"))
    if samples < MEMORY_MIN_SAMPLES:
        return []
    labels = []
    avg_len = _avg(tone, "total_len", samples)
    labels.append("短句为主" if avg_len <= 10 else "喜欢长句" if avg_len >= 30 else "句子长度适中")
    if _avg(tone, "emoji", samples) >= 0.4:
        labels.append("爱用 emoji")
    if _avg(tone, "laugh", samples) >= 0.3:
        labels.append("爱开玩笑")
    if _avg(tone, "cute", samples) >= 0.3:
        labels.append("语气软软的")
    if _avg(tone, "question", samples) >= 0.5:
        labels.append("问题很多")
    peak = _peak_hour(profile)
    if peak:
        labels.append(peak)
    return labels


def interest_score(profile, text):
    """画像与一段文字的匹配度，用于个性化挑内容。无信号时返回 0。"""
    if not profile:
        return 0.0
    text = str(text or "")
    if not text:
        return 0.0
    score = 0.0
    for topic, weight in (profile.get("topics") or {}).items():
        keywords = TOPIC_KEYWORDS.get(topic)
        if keywords and any(keyword in text for keyword in keywords):
            score += min(_int(weight), 5)
    for like in profile.get("likes") or []:
        if like and like in text:
            score += 3.0
    for dislike in profile.get("dislikes") or []:
        if dislike and dislike in text:
            score -= 6.0
    return score


def build_prompt_context(user_id, group_id):
    """给 DeepSeek 的「记忆补丁」：返回 (system_extra, turns)。"""
    if not MEMORY_ENABLED:
        return "", []
    profile = get_profile(user_id)
    if not profile:
        return "", []

    lines = []
    traits = []
    if profile.get("nickname"):
        traits.append(f"称呼：{profile['nickname']}")
    if profile.get("first_seen"):
        since = str(profile["first_seen"])[:10]
        traits.append(f"从 {since} 认识，共聊过 {profile['message_count']} 次")
    if traits:
        lines.append("· " + "；".join(traits))

    topics = _top_labels(profile.get("topics"), 3)
    if topics:
        lines.append("· 常聊话题：" + "、".join(f"{name}({count})" for name, count in topics))
    commands = _top_labels(profile.get("command_counts"), 3)
    if commands:
        lines.append("· 常用指令：" + "、".join(name for name, _ in commands))
    if profile.get("identities"):
        lines.append("· 他自我介绍：" + "、".join(profile["identities"]))
    if profile.get("likes"):
        lines.append("· 他说过喜欢：" + "、".join(profile["likes"]))
    if profile.get("dislikes"):
        lines.append("· 他说过不喜欢：" + "、".join(profile["dislikes"]))
    if profile.get("notes"):
        lines.append("· 他让你记住：" + "、".join(profile["notes"]))
    tone = tone_labels(profile)
    if tone:
        lines.append("· 语气习惯：" + "、".join(tone))

    if not lines:
        return "", []

    hint = style_hint(profile)
    block = ["【关于这位群友的长期记忆】", *lines]
    if hint:
        block.append(f"【表达方式】{hint}。")
    block.append(
        "【使用要求】自然地用这些信息把回答调得更贴合他，但不要复述这份记忆，"
        "也不要说「根据我的记录」之类的话。信息不确定时宁可不提。"
    )
    return "\n".join(block), recent_turns(user_id, group_id)


def profile_text(user_id):
    """「/我的画像」的回复。"""
    profile = get_profile(user_id)
    if not profile or not profile.get("message_count"):
        return ("🛰️【星芒记忆卡】\n"
                "星芒还没攒到关于你的记忆～\n"
                "多来碰几次爪、聊几句，我就会慢慢记住你的喜好啦 ✨")

    lines = ["🧠【星芒记忆卡】", ""]
    if profile.get("nickname"):
        lines.append(f"👤 称呼：{profile['nickname']}")
    if profile.get("first_seen"):
        lines.append(f"📅 认识：{str(profile['first_seen'])[:10]} 起，一共聊了 {profile['message_count']} 次")
    topics = _top_labels(profile.get("topics"), 4)
    if topics:
        lines.append("🗂️ 常聊话题：" + "、".join(f"{name} {count} 次" for name, count in topics))
    commands = _top_labels(profile.get("command_counts"), 4)
    if commands:
        lines.append("⌨️ 常用指令：" + "、".join(name for name, _ in commands))
    if profile.get("identities"):
        lines.append("🪪 你自我介绍过：" + "、".join(profile["identities"]))
    if profile.get("likes"):
        lines.append("💚 你说过喜欢：" + "、".join(profile["likes"]))
    if profile.get("dislikes"):
        lines.append("🚫 你说过不喜欢：" + "、".join(profile["dislikes"]))
    if profile.get("notes"):
        lines.append("📌 你让我记住：" + "、".join(profile["notes"]))
    tone = tone_labels(profile)
    if tone:
        lines.append("🗣️ 语气画像：" + "、".join(tone))

    turns = recent_turns(user_id, (profile.get("group_ids") or [""])[-1], 3)
    asked = [t["content"] for t in turns if t["role"] == "user"][-3:]
    if asked:
        lines.append("💬 最近聊过：" + "；".join(asked))

    lines += ["", "📡 发送 /忘记我 可以清空这些记忆 ✨"]
    return "\n".join(lines)


def forget_text(user_id):
    """「/忘记我」的回复。"""
    removed = forget_user(user_id)
    if removed:
        return ("🧹【记忆已清空】\n"
                "星芒把关于你的画像和聊天记录都删掉啦，触角已经归零 🛸\n"
                "下次再聊，我们就重新认识一次 ✨")
    return ("🛰️【本来就没有记忆】\n"
            "星芒的档案里没有你的记录，放心 ✨")


def stats_text():
    """管理员用的「/记忆概况」。"""
    with _LOCK:
        users = [_normalize_user(u, uid) for uid, u in _load()["users"].items()]
    if not users:
        return "🧠【星芒记忆概况】\n还没有任何用户画像 ✨"
    total_messages = sum(u["message_count"] for u in users)
    topics = {}
    for user in users:
        for name, count in user["topics"].items():
            topics[name] = topics.get(name, 0) + count
    ranked = sorted(topics.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    lines = [
        "🧠【星芒记忆概况】",
        f"已记住 {len(users)} 位群友，累计 {total_messages} 条发言",
    ]
    if ranked:
        lines.append("话题 Top：" + "、".join(f"{name} {count}" for name, count in ranked))
    active = sorted(users, key=lambda u: u["last_seen"], reverse=True)[:5]
    if active:
        lines.append("")
        lines.append("最近活跃：")
        for user in active:
            label = user["nickname"] or user["user_id"]
            lines.append(f"· {label}（{user['message_count']} 次）")
    return "\n".join(lines)
