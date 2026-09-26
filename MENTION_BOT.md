# 定时 @ 提醒机器人（第二个机器人实例）

这份文档对应 `mention_bot.py`：一个**独立于原机器人**的新机器人，只有两个功能。
真实 QQ 号 / 群号 / 端口不写进仓库，放在仓库外的私密配置里（见下文）。

## 1. 功能

在 `MENTION_GROUP_ID` 这个群里，只有 `MENTION_ALLOWED_USER_ID` 这个 QQ 号能下命令：

| 群消息 | 行为 |
| --- | --- |
| `!5秒@某人` | 每 5 秒 @ 一次这个人，直到被停止 |
| `!30秒@某人` | 每 30 秒 @ 一次（时间可任意改） |
| `!0秒@某人` | 立刻停止 @ 这个人 |

- 命令格式也接受全角叹号、空格、`s`：`！5秒 @某人`、`! 5 秒@某人`、`!5s@某人`。
- 多条命令互不干扰，可以同时 @ 多个人；对同一个人重复下命令 = 覆盖间隔。
- 机器人的其它任何消息都不回复、不插话；其它群、其它人发的命令一律忽略。

安全限制：

- 间隔下限默认 **5 秒**（`MENTION_MIN_INTERVAL`），防止刷屏和 QQ 风控；小于下限会自动抬到下限。
- 间隔上限默认 24 小时（`MENTION_MAX_INTERVAL`）。
- 每次 @ 的内容默认是 `@某人 🔔`，可用 `MENTION_TEXT` 改，设为空则只 @ 人。
- 计时只存在内存里，进程重启后所有 @ 任务清空（需要重新下命令）。

## 2. 文件说明

| 文件 | 说明 |
| --- | --- |
| `mention_bot.py` | 主程序（只用 Python 标准库） |
| `run_mention_bot.sh` | 启动脚本，自动加载仓库外的私密配置 |
| `start_second_qq.sh` | 给第二个 QQ 号单独起一个 QQ/NapCat 实例（独立数据目录，不影响原号） |
| `mention_bot.env.example` | 配置模板 |
| `test_mention_bot.py` | 端到端自测（本地假 OneBot 服务，不碰真实 QQ） |

原来的 `main.py` / `run_bot.sh` / `reply_interface.py` **没有任何改动**，两个机器人各跑各的。

## 3. 配置

把模板复制到仓库外并填真实值：

```bash
mkdir -p ~/.config/qq-mention-bot
cp mention_bot.env.example ~/.config/qq-mention-bot/env.sh
chmod 600 ~/.config/qq-mention-bot/env.sh
$EDITOR ~/.config/qq-mention-bot/env.sh
```

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `MENTION_BOT_QQ` | 本机器人的 QQ 号（必填） | 无 |
| `MENTION_GROUP_ID` | 只监听这个群（必填） | 无 |
| `MENTION_ALLOWED_USER_ID` | 只有这个 QQ 号能下命令（必填） | 无 |
| `MENTION_HOST` / `MENTION_PORT` | Webhook 监听地址 | `127.0.0.1:18081` |
| `MENTION_NAPCAT_API_BASE` | 本机器人自己的 OneBot HTTP API | `http://127.0.0.1:3001` |
| `MENTION_NAPCAT_ACCESS_TOKEN` | OneBot 鉴权 token | 空 |
| `MENTION_MIN_INTERVAL` / `MENTION_MAX_INTERVAL` | 间隔上下限（秒） | `5` / `86400` |
| `MENTION_TEXT` | 每次 @ 附带的内容 | `🔔` |

端口必须和原机器人错开：原机器人用 Webhook `18080` + API `3000`，这里用 `18081` + `3001`。

## 4. QQ 接入（NapCat）侧

napcat 的每个账号有自己的一份 OneBot 配置：

```
Napcat/opt/QQ/resources/app/app_launcher/napcat/config/onebot11_<QQ号>.json
```

本仓库已经准备好新账号的那一份（HTTP API 端口 3001，事件上报到
`http://127.0.0.1:18081/onebot`），登录该账号后会自动读取。

**注意：** 官方 NapCatShell 启动器同一套环境同一时间只允许登录一个 QQ 号，
同时启动第二个号会提示「禁止多账户 / 无法重复登录」。所以第二个 QQ 号需要满足下面之一：

1. 用**独立的数据目录**再开一个 QQ 实例（`--user-data-dir` 指向别的目录）；
2. 复制一份 NapCat 安装目录，各自登录一个号；
3. 用 Docker 单独跑一个 NapCat 容器；
4. 部署在另一台机器上，并把上报地址指向本机 `18081`（此时需把 `MENTION_HOST` 改成 `0.0.0.0`）。

最省事的是第 1 种，仓库里已经给了脚本（它只启动新实例，不会踢掉正在运行的原号）：

```bash
./start_second_qq.sh                      # 不带参数：自动读取私密配置里的 MENTION_BOT_QQ
tail -f ~/Napcat/log/napcat_<新QQ号>.log   # 出现二维码就用手机 QQ 扫
```

登录方式：NapCat WebUI 或启动日志里的二维码，用手机 QQ 扫码；登录成功后 Webhook 才会开始推事件。
登录完成后可以确认一下：`curl --noproxy '*' http://127.0.0.1:3001/get_status`。

## 5. 启动 / 停止 / 排错

```bash
# 启动（后台会话）
screen -dmS qq_mention_bot ./run_mention_bot.sh

# 健康检查：会返回机器人 QQ、监听群、授权用户、当前正在 @ 的任务
curl --noproxy '*' http://127.0.0.1:18081/health

# 停止
screen -S qq_mention_bot -X quit
```

排错顺序：

1. `screen -ls` 看 `qq_mention_bot` 在不在；
2. `curl http://127.0.0.1:18081/health` 是否返回 `ok`；
3. 该 QQ 号的 NapCat 是否在线（`onebot11_<QQ号>.json` 里的 HTTP 服务 3001 端口是否在监听）；
4. NapCat 的上报地址是否是 `http://127.0.0.1:18081/onebot`；
5. 机器人是否真的在那个群里、命令是否由授权用户发出。

## 6. 自测

```bash
python3 test_mention_bot.py
```

会起一个本地假的 OneBot 服务和一个真的机器人进程，验证：非目标群/非授权用户被忽略、
按间隔 @、重复命令不叠加、`!0秒` 能停、非命令消息不触发。

## 7. 风险提示

- 高频 @ 会打扰群成员，也可能触发 QQ 风控，建议优先用较长间隔。
- 该功能会持续 @ 指定成员，请在群规允许、当事人知情的范围内使用。
