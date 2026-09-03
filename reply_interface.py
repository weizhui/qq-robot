import hashlib
import json
import random
import re
import shutil
import threading
import time
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
BASE_DIR = Path(__file__).resolve().parent
CHARACTER_IMAGE_DIR = BASE_DIR / "Character_Image"
CACHE_DIR = BASE_DIR / "runtime_cache"
DAILY_STATE_PATH = CACHE_DIR / "daily_state.json"
DAILY_LIMIT = 100
AI_DAILY_LIMIT = 100
COOLDOWN_SECONDS = 5
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "").strip()
JIKAN_API_BASE = os.getenv("JIKAN_API_BASE", "").strip().rstrip("/")
ANILIST_API_URL = os.getenv("ANILIST_API_URL", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
MAX_DAILY_IMAGE_BYTES = 8 * 1024 * 1024
_LOCK = threading.Lock()
_LAST_COMMAND_AT = {}

BOOKS = [
    ("《神经漫游者》", "威廉·吉布森", "赛博朋克开山之作，霓虹、黑客、意识网络一起闪烁 ⚡"),
    ("《三体》", "刘慈欣", "文明、宇宙和黑暗森林，一口气把尺度拉到恒星级 🌌"),
    ("《沙丘》", "弗兰克·赫伯特", "沙海、香料、预言与权谋，史诗感直接拉满 🪐"),
    ("《仿生人会梦见电子羊吗？》", "菲利普·迪克", "复制人与人类边界雾蒙蒙，适合深夜发呆 🤖"),
    ("《基地》", "艾萨克·阿西莫夫", "用心理史学给银河帝国打一针未来疫苗 📡"),
    ("《你一生的故事》", "特德·姜", "语言、时间和选择，温柔但锋利 ✨"),
]

MOVIES = [
    ("《银翼杀手2049》", "雨、霓虹、复制人，以及一个关于灵魂的问题 🌧️"),
    ("《降临》", "语言不是工具，是看见时间的另一种眼睛 🛸"),
    ("《星际穿越》", "爱、引力、黑洞，和一块非常忙的手表 🕳️"),
    ("《攻壳机动队》", "电子幽灵在壳里低声发问：我是谁？🤖"),
    ("《火星救援》", "用土豆、数学和乐观主义活下去 🥔"),
    ("《2001太空漫游》", "人类、黑石碑和沉默宇宙的凝视 🌑"),
]

FACTS = [
    "旅行者1号携带金唱片，记录了地球的声音、图像和问候。来源：NASA Voyager Golden Record 🛰️",
    "国际空间站约每90分钟绕地球一圈，一天能看见很多次日出。来源：NASA ISS 🌍",
    "詹姆斯·韦布空间望远镜主要在红外波段观测，适合看穿宇宙尘埃。来源：NASA JWST 🔭",
    "火星奥林帕斯山是太阳系最高的火山之一，高度约为珠穆朗玛峰的三倍。来源：NASA Mars 🪐",
    "戴森球是弗里曼·戴森提出的恒星能量采集设想，经常出现在科幻作品中。来源：Dyson 1960 ☀️",
]

LUCKY_WORDS = ["曲率驱动", "量子泡沫", "深空回声", "仿生梦", "星门", "离子风", "银河尘埃", "触角投影"]
GOOD_ACTIONS = ["写稿", "幻想", "喝能量汽水", "整理书单", "开新坑", "看星星", "做实验"]
BAD_ACTIONS = ["硬刚ddl", "说这不科学", "忘记存档", "空腹跃迁", "深夜改配置", "和黑洞讲道理"]

FORTUNES = [
    ("上上签·星际跃迁", "跃迁引擎已预热，目标星辰大海。", "适合开启新计划，别怕迷航 🚀"),
    ("上签·月面漫步", "脚印会留在月尘里，心跳会留在今天。", "稳步推进，别被噪声打断 🌙"),
    ("下签·信号延迟", "来自未来的回信还在路上。", "先检查坐标，再启动引擎 📡"),
    ("下下签·黑洞擦肩", "警告：事件视界附近不宜头铁。", "今天适合保守操作，多喝水，少冒险 🕳️"),
]

ANIME_RECOMMENDATIONS = [
    {
        "mal_id": 5114,
        "title": "《钢之炼金术师 FULLMETAL ALCHEMIST》",
        "tags": "奇幻 / 冒险 / 成长",
        "intro": "两兄弟为了找回失去的身体踏上旅程。它把热血、亲情、战争代价和等价交换讲得很完整，适合想看高完成度长篇的人。",
        "watch_hint": "适合从第 1 集开始顺序看，节奏稳定，主线回收很强。",
    },
    {
        "mal_id": 9253,
        "title": "《命运石之门》",
        "tags": "科幻 / 时间旅行 / 悬疑",
        "intro": "秋叶原的小发明社团意外触碰时间线。前期铺垫偏生活，后半段会把伏笔和情绪一起收紧。",
        "watch_hint": "前几集慢热，建议至少看到关键转折后再判断。",
    },
    {
        "mal_id": 32281,
        "title": "《你的名字。》",
        "tags": "青春 / 奇幻 / 恋爱",
        "intro": "两个陌生少年少女在梦中交换身体，故事从日常错位一路走向灾难与重逢。画面、音乐和情绪推进都很适合轻松观影。",
        "watch_hint": "电影体量，一晚就能看完。",
    },
    {
        "mal_id": 33352,
        "title": "《紫罗兰永恒花园》",
        "tags": "治愈 / 战后 / 书信",
        "intro": "少女在替人写信的工作中学习理解情感。每一集像一封慢慢展开的信，画面精致，情绪细腻。",
        "watch_hint": "适合安静时看，建议准备纸巾。",
    },
    {
        "mal_id": 52991,
        "title": "《葬送的芙莉莲》",
        "tags": "奇幻 / 旅途 / 时间",
        "intro": "勇者故事结束后，长寿精灵重新理解同行、离别和人类短暂的一生。它不急着燃，而是把余韵铺得很准。",
        "watch_hint": "适合喜欢慢节奏奇幻和人物关系的人。",
    },
    {
        "mal_id": 1,
        "title": "《星际牛仔》",
        "tags": "科幻 / 公路片 / 爵士",
        "intro": "赏金猎人们在太阳系各处接活、流浪、逃避过去。单元剧气质浓，音乐和氛围非常突出。",
        "watch_hint": "适合一集一集慢慢看，像翻旧唱片。",
    },
]

VISUAL_POOLS = {
    "star": [
        {
            "title": "蟹状星云",
            "url": "",
            "source": "NASA / ESA / Wikimedia Commons",
            "source_url": "",
            "caption": "一千年前爆发的恒星，把自己炸成了发光的宇宙蛛网；中心那颗中子星还在高速旋转，像一座深空灯塔。"
        },
        {
            "title": "创生之柱",
            "url": "",
            "source": "NASA / ESA / Hubble / Wikimedia Commons",
            "source_url": "",
            "caption": "鹰状星云里的尘埃巨柱正在孕育新恒星，像宇宙把小星星藏进了雾气城堡。"
        },
        {
            "title": "哈勃超深场",
            "url": "",
            "source": "NASA / ESA / Wikimedia Commons",
            "source_url": "",
            "caption": "看似很小的一片黑暗天空里，藏着成千上万座星系；星云宝宝的全息眼差点数到打嗝。"
        },
        {
            "title": "土星春分",
            "url": "",
            "source": "NASA / JPL / Space Science Institute / Wikimedia Commons",
            "source_url": "",
            "caption": "卡西尼号拍下土星春分时的环影，薄薄一圈像宇宙给行星戴上的银色耳机。"
        },
        {
            "title": "猫眼星云",
            "url": "",
            "source": "NASA / ESA / HEIC / Wikimedia Commons",
            "source_url": "",
            "caption": "恒星生命末期吐出的层层气壳，像深空里睁开的一只蓝绿色电子眼。"
        }
    ],
    "wallpaper": [
        {
            "title": "哈勃超深场壁纸",
            "url": "",
            "source": "NASA / ESA / Wikimedia Commons",
            "source_url": "",
            "caption": "把屏幕交给几千座星系，桌面立刻变成深空舷窗。"
        },
        {
            "title": "土星环壁纸",
            "url": "",
            "source": "NASA / JPL / Space Science Institute / Wikimedia Commons",
            "source_url": "",
            "caption": "银色星环挂在屏幕上，适合搭配能量汽水和低音电子乐。"
        },
        {
            "title": "地出壁纸",
            "url": "",
            "source": "NASA / Wikimedia Commons",
            "source_url": "",
            "caption": "月面上升起的蓝色地球，像宇宙发来的一枚温柔坐标。"
        }
    ],
    "poster": [
        {
            "title": "星际茶话会",
            "url": "",
            "source": "NASA / Wikimedia Commons",
            "source_url": "",
            "caption": "把地球当背景，把幻想倒进杯子里，星际茶话会开始啦。"
        },
        {
            "title": "深空读书会",
            "url": "",
            "source": "NASA / ESA / Wikimedia Commons",
            "source_url": "",
            "caption": "今天的书页背后，是一整片会发光的宇宙。"
        },
        {
            "title": "星环幻想夜",
            "url": "",
            "source": "NASA / JPL / Space Science Institute / Wikimedia Commons",
            "source_url": "",
            "caption": "土星把环影铺成舞台，今晚适合把脑洞开到最大。"
        }
    ],
}

def today_key():
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")


def stable_index(name, modulo):
    digest = hashlib.sha256(f"{today_key()}:{name}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulo


def clean_message(message):
    return re.sub(r"\s+", " ", (message or "")).strip()


def command_text(message):
    msg = clean_message(message)
    if msg.startswith("/"):
        return msg[1:].strip()
    return msg


def cq_image(value):
    if isinstance(value, Path):
        return f"[CQ:image,file=file://{value}]"
    return f"[CQ:image,file={value}]"


def parse_character_image(path):
    name = path.stem
    match = re.match(r"星云(\d+)_(.+)$", name)
    if not match:
        return {"number": "?", "label": name}
    return {"number": int(match.group(1)), "label": match.group(2)}


def pick_today_character():
    target_number = stable_index("today-nebula", 141) + 1
    matches = sorted(CHARACTER_IMAGE_DIR.glob(f"星云{target_number}_*.png"))
    if not matches:
        all_images = sorted(CHARACTER_IMAGE_DIR.glob("星云*_*.png"))
        if not all_images:
            return {"number": target_number, "label": "未知信号", "path": "", "missing": True}
        match = all_images[stable_index("today-nebula-fallback", len(all_images))]
    else:
        match = matches[0]
    parsed = parse_character_image(match)
    return {"number": parsed["number"], "label": parsed["label"], "path": str(match), "missing": False}


def limited_image_url(url, width=1400):
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key.lower() != "width"]
    query.append(("width", str(width)))
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))


def download_daily_image(kind, item, date_dir):
    suffix = Path(urllib.parse.urlsplit(item["url"]).path).suffix or ".jpg"
    target = date_dir / f"{kind}{suffix}"
    widths = (1400, 1100, 900) if "wikimedia.org" in item["url"] else (1400,)
    for width in widths:
        image_url = limited_image_url(item["url"], width)
        request = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0 qq-bot"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
            if len(data) < 2048 or len(data) > MAX_DAILY_IMAGE_BYTES:
                continue
            target.write_bytes(data)
            return str(target)
        except Exception:
            continue
    return ""


def repair_visual_cache(state):
    date_dir = CACHE_DIR / "images" / today_key()
    date_dir.mkdir(parents=True, exist_ok=True)
    changed = False
    visuals = state.get("visuals") or {}
    for kind, item in visuals.items():
        local_path = item.get("local_path")
        needs_download = not local_path
        if local_path:
            path = Path(local_path)
            needs_download = not path.exists() or path.stat().st_size > MAX_DAILY_IMAGE_BYTES
        if needs_download:
            item["local_path"] = download_daily_image(kind, item, date_dir)
            changed = True
    return changed


def cleanup_old_cache(current_date):
    image_root = CACHE_DIR / "images"
    if not image_root.exists():
        return
    for child in image_root.iterdir():
        if child.is_dir() and child.name != current_date:
            shutil.rmtree(child, ignore_errors=True)


def build_daily_state():
    date = today_key()
    date_dir = CACHE_DIR / "images" / date
    date_dir.mkdir(parents=True, exist_ok=True)
    cleanup_old_cache(date)

    visuals = {}
    for kind, pool in VISUAL_POOLS.items():
        item = dict(pool[stable_index(kind, len(pool))])
        item["local_path"] = download_daily_image(kind, item, date_dir)
        visuals[kind] = item

    return {
        "date": date,
        "command_count": 0,
        "ai_question_count": 0,
        "today_nebula": pick_today_character(),
        "visuals": visuals,
    }


def load_state_unlocked():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if DAILY_STATE_PATH.exists():
        try:
            state = json.loads(DAILY_STATE_PATH.read_text(encoding="utf-8"))
            if state.get("date") == today_key():
                if repair_visual_cache(state):
                    save_state_unlocked(state)
                return state
        except (json.JSONDecodeError, OSError):
            pass
    state = build_daily_state()
    save_state_unlocked(state)
    return state


def save_state_unlocked(state):
    DAILY_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_daily_state():
    with _LOCK:
        return load_state_unlocked()


def daily_cache_worker():
    while True:
        time.sleep(60)
        try:
            ensure_daily_state()
        except Exception:
            pass


def start_daily_cache_worker():
    thread = threading.Thread(target=daily_cache_worker, name="daily-cache-worker", daemon=True)
    thread.start()


def quota_guard(event):
    user_id = str(event.get("user_id", "unknown"))
    now = time.time()
    last = _LAST_COMMAND_AT.get(user_id, 0)
    if now - last < COOLDOWN_SECONDS:
        return "🛰️ 星云宝宝的触角还在冷却中……\n⏳ 请等 5 秒再呼叫我，能量汽水正在冒泡泡！🥤✨"
    _LAST_COMMAND_AT[user_id] = now

    with _LOCK:
        state = load_state_unlocked()
        if int(state.get("command_count", 0)) >= DAILY_LIMIT:
            return "🌙 星云宝宝今天已经回复 100 条指令啦！\n🛸 触角有点累，要钻进小小休眠舱补充能量汽水。\n✨ 北京时间零点刷新后，我们明天再继续聊天呀！"
        state["command_count"] = int(state.get("command_count", 0)) + 1
        save_state_unlocked(state)
    return None


def ai_quota_guard():
    with _LOCK:
        state = load_state_unlocked()
        if int(state.get("ai_question_count", 0)) >= AI_DAILY_LIMIT:
            return "🌙【提问额度用完啦】\n星云宝宝今天已经认真思考 100 次啦，触角热热的，要抱着能量汽水休息一下 🥤✨\n北京时间零点刷新后再来问我吧！🛸"
        state["ai_question_count"] = int(state.get("ai_question_count", 0)) + 1
        save_state_unlocked(state)
    return None


def build_ai_task(question, event):
    blocked = ai_quota_guard()
    if blocked:
        return blocked
    if not question:
        return "💭【星云提问】\n小小问号没有捕获到内容呀。\n请这样问：@星云 /提问 什么是黑洞？🛸✨"
    if len(question) > 500:
        return "📡【问题太长啦】\n星云宝宝的触角被问题绕成蝴蝶结了。\n请把 /提问 后面的内容控制在 500 字以内哦 🥺✨"
    return {
        "type": "deepseek_question",
        "question": question,
        "immediate": "💭【星云思考中】\n星云宝宝收到问题啦，正在晃晃触角、打开深空小脑袋仔细想想……🛸✨\n请稍等一下，能量汽水已经插上吸管！🥤",
    }


def fallback_ai_answer():
    return "😵‍💫【星云卡壳啦】\n这个问题有点难，星云宝宝的全息电子眼转圈圈了……\n嘿嘿 🛸✨\n\n嘿嘿 😝✨"


def clean_ai_answer(answer):
    text = answer.strip()
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"(?m)^\s*[*-]\s+", "", text)
    text = text.replace("*", "")
    return text.strip()


def call_deepseek(question):
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key or not DEEPSEEK_API_URL:
        return "🔑【DeepSeek API Key 未配置】\n星云宝宝还没有拿到深空通行证。\n请通过运行环境配置 DEEPSEEK_API_KEY 和 DEEPSEEK_API_URL。🛸"

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是星云，一个俏皮可爱、带科幻感的中文群聊机器人。回答简单问题时要准确、简洁、友好，像群里的活人一样自然说话，语气闲一点、可爱一点。每段都可以自然带一点emoji，但不要堆太多。不要使用Markdown格式，不要用星号、加粗、项目符号或标题腔。不要输出过长，尽量控制在600字以内。",
            },
            {"role": "user", "content": question},
        ],
        "stream": False,
        "max_tokens": 900,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.loads(response.read().decode("utf-8"))
    answer = data["choices"][0]["message"].get("content", "").strip()
    if not answer:
        return fallback_ai_answer()
    answer = clean_ai_answer(answer)
    return f"🤖【星云回答】\n{answer}\n\n✨ 来自 DeepSeek · 星云整理完成 🛸"


def build_ai_answer(question):
    try:
        return call_deepseek(question)
    except Exception:
        return fallback_ai_answer()


def help_text():
    return """✨【星云·赛博帮助手册】✨
来碰爪！我是星云，霓虹螺旋角，全息电子眼 🛸💫

📡 基础指令
/帮助　/签到　/碰爪　/今日星云

🌌 星图与视觉
/星图　/壁纸　/海报

📚 科幻内容
/荐书　/荐影　/动漫　/冷知识　/提问 问题

🎲 娱乐随机
/运势　/抽签

🛸 协会服务
/协会介绍　/活动　/招新　/投稿

⏳ 连续指令冷却 5 秒。
🔋 每天最多回复 100 条指令，北京时间零点刷新。"""


def checkin_text(cmd):
    if "晚安" in cmd:
        tail = "今晚适合把梦调到深空频道，晚安啦 🌙✨"
    elif "早安" in cmd:
        tail = "今日状态：适合幻想，不适合早八 ☀️📡"
    else:
        tail = random.choice([
            "今日状态：适合幻想，不适合早八 ☀️",
            "触角电量稳定，适合写下一个宇宙 📚",
            "能量汽水已补充，赛博精神 +5 🥤",
        ])
    return f"""✅【星云签到成功】
星云伸出触角，在你脑门上轻轻一点 🛸

🥤 今日能量汽水 +1
⚡ 赛博精神 +5
🌟 {tail}"""


def today_nebula(state):
    info = state["today_nebula"]
    if info.get("missing") or not info.get("path"):
        return f"⚠️【今日星云】\n触角投影启动失败：没有找到 星云{info.get('number')}_*.png 🛰️"
    path = Path(info["path"])
    return f"""{cq_image(path)}
🌟【今日星云】
编号：星云{info['number']}
身份：{info['label']} ✨
图片：由 AI 生成 🎨🤖

触角投影启动——今天的星云形态已锁定！🛸"""


def daily_visual(state, kind):
    item = state["visuals"][kind]
    image_value = Path(item["local_path"]) if item.get("local_path") else limited_image_url(item["url"], 900)
    labels = {
        "star": ("🌌【今日星图】", "触角投影启动——今天的深空坐标已点亮！🔭"),
        "wallpaper": ("🖥️【今日壁纸】", "全息电子眼扫描完成，适合设成屏幕背景！✨"),
        "poster": ("🎬【今日海报】", "科幻海报投影完成，幻想干杯！🥤"),
    }
    title, note = labels[kind]
    caption = item.get("caption", note)
    return f"""{cq_image(image_value)}
{title}
名称：{item['title']}
文案：{caption} 🛸✨
说明：{note}
来源：{item['source']}
链接：{item['source_url']}"""


def jikan_json(path):
    if not JIKAN_API_BASE:
        return {}
    request = urllib.request.Request(
        f"{JIKAN_API_BASE}{path}",
        headers={"User-Agent": "qq-bot anime recommender"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def anilist_images(title):
    query = """
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        coverImage { extraLarge large }
        bannerImage
        characters(perPage: 3) {
          nodes { image { large medium } }
        }
      }
    }
    """
    clean_title = title.strip("《》")
    payload = json.dumps({"query": query, "variables": {"search": clean_title}}, ensure_ascii=False).encode("utf-8")
    if not ANILIST_API_URL:
        return []
    request = urllib.request.Request(
        ANILIST_API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "qq-bot anime recommender"},
        method="POST",
    )
    images = []
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            media = json.loads(response.read().decode("utf-8")).get("data", {}).get("Media") or {}
        cover = media.get("coverImage") or {}
        for url in (cover.get("extraLarge"), media.get("bannerImage")):
            if url and url not in images:
                images.append(url)
        for node in ((media.get("characters") or {}).get("nodes") or []):
            image = node.get("image") or {}
            url = image.get("large") or image.get("medium")
            if url and url not in images:
                images.append(url)
            if len(images) >= 3:
                break
        if len(images) < 3:
            for url in (cover.get("large"), cover.get("medium")):
                if url and url not in images:
                    images.append(url)
                if len(images) >= 3:
                    break
    except Exception:
        pass
    return images


def anime_images(mal_id):
    images = []
    try:
        data = jikan_json(f"/anime/{mal_id}/pictures").get("data", [])
        for item in data:
            jpg = item.get("jpg") or {}
            url = jpg.get("large_image_url") or jpg.get("image_url")
            if url and url not in images:
                images.append(url)
            if len(images) >= 3:
                return images
    except Exception:
        pass

    try:
        data = jikan_json(f"/anime/{mal_id}/characters").get("data", [])
        for item in data:
            character = item.get("character") or {}
            jpg = ((character.get("images") or {}).get("jpg") or {})
            url = jpg.get("image_url")
            if url and url not in images:
                images.append(url)
            if len(images) >= 3:
                break
    except Exception:
        pass
    return images


def build_anime_recommendation():
    item = ANIME_RECOMMENDATIONS[stable_index("anime-recommendation", len(ANIME_RECOMMENDATIONS))]
    title = item["title"]
    score = "暂无评分"
    episodes = "未知"
    images = anime_images(item["mal_id"])
    if len(images) < 3:
        for url in anilist_images(item["title"]):
            if url and url not in images:
                images.append(url)
            if len(images) >= 3:
                break
    try:
        data = jikan_json(f"/anime/{item['mal_id']}/full").get("data", {})
        title = f"《{data.get('title_japanese') or data.get('title') or item['title'].strip('《》')}》"
        score = data.get("score") or score
        episodes = data.get("episodes") or episodes
        cover = ((data.get("images") or {}).get("jpg") or {}).get("large_image_url")
        trailer = ((data.get("trailer") or {}).get("images") or {}).get("maximum_image_url")
        for url in (cover, trailer):
            if url and url not in images:
                images.insert(0, url)
        if len(images) < 3:
            for url in anilist_images(title):
                if url and url not in images:
                    images.append(url)
                if len(images) >= 3:
                    break
        images = images[:3]
    except Exception:
        pass

    image_lines = "\n".join(cq_image(url) for url in images[:3])
    prefix = f"{image_lines}\n" if image_lines else ""
    return f"""{prefix}🎞️【今日动漫推荐】
片名：{title}
类型：{item['tags']}
集数：{episodes}
评分：{score}

简介：{item['intro']}

观看提示：{item['watch_hint']}
图片来源：Jikan / MyAnimeList / AniList 公开接口"""


def recommend_book():
    title, author, note = random.choice(BOOKS)
    return f"""📚【星云荐书】
从小小亚空间书柜里抽出一本书——

书名：{title}
作者：{author}
推荐：{note}
来源：来自星云推荐 🌟"""


def recommend_movie():
    title, note = random.choice(MOVIES)
    return f"""🎬【星云荐影】
全息电子眼开始闪烁——

影片：{title}
看点：{note}
来源：来自星云推荐 🌟"""


def cyber_luck():
    score = random.randint(1, 100)
    bars = round(score / 12.5)
    meter = "▓" * bars + "░" * (8 - bars)
    good = "、".join(random.sample(GOOD_ACTIONS, 3))
    bad = random.choice(BAD_ACTIONS)
    lucky = random.choice(LUCKY_WORDS)
    return f"""🔮【今日赛博运势】
能量指数：{meter} {score}%

✅ 宜：{good}
⚠️ 忌：{bad}
🍀 幸运词：{lucky}

嗝——赛博能量满格！🥤✨"""


def draw_lot():
    name, poem, explain = random.choice(FORTUNES)
    return f"""🎴【星云抽签】
签位：{name}

签文：{poem}
解签：{explain}

这不科学，但很科幻 ✨"""


def unknown_text():
    return """🛰️【未知信号】
全息电子眼眨了眨，没解析出这条指令。

可以试试：
/帮助　/星图　/荐书　/运势　/提问 问题

记得在 @星云 后面加 / 指令哦 ✨"""


def build_reply(message, event, bot_qq, group_id):
    limited = quota_guard(event)
    if limited:
        return limited

    state = ensure_daily_state()
    msg = clean_message(message)
    cmd = command_text(msg)
    lowered = cmd.lower()

    if cmd.startswith("提问"):
        question = cmd[len("提问"):].strip()
        return build_ai_task(question, event)
    if not cmd or any(word in cmd for word in ["帮助", "菜单", "功能"]):
        return help_text()
    if any(word in cmd for word in ["签到", "早安", "晚安"]):
        return checkin_text(cmd)
    if "今日星云" in cmd:
        return today_nebula(state)
    if "碰爪" in cmd:
        return "🤝【碰爪成功】\n碰爪！星际协议达成。\n你已接入星云触角网络，欢迎随时呼叫 🛸✨"
    if any(word in cmd for word in ["星图", "深空", "星云图"]):
        return daily_visual(state, "star")
    if "壁纸" in cmd or "科幻壁纸" in cmd:
        return daily_visual(state, "wallpaper")
    if "海报" in cmd or "科幻海报" in cmd:
        return daily_visual(state, "poster")
    if "荐书" in cmd or "推荐小说" in cmd:
        return recommend_book()
    if "荐影" in cmd or "推荐电影" in cmd:
        return recommend_movie()
    if any(word in cmd for word in ["动漫", "今日动漫", "动漫推荐", "推荐动漫"]):
        return build_anime_recommendation()
    if "冷知识" in cmd:
        return f"🧠【科幻冷知识】\n{random.choice(FACTS)}\n\n星云触角已帮你记下啦 ✨"
    if "运势" in cmd or "占卜" in cmd:
        return cyber_luck()
    if "抽签" in cmd:
        return draw_lot()
    if "协会介绍" in cmd or "星云科幻协会" in cmd:
        return """🛸【星云科幻协会】
中国石油大学（北京）星云科幻协会。

这里聚集了一群爱科幻、爱幻想、爱星辰的人。
读书会、观影夜、科幻创作、星图观测，都在星云触角覆盖范围内。

来碰爪，一起遨游科幻宇宙 ✨"""
    if "活动" in cmd or "最近活动" in cmd:
        return "📅【最近活动】\n最近活动占位信息，可由管理员更新。\n\n星云的小日程本已经摊开啦 🛸✨"
    if "招新" in cmd or "入会" in cmd:
        return """🌟【星云招新】
星云科幻协会招新中！

如果你也相信幻想的力量，欢迎加入。
星云会用触角给你留一个位置 🛸💫"""
    if "投稿" in cmd or "写手" in cmd:
        return "📝【投稿方式】\n返回投稿方式。\n\n星云已经准备好小小收稿箱啦 ✨"
    if "42" in cmd:
        return "✨【暗号确认】\n宇宙的终极答案。但问题是什么？🛸"
    if "银河系漫游指南" in cmd:
        return "📘【暗号确认】\n毛巾已备好，别慌。✨"
    if "能量汽水" in cmd:
        return "🥤【能量补给】\n嗝——已补充赛博能量，电力满格！⚡"
    if "这不科学" in cmd:
        return "🧪【星云吐槽】\n但很科幻。✨"
    if "星云是谁" in cmd:
        return "🌟【星云自我介绍】\n我是星云，霓虹螺旋角，全息电子眼，来自赛博星系。\n爱喝能量汽水打嗝，信奉赛博精神 🥤🛸"

    return unknown_text()


ensure_daily_state()
start_daily_cache_worker()
