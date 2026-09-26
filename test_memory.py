#!/usr/bin/env python3
"""星芒长期记忆的自测：画像、上下文注入、遗忘、个性化推荐。

用法：python3 test_memory.py

全部跑在临时目录里，不碰真实运行缓存、不发任何网络请求。
"""

import os
import sys
import tempfile
import time
from pathlib import Path

TMP_DIR = Path(tempfile.mkdtemp(prefix="xingmang-memory-"))
os.environ["MEMORY_PATH"] = str(TMP_DIR / "memory.json")
os.environ["REPLY_INTERFACE_SKIP_BOOTSTRAP"] = "1"
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["DEEPSEEK_API_URL"] = ""
os.environ["BOT_QQ"] = "100000003"
os.environ["TARGET_GROUP_IDS"] = "800000001"

import memory_store  # noqa: E402
import reply_interface  # noqa: E402

# 把每日状态换成内存版，避免导入后去下载图片
_FAKE_STATE = {
    "date": "test",
    "command_count": 0,
    "ai_question_count": 0,
    "today_nebula": {"missing": True, "number": "?", "label": "未知信号"},
    "visuals": {},
}
reply_interface.load_state_unlocked = lambda: dict(_FAKE_STATE)
reply_interface.save_state_unlocked = lambda state: _FAKE_STATE.update(state)
reply_interface.ROTATION_PATH = TMP_DIR / "rotation_state.json"

GROUP = "800000001"


def make_event(text, user_id, nickname="小明", group_id=GROUP):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": int(group_id),
        "user_id": int(user_id),
        "raw_message": text,
        "message": [{"type": "text", "data": {"text": text}}],
        "sender": {"user_id": int(user_id), "nickname": nickname, "card": ""},
    }


FAILED = []


def check(label, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        FAILED.append(label)


def test_profile_and_context():
    print("\n== 画像与上下文 ==")
    uid = "900000001"
    memory_store.remember_message(
        uid, GROUP, "我喜欢《三体》，我是大二学生，哈哈哈哈这个设定好绝",
        nickname="阿星", command="提问",
    )
    profile = memory_store.get_profile(uid)
    check("画像已建立", profile is not None and profile["message_count"] == 1)
    check("记住昵称", profile["nickname"] == "阿星")
    check("抽出偏好", "《三体》" in profile["likes"])
    check("抽出身份", "大二学生" in profile["identities"])
    check("识别话题", "科幻小说" in profile["topics"])

    context, turns = memory_store.build_prompt_context(uid, GROUP)
    check("生成记忆补丁", "阿星" in context and "大二学生" in context)
    check("带出最近对话", len(turns) == 1 and turns[0]["role"] == "user")

    messages = reply_interface.build_deepseek_messages("那黑暗森林呢？", uid, GROUP)
    check("system 里带人设", "星芒" in messages[0]["content"])
    check("system 里带记忆", "大二学生" in messages[0]["content"])
    check("保留对话历史", len(messages) == 3 and messages[1]["role"] == "user")
    check("最后一条是本次提问", messages[-1]["content"] == "那黑暗森林呢？")

    # 本轮提问已写进记忆时，不能重复塞进请求
    memory_store.remember_message(uid, GROUP, "那黑暗森林呢？", command="提问")
    messages = reply_interface.build_deepseek_messages("那黑暗森林呢？", uid, GROUP)
    check("去掉重复的本轮提问",
          messages[-1]["content"] == "那黑暗森林呢？"
          and messages[-2]["content"] != "那黑暗森林呢？")


def test_tone_adapts():
    print("\n== 语气习惯 ==")
    uid = "900000002"
    for text in ("好耶~", "哈哈哈太可爱啦", "嘻嘻这个我喜欢呀", "嘿嘿嘿"):
        memory_store.remember_message(uid, GROUP, text, nickname="软软")
    profile = memory_store.get_profile(uid)
    hint = memory_store.style_hint(profile)
    check("样本够了才给语气建议", bool(hint))
    check("识别出爱开玩笑", "接梗" in hint)
    check("识别出短句", "两三句" in hint)

    quiet = "900000003"
    for _ in range(3):
        memory_store.remember_message(
            quiet, GROUP,
            "请帮我分析一下这个方案的可行性与潜在风险，我需要一份结论明确的评估结果。",
        )
    quiet_hint = memory_store.style_hint(memory_store.get_profile(quiet))
    check("冷静型用户收着点表情", "别堆表情" in quiet_hint)


def test_reply_integration():
    print("\n== 接入 build_reply ==")
    uid = "900000004"
    event = make_event("/帮助", uid, nickname="小测")

    reply = reply_interface.build_reply("/帮助", event, "100000003", GROUP)
    check("帮助里能看到记忆指令", "我的画像" in reply and "忘记我" in reply)

    event = make_event("星芒你怎么看星际穿越", uid + "1", nickname="小测")
    reply = reply_interface.build_reply("星芒你怎么看星际穿越", event, "100000003", GROUP)
    check("闲聊走 AI 提问", isinstance(reply, dict) and reply["type"] == "deepseek_question")
    check("带回提问者身份", reply["user_id"] == uid + "1" and reply["group_id"] == GROUP)
    profile = memory_store.get_profile(uid + "1")
    check("提问已进记忆", profile is not None and profile["message_count"] == 1)
    check("识别为提问", "提问" in profile["command_counts"])

    # AI 回答写回记忆，下一轮才能接上文（这里替换掉真实接口调用）
    original_call = reply_interface.call_deepseek
    reply_interface.call_deepseek = lambda question, user_id=None, group_id=None: (
        "🤖【星芒回答】\n第一问的答案\n\n✨ 来自 DeepSeek · 星芒整理完成 🛸"
    )
    try:
        reply_interface.build_ai_answer("第一问", user_id=uid + "1", group_id=GROUP)
    finally:
        reply_interface.call_deepseek = original_call
    turns = memory_store.recent_turns(uid + "1", GROUP)
    check("回答写回上下文", len(turns) == 2 and turns[-1]["role"] == "assistant")
    check("回灌的记忆不含群发包装",
          "第一问的答案" in turns[-1]["content"] and "来自 DeepSeek" not in turns[-1]["content"])

    quota_before = _FAKE_STATE["command_count"]
    profile_reply = reply_interface.build_reply(
        "/我的画像", make_event("/我的画像", uid + "1", nickname="小测"), "100000003", GROUP
    )
    check("画像指令可用", "星芒记忆卡" in profile_reply and "小测" in profile_reply)

    forget_reply = reply_interface.build_reply(
        "/忘记我", make_event("/忘记我", uid + "1", nickname="小测"), "100000003", GROUP
    )
    check("遗忘指令可用", "记忆已清空" in forget_reply)
    check("遗忘后画像消失", memory_store.get_profile(uid + "1") is None)
    check("记忆指令不占每日配额", _FAKE_STATE["command_count"] == quota_before)

    again = reply_interface.build_reply(
        "/我的画像", make_event("/我的画像", uid + "1"), "100000003", GROUP
    )
    check("清空后是新用户", "还没攒到" in again)


def test_personalized_recommend():
    print("\n== 个性化推荐 ==")
    uid = "900000005"
    for _ in range(3):
        memory_store.remember_message(
            uid, GROUP, "我最近在看刘慈欣的科幻小说，三体太好看了",
            nickname="书虫", command="荐书",
        )

    def book_score(item, profile):
        return memory_store.interest_score(profile, " ".join(str(part) for part in item))

    profile = memory_store.get_profile(uid)
    check("话题权重累计到上限", min(profile["topics"]["科幻小说"], 5) == 5)

    picked = reply_interface.hourly_from_pool("books", reply_interface.BOOKS, uid, book_score)
    check(f"按口味挑书（{picked[0]}）", picked[1] in ("刘慈欣", "艾萨克·阿西莫夫"))
    again = reply_interface.hourly_from_pool("books", reply_interface.BOOKS, uid, book_score)
    check("同一小时结果稳定", again == picked)

    cold = "900000006"
    memory_store.remember_message(cold, GROUP, "在吗", nickname="路人")
    check("没有画像信号时不个性化",
          reply_interface.personalized_pick("books", reply_interface.BOOKS, cold, book_score) is None)

    plain = reply_interface.hourly_from_pool("books", reply_interface.BOOKS)
    check("不传用户时仍走全局轮换", plain in reply_interface.BOOKS)


def test_helpers():
    print("\n== 边角逻辑 ==")
    check("识别指令标签", reply_interface.detect_command_label("/荐书") == "荐书")
    check("识别闲聊标签", reply_interface.detect_command_label("你好呀") == "提问")
    check("指令名为空时不崩", reply_interface.detect_command_label("/") == "")
    check("事件里取昵称",
          memory_store.identity_from_event(make_event("hi", "1", nickname="夜猫")) == "夜猫")

    profile = memory_store.get_profile("900000001")
    check("兴趣打分对味", memory_store.interest_score(profile, "《三体》 刘慈欣 硬科幻") > 0)
    check("兴趣打分不对味", memory_store.interest_score(profile, "《海伯利安》 丹·西蒙斯") == 0)

    stats = memory_store.stats_text()
    check("管理员概况可用", "星芒记忆概况" in stats and "位群友" in stats)

    # 记忆文件要能反复读取，说明落盘内容合法
    import json
    data = json.loads(Path(os.environ["MEMORY_PATH"]).read_text(encoding="utf-8"))
    check("记忆文件是合法 JSON", isinstance(data.get("users"), dict))

    started = time.time()
    memory_store.remember_message(123456789, GROUP, "压测一条", command="提问")
    check("写入够快", time.time() - started < 1.0)

    # 记忆文件被写坏时不能把机器人搞崩
    Path(os.environ["MEMORY_PATH"]).write_text("{坏掉的 json", encoding="utf-8")
    check("坏文件按空记忆处理", memory_store.get_profile("900000001") is None)
    memory_store.remember_message("900000007", GROUP, "灾后重建", command="提问")
    check("坏文件能自愈", memory_store.get_profile("900000007") is not None)


def test_main_wiring():
    print("\n== main.py 事件接线 ==")
    import main

    captured = {}
    original = (main.build_reply, main.send_ai_answer, main.send_group_reply)
    main.build_reply = lambda **kwargs: {
        "type": "deepseek_question",
        "question": "记忆能接上吗",
        "user_id": "424242",
        "group_id": GROUP,
        "immediate": "",
    }
    main.send_ai_answer = lambda group_id, question, user_id=None: captured.update(
        {"group_id": group_id, "user_id": user_id, "question": question}
    )
    main.send_group_reply = lambda group_id, message: captured.update({"sent": message})
    try:
        main.handle_event({
            "post_type": "message",
            "message_type": "group",
            "group_id": int(GROUP),
            "user_id": 424242,
            "raw_message": "[CQ:at,qq=100000003] 记忆能接上吗",
        })
        time.sleep(0.4)
    finally:
        main.build_reply, main.send_ai_answer, main.send_group_reply = original

    check("后台线程拿到提问者 user_id", captured.get("user_id") == "424242")
    check("后台线程拿到群号", captured.get("group_id") == int(GROUP))

    captured.clear()
    original_answer = main.build_ai_answer
    main.build_ai_answer = lambda question, user_id=None, group_id=None: (
        captured.update({"user_id": user_id, "group_id": group_id}) or "回答"
    )
    main.send_group_reply = lambda group_id, message: captured.update({"sent": message})
    try:
        main.send_ai_answer(int(GROUP), "问题", user_id="424242")
    finally:
        main.build_ai_answer = original_answer
        main.send_group_reply = original[2]
    check("send_ai_answer 透传记忆身份", captured.get("user_id") == "424242")
    check("send_ai_answer 正常发消息", captured.get("sent") == "回答")


def main():
    test_profile_and_context()
    test_tone_adapts()
    test_reply_integration()
    test_personalized_recommend()
    test_main_wiring()
    test_helpers()
    if FAILED:
        print(f"\n{len(FAILED)} 项失败 ❌")
        for label in FAILED:
            print(f"  - {label}")
        return 1
    print("\n全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
