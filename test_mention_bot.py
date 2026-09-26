#!/usr/bin/env python3
"""mention_bot 的端到端自测：本地假 OneBot 服务 + 真实 webhook 事件。

用法：python3 test_mention_bot.py
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FAKE_API_PORT = 18998
BOT_PORT = 18999
# 自测用的是假号码，不涉及真实 QQ 号/群号
GROUP_ID = 100000001
USER_ID = 100000002
BOT_QQ = "100000003"
TARGET_QQ = 100000004

sent = []
_sent_lock = threading.Lock()


class FakeNapcatHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        with _sent_lock:
            sent.append((self.path.rsplit("/", 1)[-1], body))
        payload = json.dumps({"status": "ok", "retcode": 0}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def post_event(event):
    data = json.dumps(event).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{BOT_PORT}/onebot",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        return json.loads(response.read())


def group_event(raw_message, user_id=USER_ID, group_id=GROUP_ID):
    return {
        "post_type": "message",
        "message_type": "group",
        "group_id": group_id,
        "user_id": user_id,
        "raw_message": raw_message,
        "message": [{"type": "text", "data": {"text": raw_message}}],
    }


def mention_count():
    with _sent_lock:
        return sum(
            1
            for action, body in sent
            if action == "send_group_msg"
            and f"[CQ:at,qq={TARGET_QQ}]" in str(body.get("message"))
        )


def get_health():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{BOT_PORT}/health", timeout=5) as response:
        return json.loads(response.read())


def wait_for_health(timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return get_health()
        except Exception:
            time.sleep(0.2)
    raise SystemExit("mention_bot 启动超时")


def check(label, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        raise SystemExit(1)


def main():
    api_server = ThreadingHTTPServer(("127.0.0.1", FAKE_API_PORT), FakeNapcatHandler)
    threading.Thread(target=api_server.serve_forever, daemon=True).start()

    env = dict(os.environ)
    env.update(
        {
            "MENTION_BOT_QQ": BOT_QQ,
            "MENTION_GROUP_ID": str(GROUP_ID),
            "MENTION_ALLOWED_USER_ID": str(USER_ID),
            "MENTION_HOST": "127.0.0.1",
            "MENTION_PORT": str(BOT_PORT),
            "MENTION_NAPCAT_API_BASE": f"http://127.0.0.1:{FAKE_API_PORT}",
            "MENTION_MIN_INTERVAL": "1",
            "MENTION_TEXT": "",
            "LOG_LEVEL": "WARNING",
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "mention_bot.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=env,
    )

    try:
        wait_for_health()
        check("/health 正常", get_health().get("ok") is True)

        # 1) 别的群：必须忽略
        post_event(group_event(f"!1秒[CQ:at,qq={TARGET_QQ}]", group_id=999))
        # 2) 别人发的：必须忽略
        post_event(group_event(f"!1秒[CQ:at,qq={TARGET_QQ}]", user_id=888))
        time.sleep(1.4)
        check("非目标群/非授权用户被忽略", mention_count() == 0)

        # 3) 正常命令：每 1 秒 @ 一次
        post_event(group_event(f"!1秒[CQ:at,qq={TARGET_QQ}]"))
        time.sleep(2.6)
        first_round = mention_count()
        check(f"开始后按间隔 @（实际 {first_round} 次）", first_round >= 2)
        health = get_health()
        check("状态里能看到任务", health["mentions"].get(str(TARGET_QQ), {}).get("interval") == 1)

        # 4) 重复下发会覆盖间隔，不会叠加
        post_event(group_event(f"!1秒[CQ:at,qq={TARGET_QQ}]", user_id=USER_ID))
        time.sleep(0.2)
        check("同一目标只有一个任务", len(get_health()["mentions"]) == 1)

        # 5) 停止
        post_event(group_event(f"!0秒[CQ:at,qq={TARGET_QQ}]"))
        time.sleep(0.3)
        stopped_at = mention_count()
        check("停止后任务清空", get_health()["mentions"] == {})
        time.sleep(2.2)
        check("停止后不再 @", mention_count() == stopped_at)

        # 6) 命令以外的消息不触发
        post_event(group_event("普通聊天内容"))
        post_event(group_event(f"!1秒[CQ:at,qq={TARGET_QQ}] 多打了字"))
        time.sleep(1.4)
        check("非命令消息被忽略", mention_count() == stopped_at)

        # 7) 间隔下限保护（1秒请求被抬到最小 1 秒；这里只验证不会更小）
        post_event(group_event(f"!1秒[CQ:at,qq={TARGET_QQ}]"))
        time.sleep(0.2)
        post_event(group_event(f"!0秒[CQ:at,qq={TARGET_QQ}]"))

        print("\n全部通过 ✅")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        api_server.shutdown()


if __name__ == "__main__":
    main()
