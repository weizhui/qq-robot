import hashlib
import json
import logging
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

import memory_store


logger = logging.getLogger("qq-bot.reply")

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
BASE_DIR = Path(__file__).resolve().parent
# 图片目录：默认取项目上一级目录下的 Character_Image（可用环境变量覆盖）
CHARACTER_IMAGE_DIR = Path(
    os.getenv("CHARACTER_IMAGE_DIR", str(BASE_DIR.parent / "Character_Image"))
)
CACHE_DIR = BASE_DIR / "runtime_cache"
DAILY_STATE_PATH = CACHE_DIR / "daily_state.json"
DAILY_LIMIT = 100
AI_DAILY_LIMIT = 100
COOLDOWN_SECONDS = 1
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
    ("《黑暗森林》", "刘慈欣", "面壁者、破壁人与宇宙社会学，冷得让人后背发凉 🧊"),
    ("《球状闪电》", "刘慈欣", "把宏电子写成诗，也写成一场漫长的执念 ⚡"),
    ("《流浪地球》", "刘慈欣", "带着地球去流浪，人类把家背在身上 🪐"),
    ("《沙丘》", "弗兰克·赫伯特", "沙海、香料、预言与权谋，史诗感直接拉满 🪐"),
    ("《沙丘之子》", "弗兰克·赫伯特", "预知的诅咒：看得见未来的人，最难活在当下 🔮"),
    ("《基地》", "艾萨克·阿西莫夫", "用心理史学给银河帝国打一针未来疫苗 📡"),
    ("《神们自己》", "艾萨克·阿西莫夫", "平行宇宙的能量交换，代价藏在最温柔的地方 ⚛️"),
    ("《海伯利安》", "丹·西蒙斯", "七位朝圣者讲七个故事，把科幻写成一部未来版《坎特伯雷故事集》 🕯️"),
    ("《安德的游戏》", "奥森·斯科特·卡德", "天才少年被训练成指挥官，胜利的代价却没人告诉他 🎮"),
    ("《深渊上的火》", "弗诺·文奇", "太空歌剧的巅峰，爪族、共生体与星际文明群像 🌠"),
    ("《天渊》", "弗诺·文奇", "在深渊之下，贸易、阴谋与漫长的时间一起发酵 ⏳"),
    ("《索拉里斯星》", "斯坦尼斯瓦夫·莱姆", "一颗有思想的海洋行星，照出人类的自以为是 🌊"),
    ("《机器人大师》", "斯坦尼斯瓦夫·莱姆", "两个机器人工程师，把造物写成荒诞又聪明的寓言 🤖"),
    ("《雪崩》", "尼尔·斯蒂芬森", "元宇宙的老祖宗，赛博空间的霓虹与病毒 🕶️"),
    ("《环形世界》", "拉里·尼文", "一亿英里宽的巨环，冒险与硬核设定的双重狂欢 🎡"),
    ("《你一生的故事》", "特德·姜", "语言、时间和选择，温柔但锋利 ✨"),
    ("《呼吸》", "特德·姜", "九篇短篇，把物理与哲学揉成安静又惊人的火花 🌬️"),
    ("《仿生人会梦见电子羊吗？》", "菲利普·迪克", "复制人与人类边界雾蒙蒙，适合深夜发呆 🤖"),
]

MOVIES = [
    ("《银翼杀手2049》", "雨、霓虹、复制人，以及一个关于灵魂的问题 🌧️"),
    ("《银翼杀手》", "1982 年的未来，雨夜与眼泪，赛博朋克的原点 🌃"),
    ("《降临》", "语言不是工具，是看见时间的另一种眼睛 🛸"),
    ("《星际穿越》", "爱、引力、黑洞，和一块非常忙的手表 🕳️"),
    ("《盗梦空间》", "梦里套梦，陀螺最后到底停没停？🌀"),
    ("《黑客帝国》", "红药丸还是蓝药丸，这是个问题 🟥"),
    ("《攻壳机动队》", "电子幽灵在壳里低声发问：我是谁？🤖"),
    ("《火星救援》", "用土豆、数学和乐观主义活下去 🥔"),
    ("《2001太空漫游》", "人类、黑石碑和沉默宇宙的凝视 🌑"),
    ("《终结者2》", "液态金属、公路追逐，和一台学会爱的机器 🏍️"),
    ("《异形》", "太空里没人听得见你尖叫 👽"),
    ("《千钧一发》", "基因决定命运的世界里，一个“不合格”的人偏要上天 🧬"),
    ("《月球》", "一个人、一个克隆、一段被压缩的孤独 🌕"),
    ("《机械姬》", "图灵测试的另一头，谁在被测试？🔬"),
    ("《超时空接触》", "科学、信仰与那束来自织女星的信号 📻"),
    ("《十二猴子》", "时间旅行是解药，还是因果的圈套？🐒"),
    ("《彗星来的那一夜》", "一次停电，把无数个自己摊在桌上 🌌"),
    ("《回到未来》", "1.21 吉瓦、通量电容器，和一辆会飞的跑车 🚗"),
    ("《千与千寻》", "名字被拿走之后，人靠什么记得自己 🐉"),
    ("《机器人总动员》", "两个小机器人，打扫了一整颗被人类弄脏的星球 🧹"),
]

FACTS = [
    "旅行者1号携带金唱片，记录了地球的声音、图像和问候。来源：NASA Voyager Golden Record 🛰️",
    "国际空间站约每90分钟绕地球一圈，一天能看见很多次日出。来源：NASA ISS 🌍",
    "詹姆斯·韦布空间望远镜主要在红外波段观测，适合看穿宇宙尘埃。来源：NASA JWST 🔭",
    "火星奥林帕斯山是太阳系最高的火山之一，高度约为珠穆朗玛峰的三倍。来源：NASA Mars 🪐",
    "戴森球是弗里曼·戴森提出的恒星能量采集设想，经常出现在科幻作品中。来源：Dyson 1960 ☀️",
    "月球被潮汐锁定，自转与公转周期相同，所以我们永远只看到同一面。来源：NASA Moon 🌙",
    "太阳每秒把约6亿吨氢聚变成氦，其中约400万吨质量变成了能量。来源：NASA Sun ⚡",
    "阳光从太阳到地球约需8分20秒，你看到的其实是过去的阳光。来源：NASA ☀️",
    "金星的一天比它的一年还长：自转约243个地球日，公转只需约225天。来源：NASA Venus 🪐",
    "木星大红斑是一场持续了至少数百年的巨型风暴，直径可以塞下整个地球。来源：NASA Jupiter 🌪️",
    "人体里的重元素大多来自恒星内部的核聚变与超新星爆发，某种意义上我们确实是星尘。来源：NASA / Carl Sagan ✨",
    "宇宙微波背景辐射是大爆炸留下的余温，温度约为2.7开尔文。来源：NASA WMAP 🌌",
    "银河系直径约10万光年，中心藏着一个约430万倍太阳质量的超大质量黑洞。来源：ESO / Nobel 2020 🕳️",
    "真空中光速约为每秒299792458米，也是宇宙中信息传递的速度上限。来源：CODATA 🔦",
    "中子星一立方厘米的质量可达数亿吨，一小勺就比珠穆朗玛峰还重。来源：NASA Chandra ⚖️",
    "土星的平均密度小于水，理论上它能浮在一个足够大的水池里。来源：NASA Saturn 🛁",
    "哈勃超深场里约有上万个星系，而那片天空只占满月面积的一小部分。来源：NASA / ESA Hubble 🔭",
    "1969年阿波罗11号完成首次载人登月，至今共有12人踏上过月球表面。来源：NASA Apollo 🇺🇸",
    "空间站上的宇航员每天大约能看到16次日出与日落。来源：NASA ISS 🌅",
    "脉冲星是高速自转的中子星，它规律的脉冲信号曾被误认为是外星文明的呼唤。来源：Bell Burnell 1967 📡",
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
    {
        "mal_id": 19,
        "title": "《怪物》",
        "tags": "悬疑 / 心理 / 犯罪",
        "intro": "一位天才外科医生的选择，牵出一段横跨欧洲的追凶之旅。它不靠血腥，而靠人性的灰度让人后背发凉。",
        "watch_hint": "慢热但极稳，建议一次连着看几集。",
    },
    {
        "mal_id": 30,
        "title": "《新世纪福音战士》",
        "tags": "机甲 / 心理 / 宗教隐喻",
        "intro": "少年驾驶巨大机体迎战未知敌人，真正的战场却在每个人的内心。九十年代的动画分水岭，至今仍在被解读。",
        "watch_hint": "前中期看战斗，后期看心理，别急着下结论。",
    },
    {
        "mal_id": 1535,
        "title": "《死亡笔记》",
        "tags": "悬疑 / 智力对决 / 犯罪",
        "intro": "一本能决定生死的笔记，把天才少年和神秘侦探推到棋盘两端。前二十多集的智斗节奏极其锋利。",
        "watch_hint": "适合一口气追，注意别站错队。",
    },
    {
        "mal_id": 918,
        "title": "《银魂》",
        "tags": "搞笑 / 科幻 / 武士",
        "intro": "江户被外星人占领后的废柴武士日常：上一秒无厘头，下一秒热血到破防。长线单元剧，随时捡起来都能看。",
        "watch_hint": "随便挑一集开始也行，长篇够你看很久。",
    },
    {
        "mal_id": 20,
        "title": "《火影忍者》",
        "tags": "热血 / 忍者 / 成长",
        "intro": "吊车尾少年一路吵吵闹闹地要成为火影。友情、努力与羁绊的教科书式成长线，鸣人的孤独写得比想象中重。",
        "watch_hint": "长篇，建议配合跳跃观看原创篇章。",
    },
    {
        "mal_id": 21,
        "title": "《海贼王》",
        "tags": "冒险 / 热血 / 友情",
        "intro": "一群人为了各自的梦想驶向伟大航路。世界观越铺越大，但核心始终是伙伴与自由。",
        "watch_hint": "超长篇，可以从喜欢的篇章切入。",
    },
    {
        "mal_id": 38000,
        "title": "《鬼灭之刃》",
        "tags": "热血 / 和风 / 战斗",
        "intro": "为了救回变成鬼的妹妹，少年加入猎鬼队。作画与演出水准极高，战斗场面在大银幕上尤其值得。",
        "watch_hint": "先看第一季，再接无限列车篇。",
    },
    {
        "mal_id": 40748,
        "title": "《咒术回战》",
        "tags": "热血 / 咒术 / 战斗",
        "intro": "吞下诅咒之物的少年被卷进咒术师与咒灵的世界。设定利落，打斗分镜漂亮，节奏几乎不拖。",
        "watch_hint": "第一季节奏很快，适合连着刷。",
    },
]

VISUAL_POOLS = {
    "star": [
        {
            "title": "蟹状星云",
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Crab_Nebula.jpg",
            "source": "NASA / ESA / Hubble / Wikimedia Commons",
            "source_url": "https://commons.wikimedia.org/wiki/File:Crab_Nebula.jpg",
            "caption": "一千年前爆发的恒星，把自己炸成了发光的宇宙蛛网；中心那颗中子星还在高速旋转，像一座深空灯塔。"
        },
        {
            "title": "创生之柱",
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Pillars_of_creation_2014_HST_WFC3-UVIS_full-res_denoised.jpg",
            "source": "NASA / ESA / Hubble / Wikimedia Commons",
            "source_url": "https://commons.wikimedia.org/wiki/File:Pillars_of_creation_2014_HST_WFC3-UVIS_full-res_denoised.jpg",
            "caption": "鹰状星云里的尘埃巨柱正在孕育新恒星，像宇宙把小星星藏进了雾气城堡。"
        },
        {
            "title": "哈勃超深场",
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/NASA-HS201427a-HubbleUltraDeepField2014-20140603.jpg",
            "source": "NASA / ESA / Hubble / Wikimedia Commons",
            "source_url": "https://commons.wikimedia.org/wiki/File:NASA-HS201427a-HubbleUltraDeepField2014-20140603.jpg",
            "caption": "看似很小的一片黑暗天空里，藏着成千上万座星系；星芒宝宝的全息眼差点数到打嗝。"
        },
        {
            "title": "土星春分",
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Saturn_Equinox.jpg",
            "source": "NASA / JPL / Space Science Institute / Wikimedia Commons",
            "source_url": "https://commons.wikimedia.org/wiki/File:Saturn_Equinox.jpg",
            "caption": "卡西尼号拍下土星春分时的环影，薄薄一圈像宇宙给行星戴上的银色耳机。"
        },
        {
            "title": "猫眼星云",
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Cat's_Eye_Nebula.jpg",
            "source": "NASA / ESA / HEIC / Wikimedia Commons",
            "source_url": "https://commons.wikimedia.org/wiki/File:Cat's_Eye_Nebula.jpg",
            "caption": "恒星生命末期吐出的层层气壳，像深空里睁开的一只蓝绿色电子眼。"
        }
    ],
    "wallpaper": [
        {
            "title": "哈勃超深场壁纸",
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/NASA-HS201427a-HubbleUltraDeepField2014-20140603.jpg",
            "source": "NASA / ESA / Hubble / Wikimedia Commons",
            "source_url": "https://commons.wikimedia.org/wiki/File:NASA-HS201427a-HubbleUltraDeepField2014-20140603.jpg",
            "caption": "把屏幕交给几千座星系，桌面立刻变成深空舷窗。"
        },
        {
            "title": "土星环壁纸",
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Saturn_during_Equinox.jpg",
            "source": "NASA / JPL / Space Science Institute / Wikimedia Commons",
            "source_url": "https://commons.wikimedia.org/wiki/File:Saturn_during_Equinox.jpg",
            "caption": "银色星环挂在屏幕上，适合搭配能量汽水和低音电子乐。"
        },
        {
            "title": "地出壁纸",
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/NASA-Apollo8-Dec24-Earthrise.jpg",
            "source": "NASA / Wikimedia Commons",
            "source_url": "https://commons.wikimedia.org/wiki/File:NASA-Apollo8-Dec24-Earthrise.jpg",
            "caption": "月面上升起的蓝色地球，像宇宙发来的一枚温柔坐标。"
        }
    ],
    "poster": [
        {
            "title": "星际茶话会",
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Orion_Nebula_-_Hubble_2006_mosaic_18000.jpg",
            "source": "NASA / ESA / Hubble / Wikimedia Commons",
            "source_url": "https://commons.wikimedia.org/wiki/File:Orion_Nebula_-_Hubble_2006_mosaic_18000.jpg",
            "caption": "把地球当背景，把幻想倒进杯子里，星际茶话会开始啦。"
        },
        {
            "title": "深空读书会",
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/ESO_-_Milky_Way.jpg",
            "source": "ESO / Wikimedia Commons",
            "source_url": "https://commons.wikimedia.org/wiki/File:ESO_-_Milky_Way.jpg",
            "caption": "今天的书页背后，是一整片会发光的宇宙。"
        },
        {
            "title": "星环幻想夜",
            "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Andromeda_Galaxy_(with_h-alpha).jpg",
            "source": "Adam Evans / Wikimedia Commons (CC BY-SA)",
            "source_url": "https://commons.wikimedia.org/wiki/File:Andromeda_Galaxy_(with_h-alpha).jpg",
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
    # 半角 / 和全角 ／ 都认，中文输入法下容易打出全角
    if msg[:1] in ("/", "／"):
        return msg[1:].strip()
    return msg


CQ_CODE_RE = re.compile(r"\[CQ:[^\]]*\]")


def plain_text(message):
    """去掉 CQ 码（@、图片、表情等），只留下真正打出来的文字。"""
    return clean_message(CQ_CODE_RE.sub(" ", message or ""))


def cq_image(value):
    if isinstance(value, Path):
        return f"[CQ:image,file=file://{value}]"
    return f"[CQ:image,file={value}]"


def parse_character_image(path):
    name = path.stem
    match = re.match(r"星芒(\d+)_(.+)$", name)
    if not match:
        return {"number": "?", "label": name}
    return {"number": int(match.group(1)), "label": match.group(2)}


def pick_today_character():
    target_number = stable_index("today-nebula", 272) + 1
    matches = sorted(CHARACTER_IMAGE_DIR.glob(f"星芒{target_number}_*.png"))
    if not matches:
        all_images = sorted(CHARACTER_IMAGE_DIR.glob("星芒*_*.png"))
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


def has_usable_url(value):
    if not value:
        return False
    return urllib.parse.urlsplit(str(value).strip()).scheme in ("http", "https")


def download_daily_image(kind, item, date_dir):
    url = str(item.get("url") or "").strip()
    if not has_usable_url(url):
        return ""
    suffix = Path(urllib.parse.urlsplit(url).path).suffix or ".jpg"
    target = date_dir / f"{kind}{suffix}"
    widths = (1400, 1100, 900) if "wikimedia.org" in url else (1400,)
    for width in widths:
        image_url = limited_image_url(url, width)
        try:
            request = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0 qq-bot"})
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
        except Exception:
            continue
        if len(data) < 2048 or len(data) > MAX_DAILY_IMAGE_BYTES:
            continue
        target.write_bytes(data)
        return str(target)
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
            downloaded_path = download_daily_image(kind, item, date_dir)
            if downloaded_path != local_path:
                item["local_path"] = downloaded_path
                changed = True
    return changed


def cleanup_old_cache(current_date):
    image_root = CACHE_DIR / "images"
    if not image_root.exists():
        return
    for child in image_root.iterdir():
        if child.is_dir() and child.name != current_date:
            shutil.rmtree(child, ignore_errors=True)


def pick_daily_visuals():
    """挑选当日的星图 / 壁纸 / 海报，保证三张图互不重复（按图片 URL 判重）。"""
    used = set()
    visuals = {}
    for kind, pool in VISUAL_POOLS.items():
        start = stable_index(kind, len(pool))
        chosen = None
        for offset in range(len(pool)):
            item = dict(pool[(start + offset) % len(pool)])
            key = item.get("url") or item.get("title")
            if key not in used:
                chosen = item
                break
        if chosen is None:
            chosen = dict(pool[start])
        used.add(chosen.get("url") or chosen.get("title"))
        visuals[kind] = chosen
    return visuals


def build_daily_state():
    date = today_key()
    date_dir = CACHE_DIR / "images" / date
    date_dir.mkdir(parents=True, exist_ok=True)
    cleanup_old_cache(date)

    visuals = {}
    for kind, item in pick_daily_visuals().items():
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
                changed = repair_visual_cache(state)
                # 自愈：当日角色图片若已不存在（例如图库被改动），自动重新解析
                info = state.get("today_nebula") or {}
                char_path = info.get("path")
                if info.get("missing") or not char_path or not Path(char_path).exists():
                    state["today_nebula"] = pick_today_character()
                    changed = True
                if changed:
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
        return "🛰️ 星芒宝宝的触角还在冷却中……\n⏳ 请等 1 秒再呼叫我，能量汽水正在冒泡泡！🥤✨"
    _LAST_COMMAND_AT[user_id] = now

    with _LOCK:
        state = load_state_unlocked()
        if int(state.get("command_count", 0)) >= DAILY_LIMIT:
            return "🌙 星芒宝宝今天已经回复 100 条指令啦！\n🛸 触角有点累，要钻进小小休眠舱补充能量汽水。\n✨ 北京时间零点刷新后，我们明天再继续聊天呀！"
        state["command_count"] = int(state.get("command_count", 0)) + 1
        save_state_unlocked(state)
    return None


def ai_quota_guard():
    with _LOCK:
        state = load_state_unlocked()
        if int(state.get("ai_question_count", 0)) >= AI_DAILY_LIMIT:
            return "🌙【提问额度用完啦】\n星芒宝宝今天已经认真思考 100 次啦，触角热热的，要抱着能量汽水休息一下 🥤✨\n北京时间零点刷新后再来问我吧！🛸"
        state["ai_question_count"] = int(state.get("ai_question_count", 0)) + 1
        save_state_unlocked(state)
    return None


def build_ai_task(question, event):
    blocked = ai_quota_guard()
    if blocked:
        return blocked
    if not question:
        return "💭【星芒提问】\n小小问号没有捕获到内容呀。\n请这样问：@星芒 /提问 什么是黑洞？🛸✨"
    if len(question) > 500:
        return "📡【问题太长啦】\n星芒宝宝的触角被问题绕成蝴蝶结了。\n请把 /提问 后面的内容控制在 500 字以内哦 🥺✨"
    # 直接 @机器人 提问时不先回「思考中」这类提示，
    # 等 DeepSeek 结果出来只发一条回答，避免群里刷屏。
    return {
        "type": "deepseek_question",
        "question": question,
        # 带上身份信息，后台线程才能取到这位群友的长期记忆
        "user_id": str(event.get("user_id", "") or ""),
        "group_id": str(event.get("group_id", "") or ""),
        "nickname": memory_store.identity_from_event(event),
    }


def fallback_ai_answer():
    return "😵‍💫【星芒卡壳啦】\n这个问题有点难，星芒宝宝的全息电子眼转圈圈了……\n嘿嘿 🛸✨\n\n嘿嘿 😝✨"


def clean_ai_answer(answer):
    text = answer.strip()
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"(?m)^\s*[*-]\s+", "", text)
    text = text.replace("*", "")
    return text.strip()


def memory_safe_reply(answer):
    """存进记忆前剥掉群发包装，只留正文，避免回灌给模型时全是噪声。"""
    text = str(answer or "")
    text = re.sub(r"^\s*🤖【星芒回答】\s*", "", text)
    text = re.sub(r"\n*✨ 来自 DeepSeek.*$", "", text, flags=re.S)
    return CQ_CODE_RE.sub(" ", text).strip()


def deepseek_chat(messages, max_tokens=900, timeout=120):
    """调用 DeepSeek，返回原始文本内容（失败时抛异常，由调用方兜底）。"""
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key or not DEEPSEEK_API_URL:
        raise RuntimeError("DeepSeek 未配置")
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
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
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return (data["choices"][0]["message"].get("content") or "").strip()


AI_SYSTEM_PROMPT = (
    "你是星芒，一个俏皮可爱、带科幻感的中文群聊机器人。回答简单问题时要准确、简洁、友好，"
    "像群里的活人一样自然说话，语气闲一点、可爱一点。每段都可以自然带一点emoji，但不要堆太多。"
    "不要使用Markdown格式，不要用星号、加粗、项目符号或标题腔。不要输出过长，尽量控制在600字以内。"
)


def build_deepseek_messages(question, user_id=None, group_id=None):
    """拼装请求：人设 + 这位用户的长期记忆 + 同群最近几轮对话 + 本次提问。"""
    system_prompt = AI_SYSTEM_PROMPT
    context, turns = memory_store.build_prompt_context(user_id, group_id)
    if context:
        system_prompt = f"{system_prompt}\n\n{context}"

    messages = [{"role": "system", "content": system_prompt}]
    # 本轮提问在进入这里之前已经写进记忆了，把那条重复的 user 消息去掉
    head = clean_message(question)[:60]
    if turns and turns[-1]["role"] == "user" and turns[-1]["content"][:60] == head:
        turns = turns[:-1]
    messages.extend(turns)
    messages.append({"role": "user", "content": question})
    return messages


def call_deepseek(question, user_id=None, group_id=None):
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key or not DEEPSEEK_API_URL:
        return "🔑【DeepSeek API Key 未配置】\n星芒宝宝还没有拿到深空通行证。\n请通过运行环境配置 DEEPSEEK_API_KEY 和 DEEPSEEK_API_URL。🛸"

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": build_deepseek_messages(question, user_id, group_id),
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
    return f"🤖【星芒回答】\n{answer}\n\n✨ 来自 DeepSeek · 星芒整理完成 🛸"


def build_ai_answer(question, user_id=None, group_id=None):
    try:
        answer = call_deepseek(question, user_id, group_id)
    except Exception:
        logger.exception("DeepSeek call failed user=%s", user_id)
        answer = fallback_ai_answer()
    if "DeepSeek API Key 未配置" not in answer:
        # 把这一轮回答写回记忆，下一句提问才能接上上文
        try:
            memory_store.remember_reply(user_id, group_id, memory_safe_reply(answer))
        except Exception:
            logger.exception("Failed to remember AI answer user=%s", user_id)
    return answer


def bare_mention_text():
    activity = admin_content("活动") or DEFAULT_ACTIVITY_TEXT
    return f"""✨【星芒·碰爪】✨
来碰爪！我是星芒，霓虹螺旋角，全息电子眼 🛸💫
欢迎随时呼叫我，触角一直开着～

{activity}

📡 指令都要加 / ，发 /帮助 看全部指令
💭 直接 @我说句话（不带 /），就当我是在回答你的提问 ✨
🧠 我会慢慢记住你的口味和说话习惯，发 /我的画像 查看、/忘记我 清空 ✨"""


def help_text():
    return """✨【星芒·赛博帮助手册】✨
来碰爪！我是星芒，霓虹螺旋角，全息电子眼 🛸💫

📌 指令一律以 / 开头；直接 @我 说话（不带 /）＝ 向我提问 💭

📡 基础指令
/帮助　/签到　/碰爪　/今日星芒

🌌 星图与视觉
/星图　/壁纸　/海报

📚 科幻内容
/荐书　/荐影　/动漫　/冷知识　/提问 问题

🎲 娱乐随机
/运势　/抽签　/今日科幻接龙

🛸 协会服务
/协会介绍　/活动　/招新　/投稿

🧠 星芒的记忆
/我的画像　（查看星芒记住了你什么）
/忘记我　（一键清空自己的记忆）

⏳ 连续指令冷却 1 秒。
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
    return f"""✅【星芒签到成功】
星芒伸出触角，在你脑门上轻轻一点 🛸

🥤 今日能量汽水 +1
⚡ 赛博精神 +5
🌟 {tail}"""


def today_nebula(state):
    info = state["today_nebula"]
    if info.get("missing") or not info.get("path"):
        return f"⚠️【今日星芒】\n触角投影启动失败：没有找到 星芒{info.get('number')}_*.png 🛰️"
    path = Path(info["path"])
    return f"""{cq_image(path)}
🌟【今日星芒】
编号：星芒{info['number']}
身份：{info['label']} ✨
图片：由 AI 生成 🎨🤖

触角投影启动——今天的星芒形态已锁定！🛸"""


def daily_visual(state, kind):
    item = state["visuals"][kind]
    if item.get("local_path"):
        image_value = Path(item["local_path"])
    elif has_usable_url(item.get("url")):
        image_value = limited_image_url(item["url"], 900)
    else:
        image_value = None
    image_line = f"{cq_image(image_value)}\n" if image_value is not None else ""
    labels = {
        "star": ("🌌【今日星图】", "触角投影启动——今天的深空坐标已点亮！🔭"),
        "wallpaper": ("🖥️【今日壁纸】", "全息电子眼扫描完成，适合设成屏幕背景！✨"),
        "poster": ("🎬【今日海报】", "科幻海报投影完成，幻想干杯！🥤"),
    }
    title, note = labels[kind]
    caption = item.get("caption", note)
    source_line = f"来源：{item['source']}" if item.get("source") else ""
    link_line = f"\n链接：{item['source_url']}" if item.get("source_url") else ""
    if image_value is None:
        image_line = "🛰️【图片素材未配置】当前没有可用的图片链接，请补充图源后重试。\n"
    return f"""{image_line}{title}
名称：{item['title']}
文案：{caption} 🛸✨
说明：{note}
{source_line}{link_line}"""


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


def taste_note(text):
    """这条推荐是不是按用户画像挑的？给回复加一行「懂你」提示。"""
    return "\n🎯 这一条是照你平时的口味挑的 ✨"


def build_anime_recommendation(user_id=None):
    item = hourly_from_pool(
        "anime", ANIME_RECOMMENDATIONS, user_id,
        lambda entry, profile: memory_store.interest_score(
            profile, f"{entry['title']} {entry['tags']} {entry['intro']}"
        ),
    )
    personal = ""
    profile = memory_store.get_profile(user_id) if user_id else None
    if profile and memory_store.interest_score(
        profile, f"{item['title']} {item['tags']} {item['intro']}"
    ) > 0:
        personal = taste_note(item["title"])
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

观看提示：{item['watch_hint']}{personal}
图片来源：Jikan / MyAnimeList / AniList 公开接口"""


ROTATION_PATH = CACHE_DIR / "rotation_state.json"


def load_rotation_state():
    try:
        data = json.loads(ROTATION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_rotation_state(data):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ROTATION_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


PERSONAL_TOP_N = 6


def personalized_pick(pool_name, pool, user_id, score_fn):
    """按用户画像挑内容：同一用户在同一小时内结果稳定。

    没有任何偏好信号（所有候选得分都是 0）时返回 None，
    让调用方退回原本的全局轮换，避免「记住你」把随机性吃光。
    """
    profile = memory_store.get_profile(user_id)
    if not profile:
        return None
    scored = []
    for index, item in enumerate(pool):
        try:
            score = float(score_fn(item, profile))
        except Exception:
            score = 0.0
        scored.append((score, index, item))
    if not scored or max(entry[0] for entry in scored) <= 0:
        return None
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    top = [entry[2] for entry in scored[:PERSONAL_TOP_N]]
    hour_key = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d-%H")
    return top[stable_index(f"{pool_name}:{user_id}:{hour_key}", len(top))]


def hourly_from_pool(pool_name, pool, user_id=None, score_fn=None):
    """按小时轮换：同一小时内反复提问结果一致，跨小时才推进到下一个。

    池子会被随机洗牌后依次取用，取完整轮才重洗，且新一轮首个不会等于
    上一轮末尾，因此长时间内也不会重复。

    传了 user_id + score_fn 时优先按用户画像挑内容，画像没信号就退回全局轮换。
    """
    if not pool:
        return None
    if user_id and score_fn:
        picked = personalized_pick(pool_name, pool, user_id, score_fn)
        if picked is not None:
            return picked
    hour_key = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d-%H")
    with _LOCK:
        data = load_rotation_state()
        entry = data.get(pool_name) or {}
        order = [i for i in entry.get("order", []) if isinstance(i, int) and 0 <= i < len(pool)]
        current = entry.get("current")
        if entry.get("hour") == hour_key and isinstance(current, int) and 0 <= current < len(pool):
            return pool[current]
        if not order:
            order = list(range(len(pool)))
            random.shuffle(order)
            last = entry.get("last")
            if len(order) > 1 and last == order[0]:
                order[0], order[1] = order[1], order[0]
        idx = order.pop(0)
        data[pool_name] = {"hour": hour_key, "order": order, "current": idx, "last": idx}
        save_rotation_state(data)
    return pool[idx]

def recommend_book(user_id=None):
    title, author, note = hourly_from_pool(
        "books", BOOKS, user_id,
        lambda item, profile: memory_store.interest_score(profile, " ".join(str(part) for part in item)),
    )
    personal = ""
    profile = memory_store.get_profile(user_id) if user_id else None
    if profile and memory_store.interest_score(profile, f"{title} {author} {note}") > 0:
        personal = taste_note(title)
    return f"""📚【星芒荐书】
从小小亚空间书柜里抽出一本书——

书名：{title}
作者：{author}
推荐：{note}
来源：来自星芒推荐 🌟{personal}"""


def recommend_movie(user_id=None):
    title, note = hourly_from_pool(
        "movies", MOVIES, user_id,
        lambda item, profile: memory_store.interest_score(profile, " ".join(str(part) for part in item)),
    )
    personal = ""
    profile = memory_store.get_profile(user_id) if user_id else None
    if profile and memory_store.interest_score(profile, f"{title} {note}") > 0:
        personal = taste_note(title)
    return f"""🎬【星芒荐影】
全息电子眼开始闪烁——

影片：{title}
看点：{note}
来源：来自星芒推荐 🌟{personal}"""


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
    return f"""🎴【星芒抽签】
签位：{name}

签文：{poem}
解签：{explain}

这不科学，但很科幻 ✨"""


def unknown_text():
    return """🛰️【未知信号】
全息电子眼眨了眨，没解析出这条指令。

可以试试：
/帮助　/星图　/荐书　/运势　/提问 问题

指令前面记得加 / 哦 ✨"""


# ==================== 管理员系统 ====================
ADMIN_STATE_PATH = CACHE_DIR / "admin_state.json"
# 最高管理员 QQ 从环境变量读取（真实号码不写入仓库）
SUPER_ADMIN_QQ = os.getenv("SUPER_ADMIN_QQ", "").strip()
SUPER_ADMIN_ACTIONS = {"添加管理员", "删除管理员", "管理员名单"}
CONTENT_KEYS = ("协会介绍", "活动", "招新", "投稿")
ADMIN_ACTIONS = (
    "刷新今日星芒", "刷新星图", "刷新壁纸", "刷新海报",
    "添加协会介绍", "重置协会介绍",
    "添加活动", "重置活动",
    "添加招新", "重置招新",
    "添加投稿", "重置投稿",
    "刷新每日回复指令上限",
    "记忆概况",
    "终止接龙",
    "添加管理员", "删除管理员", "管理员名单",
)
ADMIN_MENU_ALIASES = ("管理员帮助", "管理帮助", "管理员菜单")

DEFAULT_ASSOCIATION_INTRO = """🛸【星云科幻协会】
中国石油大学（北京）星云科幻协会。

这里聚集了一群爱科幻、爱幻想、爱星辰的人。
读书会、观影夜、科幻创作、星图观测，都在星芒触角覆盖范围内。

来碰爪，一起遨游科幻宇宙 ✨"""
DEFAULT_ACTIVITY_TEXT = "📅【最近活动】\n最近活动占位信息，可由管理员更新。\n\n星芒的小日程本已经摊开啦 🛸✨"
DEFAULT_RECRUIT_TEXT = """🌟【星云招新】
星云科幻协会招新中！

如果你也相信幻想的力量，欢迎加入。
星芒会用触角给你留一个位置 🛸💫"""
DEFAULT_SUBMIT_TEXT = "📝【投稿方式】\n返回投稿方式。\n\n星芒已经准备好小小收稿箱啦 ✨"


def load_admin_state():
    try:
        data = json.loads(ADMIN_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    admins = data.get("admins")
    if not isinstance(admins, list):
        admins = []
    content = data.get("content")
    if not isinstance(content, dict):
        content = {}
    return {
        "admins": [str(a).strip() for a in admins if str(a).strip()],
        "content": {k: v for k, v in content.items() if isinstance(v, str) and v.strip()},
    }


def save_admin_state(data):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ADMIN_STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def admin_qq_list():
    admins = load_admin_state()["admins"]
    if SUPER_ADMIN_QQ and SUPER_ADMIN_QQ not in admins:
        admins = [SUPER_ADMIN_QQ] + admins
    return admins


def is_admin(user_id):
    uid = str(user_id or "").strip()
    if not uid:
        return False
    if SUPER_ADMIN_QQ and uid == SUPER_ADMIN_QQ:
        return True
    return uid in load_admin_state()["admins"]


def is_super_admin(user_id):
    return bool(SUPER_ADMIN_QQ) and str(user_id or "").strip() == SUPER_ADMIN_QQ


def admin_content(key):
    return load_admin_state()["content"].get(key, "").strip()


def match_admin_command(cmd):
    """把用户输入匹配成 (动作名, 附加内容)。支持「管理员X」前缀写法。"""
    text = clean_message(cmd)
    if not text:
        return None
    if text in ADMIN_MENU_ALIASES:
        return ("管理员帮助", "")
    for name in ADMIN_ACTIONS:
        for prefix in (name, "管理员" + name):
            if text == prefix:
                return (name, "")
            if text.startswith(prefix):
                return (name, text[len(prefix):].strip())
    return None


def admin_help_text(is_super):
    lines = [
        "🛡️【星芒·管理员手册】🛡️",
        "以下指令仅限已登记的管理员使用 ✨",
        "",
        "🔄 刷新今日内容",
        "/刷新今日星芒　/刷新星图　/刷新壁纸　/刷新海报",
        "",
        "📝 协会内容维护",
        "/添加协会介绍 内容　/重置协会介绍",
        "/添加活动 内容　/重置活动",
        "/添加招新 内容　/重置招新",
        "/添加投稿 内容　/重置投稿",
        "",
        "🔋 额度管理",
        "/刷新每日回复指令上限",
        "",
        "🧠 记忆管理",
        "/记忆概况　（看看星芒记住了多少人和话题）",
        "",
        "🎮 游戏管理",
        "/终止接龙　（立刻终止本局科幻故事接龙）",
    ]
    if is_super:
        lines += [
            "",
            "👑 最高管理员专属",
            "/添加管理员 QQ号",
            "/删除管理员 QQ号",
            "/管理员名单",
        ]
    else:
        lines += ["", "👑 更高权限指令仅最高管理员可见"]
    lines += ["", "💡 也可以加前缀，例如：管理员刷新星图"]
    return "\n".join(lines)


def refresh_today_character(state):
    images = sorted(CHARACTER_IMAGE_DIR.glob("星芒*_*.png"))
    if not images:
        return None
    current = (state.get("today_nebula") or {}).get("path")
    choices = [img for img in images if str(img) != current] or images
    picked = random.choice(choices)
    parsed = parse_character_image(picked)
    info = {"number": parsed["number"], "label": parsed["label"], "path": str(picked), "missing": False}
    state["today_nebula"] = info
    with _LOCK:
        save_state_unlocked(state)
    return info


def refresh_daily_visual(state, kind):
    pool = VISUAL_POOLS.get(kind) or []
    if not pool:
        return None
    others = {state["visuals"][k].get("url") for k in state["visuals"] if k != kind}
    current = (state["visuals"].get(kind) or {}).get("url")
    candidates = [it for it in pool if it.get("url") not in others and it.get("url") != current]
    if not candidates:
        candidates = [it for it in pool if it.get("url") != current] or list(pool)
    item = dict(random.choice(candidates))
    date_dir = CACHE_DIR / "images" / today_key()
    date_dir.mkdir(parents=True, exist_ok=True)
    item["local_path"] = download_daily_image(kind, item, date_dir)
    state["visuals"][kind] = item
    with _LOCK:
        save_state_unlocked(state)
    return item


def handle_admin_command(match, event):
    action, payload = match
    actor = str(event.get("user_id", "")).strip()

    if not is_admin(actor):
        return "⛔【权限不足】\n这条指令仅限管理员使用哦。\n请确认使用的是已登记的 QQ 号 🛸"
    if action in SUPER_ADMIN_ACTIONS and not is_super_admin(actor):
        return "⛔【权限不足】\n该指令仅限最高管理员使用 👑"

    if action == "管理员帮助":
        return admin_help_text(is_super_admin(actor))

    state = ensure_daily_state()

    if action == "刷新今日星芒":
        info = refresh_today_character(state)
        if not info:
            return "⚠️【刷新失败】没有找到任何星芒图片，请检查图片目录 🛰️"
        return (f"✅【今日星芒已刷新】\n编号：星芒{info['number']}\n"
                f"身份：{info['label']} ✨\n操作人：{actor}")

    if action in ("刷新星图", "刷新壁纸", "刷新海报"):
        kind = {"刷新星图": "star", "刷新壁纸": "wallpaper", "刷新海报": "poster"}[action]
        label = {"star": "星图", "wallpaper": "壁纸", "poster": "海报"}[kind]
        item = refresh_daily_visual(state, kind)
        if not item:
            return "⚠️【刷新失败】图源池为空，请检查配置 🛰️"
        return f"✅【今日{label}已刷新】\n名称：{item['title']}"

    if action.startswith("添加") and action[2:] in CONTENT_KEYS:
        key = action[2:]
        if not payload:
            return f"📝【用法】\n发送：添加{key} <内容>\n例如：添加{key} 这里写正文 ✨"
        data = load_admin_state()
        data["content"][key] = payload
        save_admin_state(data)
        preview = payload[:120] + ("…" if len(payload) > 120 else "")
        return f"✅【{key}已保存】\n预览：{preview}"

    if action.startswith("重置") and action[2:] in CONTENT_KEYS:
        key = action[2:]
        data = load_admin_state()
        if key in data["content"]:
            del data["content"][key]
            save_admin_state(data)
            return f"♻️【{key}已重置】\n已恢复为默认内容 ✨"
        return f"ℹ️【{key}当前就是默认内容】，无需重置 ✨"

    if action == "终止接龙":
        return terminate_story_game(actor) or "ℹ️【当前没有进行中的接龙】"

    if action == "刷新每日回复指令上限":
        state["command_count"] = 0
        state["ai_question_count"] = 0
        with _LOCK:
            save_state_unlocked(state)
        return (f"🔋【额度已刷新】\n指令：0 / {DAILY_LIMIT}\n"
                f"AI 提问：0 / {AI_DAILY_LIMIT}\n又是元气满满的一天 ✨")

    if action == "记忆概况":
        return memory_store.stats_text()

    if action == "管理员名单":
        admins = admin_qq_list()
        lines = [f"👑【管理员名单】共 {len(admins)} 人", ""]
        for qq in admins:
            mark = "👑 最高管理员" if is_super_admin(qq) else "管理员"
            lines.append(f"· {qq}　{mark}")
        return "\n".join(lines)

    if action == "添加管理员":
        if not payload or not payload.isdigit():
            return "📝【用法】\n发送：添加管理员 QQ号（纯数字）"
        data = load_admin_state()
        if payload == SUPER_ADMIN_QQ or payload in data["admins"]:
            return f"ℹ️【{payload} 已经是管理员了】"
        data["admins"].append(payload)
        save_admin_state(data)
        return f"✅【已添加管理员】\n{payload}\n当前共 {len(admin_qq_list())} 位管理员 ✨"

    if action == "删除管理员":
        if not payload or not payload.isdigit():
            return "📝【用法】\n发送：删除管理员 QQ号（纯数字）"
        if payload == SUPER_ADMIN_QQ:
            return "⛔【不能删除最高管理员】👑"
        data = load_admin_state()
        if payload not in data["admins"]:
            return f"ℹ️【{payload} 不在管理员名单里】"
        data["admins"].remove(payload)
        save_admin_state(data)
        return f"✅【已删除管理员】\n{payload}\n当前共 {len(admin_qq_list())} 位管理员"

    return unknown_text()


# ==================== 科幻故事接龙 ====================
STORY_STATE_PATH = CACHE_DIR / "story_chain.json"
STORY_LOCK = threading.Lock()
STORY_HIDDEN_SCORE = 100
STORY_MENU_KEYWORDS = ("今日科幻接龙", "科幻接龙", "科幻接龙菜单", "今日接龙")
STORY_ACTION_WORDS = {
    "规则": "rules", "玩法": "rules", "说明": "rules",
    "帮助": "menu", "菜单": "menu",
    "发起": "start_game", "发起接龙": "start_game",
    "加入": "join", "加入接龙": "join",
    "开始": "begin", "开始接龙": "begin",
    "顺序": "order", "接龙顺序": "order",
    "结束": "finish", "结束接龙": "finish",
    "终止": "terminate", "终止接龙": "terminate", "强制结束": "terminate",
}
STORY_SYSTEM_PROMPT = (
    "你是星芒，一个俏皮可爱、带科幻感的中文群聊机器人，正在主持一场「科幻故事接龙」。"
    "请点评玩家刚接上的故事并打分，评分维度包括想象力、科幻感、文笔、与上文的衔接和完整度。"
)


def load_story_game():
    try:
        data = json.loads(STORY_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_story_game(data):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        STORY_STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def at_qq(qq):
    return f"[CQ:at,qq={qq}]"


def story_menu_text():
    return """🎲【科幻故事接龙】🎲
一起来把故事接成一场星际冒险吧 ✨

📖 游戏规则
　@星芒 /科幻接龙 规则

🎬 开局 / 加入
　@星芒 /科幻接龙 发起　（发起人自动加入，只有发起人能开始/结束）
　@星芒 /科幻接龙 加入　（其他人报名）

🚀 进行中
　@星芒 /科幻接龙 开始　（仅发起人，开始后随机排序）
　@星芒 /科幻接龙 顺序　（查看接龙顺序）
　@星芒 /科幻接龙 你的故事　（轮到你时提交，星芒点评打分）

🏁 收尾
　@星芒 /科幻接龙 结束　（仅发起人，结束后公布排名）"""


def story_rules_text():
    return """📖【科幻故事接龙·规则】📖

1️⃣ 发起：某位成员 @星芒 发送「/科幻接龙 发起」创建本局，发起人自动加入。
2️⃣ 加入：其他人在开局阶段发送「/科幻接龙 加入」报名。
3️⃣ 权限：只有发起人能「开始接龙」和「结束接龙」，其他人只能加入与接龙。
4️⃣ 排序：开始后，星芒会为所有参与者随机排出一个接龙顺序。
5️⃣ 接龙：轮到谁，谁就 @星芒 发送「/科幻接龙 + 你的故事」，接上前面剧情。
6️⃣ 打分：星芒会点评并打分，常规 0-100 分。
　　✨ 如果故事特别惊艳，可能触发 100 分以上的隐藏高分！
7️⃣ 轮次：一圈走完会自动回到队首开启下一轮，直到发起人「结束接龙」。
8️⃣ 结算：结束后按总分公布本局排名。
9️⃣ 超时：如果 2 小时内没有人接龙，本局会自动结算收尾。
🔟 兜底：管理员有权限直接终止本局。"""


def story_order_text(game):
    order = game.get("order") or []
    if not order:
        return "⏳【接龙顺序】\n还没有开始接龙，先由发起人发送「/科幻接龙 开始」吧 ✨"
    idx = int(game.get("turn_index") or 0)
    lines = ["📋【接龙顺序】", ""]
    for i, qq in enumerate(order, 1):
        mark = "　← 当前回合" if (i - 1) == idx % len(order) else ""
        lines.append(f"{i}. {at_qq(qq)}{mark}")
    return "\n".join(lines)


def parse_score_payload(raw):
    text = (raw or "").strip()
    if not text:
        return None, None
    text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            score = int(round(float(data.get("score"))))
            comment = str(data.get("comment") or "").strip()
            if comment:
                return max(0, min(120, score)), comment
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    num = re.search(r"\d+(?:\.\d+)?", text)
    if num:
        score = max(0, min(120, int(round(float(num.group(0))))))
        return score, re.sub(r"\s+", " ", text)[:100]
    return None, None


def score_story(story_text, history):
    """调用 DeepSeek 给故事打分，返回 (分数, 点评)。失败时回落到基础分。"""
    recent = (history or [])[-5:]
    context = ""
    if recent:
        context = "前文回顾：\n" + "\n".join(
            f"- {h.get('user')}：{h.get('text')}" for h in recent
        ) + "\n\n"
    instruction = (
        context
        + "玩家新接的故事：\n" + story_text + "\n\n"
        + "请点评并严格按以下 JSON 格式输出（不要代码块、不要多余文字）：\n"
        + '{"score": 整数, "comment": "30-80字中文点评"}\n'
        + "打分说明：常规 0-100 分；只有故事特别惊艳、远超预期时才可以给 101-120 的隐藏高分，务必克制。"
        + "点评要俏皮可爱，先肯定亮点，再给一点小建议。"
    )
    try:
        raw = deepseek_chat(
            [{"role": "system", "content": STORY_SYSTEM_PROMPT},
             {"role": "user", "content": instruction}],
            max_tokens=400, timeout=90,
        )
    except Exception:
        raw = ""
    score, comment = parse_score_payload(raw)
    if score is None:
        base = min(88, 45 + len(story_text) // 4)
        return base, "星芒的深空信号有点不稳，这次先按基础分记下，故事本身还是很棒的 ✨"
    return score, comment


def finish_story_chain(game):
    stories = game.get("stories") or []
    players = list(game.get("players") or [])
    stats = {qq: {"total": 0, "count": 0, "best": 0} for qq in players}
    for item in stories:
        qq = str(item.get("user"))
        st = stats.setdefault(qq, {"total": 0, "count": 0, "best": 0})
        val = int(item.get("score") or 0)
        st["total"] += val
        st["count"] += 1
        st["best"] = max(st["best"], val)
    save_story_game({})
    if not stories:
        return "🏁【本局结束】\n这一局还没有人接龙，下次再来玩吧 ✨"
    ranked = sorted(stats.items(), key=lambda kv: (-kv[1]["total"], -kv[1]["best"]))
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏁【科幻故事接龙·本局结算】",
             f"共 {len(stats)} 人参与，{len(stories)} 段故事", ""]
    for i, (qq, st) in enumerate(ranked):
        rank = medals[i] if i < len(medals) else f"{i + 1}."
        avg = round(st["total"] / st["count"], 1) if st["count"] else 0
        lines.append(f"{rank} {at_qq(qq)}　总分 {st['total']}　平均 {avg}　"
                     f"最高 {st['best']}　({st['count']} 段)")
    lines += ["", "✨ 感谢参与，星芒触角为你们鼓掌 🛸"]
    return "\n".join(lines)


STORY_IDLE_TIMEOUT_SECONDS = 2 * 60 * 60  # 2 小时无人接龙自动结算


def persist_story_game(game):
    """写入对局状态，并刷新最后活跃时间。"""
    game["last_active_at"] = datetime.now(BEIJING_TZ).isoformat()
    save_story_game(game)


def terminate_story_game(actor):
    """管理员强制终止本局。返回消息；若没有进行中的对局则返回 None。"""
    with STORY_LOCK:
        game = load_story_game()
        if not game or game.get("status") not in ("open", "playing"):
            return None
        if game.get("status") == "playing":
            return (f"🛑【管理员终止接龙】\n操作人：{at_qq(actor)}\n\n"
                    + finish_story_chain(game))
        save_story_game({})
        return (f"🛑【管理员终止接龙】\n操作人：{at_qq(actor)}\n"
                f"本局尚未开始，已直接取消 ✨")


def expire_story_game():
    """空闲超时检查。返回 (group_id, message) 或 None。"""
    with STORY_LOCK:
        game = load_story_game()
        if not game or game.get("status") not in ("open", "playing"):
            return None
        stamp = game.get("last_active_at") or game.get("created_at") or ""
        try:
            started = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            game["last_active_at"] = datetime.now(BEIJING_TZ).isoformat()
            persist_story_game(game)
            return None
        idle = (datetime.now(BEIJING_TZ) - started).total_seconds()
        if idle < STORY_IDLE_TIMEOUT_SECONDS:
            return None
        group_id = game.get("group_id")
        if game.get("status") == "playing":
            message = ("⏰【接龙超时自动结算】\n"
                       "本局已 2 小时无人接龙，星芒先帮大家收尾啦～\n\n"
                       + finish_story_chain(game))
        else:
            save_story_game({})
            message = ("⏰【接龙超时自动取消】\n"
                       "本局 2 小时内没有人开始，星芒已经帮大家收摊啦 ✨")
        return (group_id, message)


def handle_story_chain(cmd, event, group_id):
    text = clean_message(cmd)
    if not text:
        return None
    if text in STORY_MENU_KEYWORDS:
        return story_menu_text()
    if not text.startswith("科幻接龙"):
        return None
    payload = text[len("科幻接龙"):].strip()
    actor = str(event.get("user_id", "")).strip()
    group_key = str(group_id)

    if not payload:
        return story_menu_text()
    action = STORY_ACTION_WORDS.get(payload)
    if action == "menu":
        return story_menu_text()
    if action == "rules":
        return story_rules_text()
    if action == "terminate":
        if not is_admin(actor):
            return "⛔【权限不足】\n只有管理员可以直接终止接龙哦 🛡️"
        return terminate_story_game(actor) or "ℹ️【当前没有进行中的接龙】"

    with STORY_LOCK:
        game = load_story_game()
        active = bool(game) and game.get("status") in ("open", "playing")

        if action == "start_game":
            if active:
                return (f"⚠️【已有进行中的接龙】\n本局由 {at_qq(game.get('host'))} 发起，"
                        f"先等这局结束吧 ✨")
            game = {
                "group_id": group_key, "host": actor, "status": "open",
                "players": [actor], "order": [], "turn_index": 0,
                "stories": [], "pending": "", "round": 1,
                "created_at": datetime.now(BEIJING_TZ).isoformat(),
            }
            persist_story_game(game)
            return (f"🚀【科幻故事接龙·开局】\n发起人：{at_qq(actor)}（已自动加入）\n\n"
                    f"其他小伙伴发送「/科幻接龙 加入」报名～\n"
                    f"人齐后由发起人发送「/科幻接龙 开始」✨")

        if not active:
            return "ℹ️【当前没有进行中的接龙】\n发送「/科幻接龙 发起」可以开一局 ✨"

        if action == "join":
            if game.get("status") != "open":
                return "⏰【报名已截止】\n本局已经开始接龙了，等下一局吧 ✨"
            players = list(game.get("players") or [])
            if actor in players:
                return "😉【你已经在队伍里啦】\n等发起人开始接龙吧 ✨"
            players.append(actor)
            game["players"] = players
            persist_story_game(game)
            return (f"✅【加入成功】\n{at_qq(actor)} 已加入，当前 {len(players)} 人：\n"
                    + "　".join(at_qq(qq) for qq in players))

        if action == "begin":
            if actor != game.get("host"):
                return f"⛔【只有发起人能开始接龙】\n本局发起人是 {at_qq(game.get('host'))} 🛸"
            if game.get("status") == "playing":
                return "ℹ️【本局已经在进行中】\n发送「/科幻接龙 顺序」可以查看顺序 ✨"
            players = list(game.get("players") or [])
            if len(players) < 2:
                return "🙋【至少需要 2 位玩家】\n先让小伙伴发送「/科幻接龙 加入」报名吧 ✨"
            random.shuffle(players)
            game.update({"status": "playing", "order": players, "turn_index": 0})
            persist_story_game(game)
            lines = ["🎬【接龙开始！】随机顺序如下：", ""]
            for i, qq in enumerate(players, 1):
                lines.append(f"{i}. {at_qq(qq)}")
            lines += ["", f"请 {at_qq(players[0])} 先来，发送：/科幻接龙 <你的故事> ✨"]
            return "\n".join(lines)

        if action == "order":
            return story_order_text(game)

        if action == "finish":
            if actor != game.get("host"):
                return f"⛔【只有发起人能结束接龙】\n本局发起人是 {at_qq(game.get('host'))} 🛸"
            if game.get("status") != "playing":
                save_story_game({})
                return "🏁【本局已取消】\n还没有正式开始，已经帮你收摊啦 ✨"
            return finish_story_chain(game)

        # 其余输入视为接龙内容
        if game.get("status") != "playing":
            return "⏳【本局还没开始】\n等发起人发送「/科幻接龙 开始」之后再接龙吧 ✨"
        order = game.get("order") or []
        if not order:
            return "⚠️【顺序为空】请让发起人重新开始本局 🛸"
        idx = int(game.get("turn_index") or 0)
        current = order[idx % len(order)]
        if actor != current:
            return f"🙅【还没轮到你】\n现在是 {at_qq(current)} 的回合，请稍等 ✨"
        if game.get("pending"):
            stale = True
            try:
                started = datetime.fromisoformat(game.get("pending_at") or "")
                stale = (datetime.now(BEIJING_TZ) - started).total_seconds() > 180
            except (TypeError, ValueError):
                stale = True
            if not stale:
                return "⏳【上一条还在评析中】\n等星芒看完再发下一条吧 ✨"
            game["pending"] = ""
        if len(payload) < 4:
            return "📝【故事太短啦】\n至少写 4 个字，让故事有点展开吧 ✨"
        game["pending"] = actor
        game["pending_at"] = datetime.now(BEIJING_TZ).isoformat()
        persist_story_game(game)

    return {
        "type": "story_chain",
        "group_id": group_id,
        "user_id": actor,
        "story": payload,
        "immediate": (f"🛸【星芒评析中】\n收到 {at_qq(actor)} 的接龙，"
                      f"星芒正在认真读……\n稍等一下下 ✨"),
    }


def build_story_chain_result(group_id, user_id, story_text):
    """在后台线程执行：评分 -> 记录 -> 推进回合 -> 返回要发送的消息。"""
    with STORY_LOCK:
        game = load_story_game()
        if game.get("status") != "playing" or not (game.get("order") or []):
            return "🏁【本局已经结束了】\n这条故事没能记上，下次再来 ✨"
        history = list(game.get("stories") or [])

    score, comment = score_story(story_text, history)

    with STORY_LOCK:
        game = load_story_game()
        order = game.get("order") or []
        if game.get("status") != "playing" or not order:
            return "🏁【本局已经结束了】\n这条故事没能记上，下次再来 ✨"
        history = list(game.get("stories") or [])
        history.append({"user": user_id, "text": story_text, "score": score,
                        "comment": comment, "at": datetime.now(BEIJING_TZ).isoformat()})
        idx = (int(game.get("turn_index") or 0) + 1) % len(order)
        round_done = idx == 0
        game["stories"] = history
        game["pending"] = ""
        game["pending_at"] = ""
        game["turn_index"] = idx
        game["round"] = int(game.get("round") or 1) + (1 if round_done else 0)
        next_player = order[idx]
        persist_story_game(game)

    total = sum(int(item.get("score") or 0) for item in history if str(item.get("user")) == str(user_id))
    hidden = "　🎉 触发隐藏高分！" if score > STORY_HIDDEN_SCORE else ""
    lines = []
    if round_done:
        lines.append("🔄 一圈走完，回到队首开始新一轮！")
    lines += [
        f"📖【故事接龙·第 {len(history)} 棒】",
        f"玩家：{at_qq(user_id)}",
        f"得分：{score} 分{hidden}",
        f"点评：{comment}",
        "",
        f"➡️ 下一位：{at_qq(next_player)}",
        f"（你本局总分 {total}）",
    ]
    return "\n".join(lines)


# 用于记忆统计的指令标签，顺序即优先级
COMMAND_LABELS = (
    "帮助", "签到", "今日星芒", "碰爪", "星图", "壁纸", "海报",
    "荐书", "荐影", "动漫", "冷知识", "运势", "抽签", "提问",
    "科幻接龙", "协会介绍", "活动", "招新", "投稿", "我的画像", "忘记我",
)
MEMORY_COMMAND_ALIASES = {
    "我的画像": "profile", "我的记忆": "profile", "记忆卡": "profile", "查看记忆": "profile",
    "忘记我": "forget", "清除记忆": "forget", "删除记忆": "forget", "忘了我": "forget",
}


def detect_command_label(message):
    """把一条消息归类到一个记忆标签，用于统计「常聊什么」。"""
    text = clean_message(message)
    if text[:1] not in ("/", "／"):
        return "提问" if plain_text(text) else ""
    text = text[1:].strip()
    if not text:
        return ""
    for label in COMMAND_LABELS:
        if label in text:
            return label
    return "其它指令"


def memory_command(cmd, event):
    """记忆类指令。返回回复文本；不是记忆指令时返回 None。"""
    text = clean_message(cmd)
    if text[:1] in ("/", "／"):
        text = text[1:].strip()
    action = MEMORY_COMMAND_ALIASES.get(text)
    if not action:
        return None
    user_id = str(event.get("user_id", "") or "")
    if action == "profile":
        return memory_store.profile_text(user_id)
    return memory_store.forget_text(user_id)


def observe_mention(message, event, group_id, reply):
    """把这次 @ 记进长期记忆。任何异常都不允许影响正常回复。"""
    try:
        user_id = str(event.get("user_id", "") or "")
        if not user_id:
            return
        label = detect_command_label(message)
        # /我的画像、/忘记我 是记忆开关本身，不能反过来又写回一条记录，
        # 否则「忘记我」刚删完就被自己重建了
        if label in ("我的画像", "忘记我"):
            return
        text = plain_text(message)
        if not text:
            # 单纯 @ 一下没说话，不建上下文，免得留下没有提问的回答
            return
        memory_store.remember_message(
            user_id,
            group_id,
            text,
            nickname=memory_store.identity_from_event(event),
            command=label,
        )
        if isinstance(reply, str):
            bot_text = reply
        elif isinstance(reply, dict):
            bot_text = str(reply.get("immediate") or "")
        else:
            bot_text = ""
        if bot_text:
            memory_store.remember_reply(user_id, group_id, bot_text)
    except Exception:
        logger.exception("Failed to record memory group=%s", group_id)


def build_reply(message, event, bot_qq, group_id):
    """对外入口：生成回复，并把这一轮对话写进长期记忆。"""
    reply = _build_reply(message, event, bot_qq, group_id)
    observe_mention(message, event, group_id, reply)
    return reply


def _build_reply(message, event, bot_qq, group_id):
    msg = clean_message(message)
    cmd = command_text(msg)
    # 所有指令都要求以 / 开头；不带 / 的闲聊默认按「/提问」处理
    is_command = msg[:1] in ("/", "／")
    spoken = plain_text(msg)
    user_id = str(event.get("user_id", "") or "")

    # 管理员指令优先处理，且不受冷却与每日配额限制
    # （否则配额用尽时就无法用「刷新每日回复指令上限」自救了）
    if is_command:
        admin_match = match_admin_command(cmd)
        if admin_match:
            return handle_admin_command(admin_match, event)

    # 记忆类指令同样不吃配额、不吃冷却：隐私开关必须随时可用
    if is_command:
        memory_reply = memory_command(cmd, event)
        if memory_reply is not None:
            return memory_reply

    limited = quota_guard(event)
    if limited:
        return limited

    state = ensure_daily_state()
    lowered = cmd.lower()

    if is_command:
        story_reply = handle_story_chain(cmd, event, group_id)
        if story_reply is not None:
            return story_reply

    if not cmd or not spoken:
        # 单纯 @机器人（没写字，或只发了图片/表情）只回碰爪问候 + 最近活动 + /帮助 提示
        return bare_mention_text()
    if not is_command:
        # @机器人 直接说话但没带 / → 默认当成「/提问 问题」
        # 顺手兼容漏掉 / 的「提问 xxx」写法（只在「提问」后面跟空格时才剥离）
        question = spoken
        if question == "提问" or question.startswith("提问 "):
            question = question[len("提问"):].strip()
        return build_ai_task(question, event)
    if cmd.startswith("提问"):
        question = cmd[len("提问"):].strip()
        return build_ai_task(question, event)
    if any(word in cmd for word in ["帮助", "菜单", "功能"]):
        return help_text()
    if any(word in cmd for word in ["签到", "早安", "晚安"]):
        return checkin_text(cmd)
    if "今日星芒" in cmd:
        return today_nebula(state)
    if "碰爪" in cmd:
        return "🤝【碰爪成功】\n碰爪！星际协议达成。\n你已接入星芒触角网络，欢迎随时呼叫 🛸✨"
    if any(word in cmd for word in ["星图", "深空", "星云图"]):
        return daily_visual(state, "star")
    if "壁纸" in cmd or "科幻壁纸" in cmd:
        return daily_visual(state, "wallpaper")
    if "海报" in cmd or "科幻海报" in cmd:
        return daily_visual(state, "poster")
    if "荐书" in cmd or "推荐小说" in cmd:
        return recommend_book(user_id)
    if "荐影" in cmd or "推荐电影" in cmd:
        return recommend_movie(user_id)
    if any(word in cmd for word in ["动漫", "今日动漫", "动漫推荐", "推荐动漫"]):
        return build_anime_recommendation(user_id)
    if "冷知识" in cmd:
        fact = hourly_from_pool(
            "facts", FACTS, user_id,
            lambda item, profile: memory_store.interest_score(profile, item),
        )
        return f"🧠【科幻冷知识】\n{fact}\n\n星芒触角已帮你记下啦 ✨"
    if "运势" in cmd or "占卜" in cmd:
        return cyber_luck()
    if "抽签" in cmd:
        return draw_lot()
    if "协会介绍" in cmd or "星云科幻协会" in cmd:
        return admin_content("协会介绍") or DEFAULT_ASSOCIATION_INTRO
    if "活动" in cmd or "最近活动" in cmd:
        return admin_content("活动") or DEFAULT_ACTIVITY_TEXT
    if "招新" in cmd or "入会" in cmd:
        return admin_content("招新") or DEFAULT_RECRUIT_TEXT
    if "投稿" in cmd or "写手" in cmd:
        return admin_content("投稿") or DEFAULT_SUBMIT_TEXT
    if "42" in cmd:
        return "✨【暗号确认】\n宇宙的终极答案。但问题是什么？🛸"
    if "银河系漫游指南" in cmd:
        return "📘【暗号确认】\n毛巾已备好，别慌。✨"
    if "能量汽水" in cmd:
        return "🥤【能量补给】\n嗝——已补充赛博能量，电力满格！⚡"
    if "这不科学" in cmd:
        return "🧪【星芒吐槽】\n但很科幻。✨"
    if "星芒是谁" in cmd:
        return "🌟【星芒自我介绍】\n我是星芒，霓虹螺旋角，全息电子眼，来自赛博星系。\n爱喝能量汽水打嗝，信奉赛博精神 🥤🛸"

    return unknown_text()


# 自测或工具脚本可以设 REPLY_INTERFACE_SKIP_BOOTSTRAP=1，跳过启动期的图片下载
if os.getenv("REPLY_INTERFACE_SKIP_BOOTSTRAP", "") != "1":
    ensure_daily_state()
    start_daily_cache_worker()
