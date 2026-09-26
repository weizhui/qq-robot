# QQ Robot

一个基于 OneBot 事件上报的 QQ 群机器人项目。仓库内只保留源码、脱敏配置模板、启动脚本和测试脚本；真实 QQ 号、群号、Token、API Key、登录态、缓存、数据库和聊天记忆不应提交到 GitHub。

## 功能概览

- 群聊 @ 机器人后自动回复。
- 签到、运势、抽签、帮助菜单、书籍推荐、电影推荐。
- 每日星芒、星图、壁纸、海报和动漫推荐。
- DeepSeek AI 问答，可结合用户画像和同群最近对话生成回答。
- 长期记忆：记录用户偏好、常用指令、语气样本和最近对话上下文。
- 记忆自助指令：`/我的画像` 查看画像，`/忘记我` 清空自己的记忆。
- 定时整点提醒和每日动漫推荐推送。
- 可选的第二机器人：按命令定时 @ 指定成员，详见 `MENTION_BOT.md`。

## 项目结构

| 文件 | 说明 |
| --- | --- |
| `main.py` | 主机器人入口，接收 OneBot Webhook、过滤群消息和 @ 消息、调用回复逻辑 |
| `reply_interface.py` | 回复生成、AI 问答、每日内容、配额、冷却、图片缓存等核心逻辑 |
| `memory_store.py` | 长期记忆读写与用户画像维护 |
| `run_bot.sh` | 主机器人启动脚本，自动加载仓库外私有配置 |
| `.env.example` | 主机器人配置模板，不包含真实密钥 |
| `install.sh` | 本地一键准备脚本 |
| `install_napcat.sh` | NapCat 安装器包装脚本，仓库不内置安装器本体 |
| `MEMORY.md` | 长期记忆功能说明 |
| `mention_bot.py` | 可选的定时 @ 提醒机器人 |
| `run_mention_bot.sh` | 定时 @ 机器人启动脚本 |
| `mention_bot.env.example` | 定时 @ 机器人配置模板 |
| `MENTION_BOT.md` | 定时 @ 机器人说明 |
| `test_memory.py` | 长期记忆自测 |
| `test_mention_bot.py` | 定时 @ 机器人端到端自测 |

## 运行架构

```text
QQ群消息
  -> QQ 接入层（例如 NapCat）
  -> OneBot 事件上报
  -> main.py Webhook
  -> reply_interface.py / memory_store.py
  -> OneBot HTTP API
  -> QQ 群消息发送
```

## 环境要求

- Linux 服务器或桌面环境。
- Python 3.10+，建议 Python 3.11+。
- `screen`：用于后台运行机器人。
- `curl`：用于健康检查。
- QQ OneBot 接入层，例如 NapCat。
- 可选：DeepSeek API Key，用于 AI 问答和接龙评分。

项目主功能只依赖 Python 标准库，`requirements.txt` 目前没有第三方 Python 包。

## 一键准备

```bash
chmod +x install.sh
./install.sh
```

脚本会做这些事：

- 检查 `python3`、`screen`、`curl` 是否存在。
- 创建 `runtime_cache/`。
- 复制 `.env.example` 到 `~/.config/qq-bot/env.sh`，并设置权限为 `600`。
- 如存在 `mention_bot.env.example`，复制到 `~/.config/qq-mention-bot/env.sh`。
- 提示你下一步需要填写真实配置。

如果系统缺少工具，可按发行版安装：

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install -y python3 screen curl
```

## 配置主机器人

编辑仓库外的私有配置：

```bash
chmod 600 ~/.config/qq-bot/env.sh
$EDITOR ~/.config/qq-bot/env.sh
```

主配置变量：

| 变量 | 说明 |
| --- | --- |
| `BOT_QQ` | 机器人 QQ 号 |
| `TARGET_GROUP_IDS` | 允许响应的群号列表，多个值用英文逗号分隔 |
| `HOST` | Webhook 监听地址，本机使用可填 `127.0.0.1` 或 `localhost` |
| `PORT` | Webhook 监听端口 |
| `NAPCAT_API_BASE` | OneBot HTTP API 地址，例如本机某个端口 |
| `NAPCAT_ACCESS_TOKEN` | OneBot API 鉴权 Token，可为空，但生产环境建议设置 |
| `LOG_LEVEL` | 日志级别，常用 `INFO` 或 `DEBUG` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key，可为空；为空时 AI 功能不可用 |
| `DEEPSEEK_API_URL` | DeepSeek Chat Completions 接口地址 |
| `DEEPSEEK_MODEL` | 模型名，默认 `deepseek-chat` |
| `JIKAN_API_BASE` | Jikan API 地址，可用于动漫数据 |
| `ANILIST_API_URL` | AniList GraphQL 地址，可用于动漫图片和条目信息 |
| `MEMORY_ENABLED` | 是否启用长期记忆，`1` 开启，`0` 关闭 |
| `MEMORY_PATH` | 记忆文件路径，默认 `runtime_cache/memory.json` |
| `MEMORY_MAX_USERS` | 最多保留的用户画像数量 |
| `MEMORY_HISTORY_TURNS` | 每个群保留的最近对话轮数 |
| `MEMORY_MIN_SAMPLES` | 至少多少条发言后启用语气画像 |

真实配置只放在 `~/.config/qq-bot/env.sh`、服务器环境变量或私有部署平台里，不要写进仓库。

## 配置 OneBot / NapCat

你需要让 QQ 接入层完成两件事：

- HTTP API 可被机器人访问，并与 `NAPCAT_API_BASE` 一致。
- 事件上报地址指向机器人 Webhook，例如 `http://127.0.0.1:8080/onebot`。

本仓库不打包 NapCat 安装器本体。如果你已经有可信的 `napcat-installer.sh`，可放到项目根目录后运行：

```bash
./install_napcat.sh
```

登录 QQ 后，用接入层状态接口确认账号在线，再启动 Python 机器人。

## 启动与停止

前台启动，便于首次调试：

```bash
./run_bot.sh
```

后台启动：

```bash
screen -dmS qq_bot ./run_bot.sh
```

健康检查：

```bash
curl --noproxy '*' http://127.0.0.1:8080/health
```

停止：

```bash
screen -S qq_bot -X quit
```

查看后台会话：

```bash
screen -ls
```

## 测试

```bash
python3 test_memory.py
python3 test_mention_bot.py
```

`test_mention_bot.py` 会启动本地假的 OneBot 服务，不会碰真实 QQ。

## 常见报错与解决

### `提示：未找到 ~/.config/qq-bot/env.sh`

还没有准备私有配置。运行：

```bash
./install.sh
$EDITOR ~/.config/qq-bot/env.sh
```

### `Cannot start server on ... Address already in use`

端口被占用。解决方式：

- 改 `~/.config/qq-bot/env.sh` 里的 `PORT`。
- 或停止占用端口的旧进程。
- 如果使用 `screen`，先执行 `screen -ls` 检查是否已经启动过机器人。

### 健康检查正常，但群里 @ 没反应

优先检查 QQ 接入层：

- NapCat 或其它 OneBot 接入层是否在线。
- 事件上报地址是否指向 `http://<HOST>:<PORT>/onebot`。
- 机器人 QQ 是否还在目标群。
- `TARGET_GROUP_IDS` 是否包含这个群。
- 群消息里是否真的 @ 了机器人或 @ 全体。

### `Cannot reach NapCat API`

机器人收到了事件，但发不出消息。常见原因：

- `NAPCAT_API_BASE` 端口写错。
- OneBot HTTP API 没启动。
- `NAPCAT_ACCESS_TOKEN` 与 OneBot 配置不一致。
- 本机代理影响了访问。`run_bot.sh` 已默认设置 `NO_PROXY=127.0.0.1,localhost`，如果仍失败，检查系统代理环境变量。

### AI 问答提示不可用

检查：

- `DEEPSEEK_API_KEY` 是否填写。
- `DEEPSEEK_API_URL` 是否填写。
- 服务器是否能访问外部 API。
- API Key 是否还有额度或权限。

### 图片发送失败或没有图片

检查：

- 服务器是否能访问对应图片来源。
- 接入层是否允许发送图片 CQ 码。
- `runtime_cache/` 是否可写。
- 图片大小是否超过接入层限制。

### 长期记忆没有生效

检查：

- `MEMORY_ENABLED=1`。
- `MEMORY_PATH` 所在目录可写。
- 用户样本数是否达到 `MEMORY_MIN_SAMPLES`。
- 不要把 `runtime_cache/memory.json` 上传到仓库，它包含聊天文本和用户画像。

### 定时 @ 机器人端口冲突

主机器人和定时 @ 机器人需要使用不同端口。默认主机器人可用 `8080`，定时 @ 机器人文档中示例使用 `18081` 和独立 OneBot API 端口。详见 `MENTION_BOT.md`。

## 安全与隐私

不要提交这些内容：

- `.env`、`env.sh`、真实 QQ 号、真实群号、API Key、Token、密码。
- NapCat 登录态、二维码、截图、客户端数据目录。
- `runtime_cache/`、`memory.json`、日志、数据库文件。
- 下载的图片、临时素材和其它运行产物。

发布前建议执行：

```bash
git status --short
git ls-files
rg -n "(api[_-]?key|access[_-]?token|secret|password|Bearer|sk-)" .
```

仓库的 `.gitignore` 已默认排除常见敏感和运行产物，但最终提交前仍应人工确认。

## 开源生态致谢

- NapCat.OneBot：QQ 接入与 OneBot 能力。
- OneBot：机器人事件和动作接口规范。
- GNU Screen：后台会话管理。
- DeepSeek API 生态：可选 AI 问答能力。
- Jikan / AniList API 生态：可选动漫数据能力。
- Wikimedia Commons、NASA 等开放素材生态：公开图片和知识来源。

使用或二次分发时，请遵守相关项目、数据源和平台的许可证与服务条款。
