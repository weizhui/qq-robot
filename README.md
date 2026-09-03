# QQ Bot 技术报告

报告时间：已脱敏  
项目路径：已脱敏  
机器人账号：`<BOT_QQ>`  
当前状态：机器人主程序与 QQ 接入进程已关闭。

## 1. 项目概述

本项目是一个 QQ 群机器人。接入层负责登录 QQ、接收群消息、上报 OneBot 事件并提供发送消息接口；Python 主程序负责接收事件、过滤目标群和 @ 消息、生成回复并调用发送接口。

仓库已脱敏，不包含真实 QQ 号、群号、API Key、IP 地址、接口网址、登录链接、二维码、运行缓存、数据库或 QQ 客户端数据。

## 2. 运行架构

```text
QQ群消息
  -> QQ 接入进程
  -> OneBot 事件上报
  -> Python Webhook
  -> main.py 解析和过滤事件
  -> reply_interface.py 生成回复
  -> OneBot 发送接口
  -> QQ 群消息发送
```

## 3. 主要文件

| 文件 | 说明 |
| --- | --- |
| `main.py` | 机器人入口，提供健康检查和 OneBot Webhook，处理事件并发送回复 |
| `reply_interface.py` | 回复生成模块，包含指令、每日内容、缓存、配额和 AI 问答逻辑 |
| `run_bot.sh` | 启动脚本，从环境变量读取运行配置 |
| `.env.example` | 脱敏后的环境变量模板 |
| `requirements.txt` | 依赖说明 |
| `install_napcat.sh` | 本地安装器包装脚本，不内置下载地址 |

## 4. 环境变量

| 变量 | 说明 |
| --- | --- |
| `BOT_QQ` | 机器人 QQ 号 |
| `TARGET_GROUP_IDS` | 允许响应的群号列表，多个值用逗号分隔 |
| `HOST` | Webhook 监听主机 |
| `PORT` | Webhook 监听端口 |
| `NAPCAT_API_BASE` | OneBot HTTP API 基础地址 |
| `NAPCAT_ACCESS_TOKEN` | OneBot API 鉴权 token |
| `LOG_LEVEL` | 日志级别 |
| `DEEPSEEK_API_KEY` | AI 服务 API Key |
| `DEEPSEEK_API_URL` | AI 服务接口地址 |
| `DEEPSEEK_MODEL` | AI 模型名 |
| `JIKAN_API_BASE` | 动漫数据 API 基础地址 |
| `ANILIST_API_URL` | 动漫图片 API 地址 |

真实值只应保存在本机环境、私有部署配置或私有 `.env` 文件中，不应提交到公开仓库。

## 5. 消息处理逻辑

1. 只处理群消息事件。
2. 只响应配置中的目标群。
3. 只响应 @ 机器人或 @ 全体的消息。
4. 文本会先去掉 @ 片段，再交给回复模块。
5. 普通回复同步发送。
6. AI 问答先发送收到提示，再由后台线程发送最终回答。

## 6. 功能模块

- 帮助菜单与未知命令提示。
- 签到、运势、抽签、书籍推荐、电影推荐。
- 每日星云、星图、壁纸、海报和动漫推荐。
- AI 问答。
- 每日配额、AI 配额和冷却控制。
- 图片下载、缓存修复和旧缓存清理。

## 7. 启动与停止

启动 QQ 接入进程：

```bash
screen -dmS napcat bash -c '<QQ_CLIENT_START_COMMAND>'
```

启动 Python Bot：

```bash
screen -dmS qq_bot ./run_bot.sh
```

停止 Python Bot：

```bash
screen -S qq_bot -X quit
```

停止 QQ 接入进程：

```bash
screen -S napcat -X quit
```

查看 screen 会话：

```bash
screen -ls
```

健康检查：

```bash
curl <BOT_HEALTH_ENDPOINT>
```

QQ 接入层状态检查：

```bash
curl <ONEBOT_STATUS_ENDPOINT>
```

## 8. 故障记录

本次排查发现：Python Bot 可以启动并响应健康检查，但 QQ 接入层登录态失效，状态不是在线。接入层日志出现过被踢下线信息，重启后进入扫码登录状态。因此，群内 @ 无响应的直接原因是 QQ 接入层未保持在线，而不是 Python Webhook 进程本身不可用。

当前处置：机器人主程序和 QQ 接入进程均已关闭。

## 9. 常见排查步骤

1. 查看 screen 会话是否存在。
2. 检查 Python Bot 健康检查是否正常。
3. 检查 OneBot 接入层是否在线。
4. 检查机器人是否仍在目标群中。
5. 检查 OneBot 事件上报地址是否指向 Python Webhook。
6. 如出现扫码登录提示，完成扫码后再验证群内响应。

## 10. 安全建议

- 不要提交真实 QQ 号、群号、API Key、token、IP 地址、接口网址、二维码、日志、数据库和运行缓存。
- 不要把长期有效密钥写入启动脚本。
- 对公开仓库只提交源码、脱敏文档和配置模板。
- 发布前执行敏感信息扫描。
- QQ 接入进程依赖非官方实现，可能触发风控，应降低发送频率并做好登录态监控。

## 11. 卸载与本地清理

如需从本机移除机器人运行环境，建议先停止正在运行的会话，再清理本地运行产物。以下命令中的路径和服务名请按实际部署环境替换，不要把真实值提交到公开仓库。

停止机器人主程序：

```bash
screen -S qq_bot -X quit
```

停止 QQ 接入进程：

```bash
screen -S napcat -X quit
```

确认相关会话已退出：

```bash
screen -ls
```

可清理的本地运行产物包括：

- QQ 接入客户端目录。
- QQ 接入客户端下载或安装缓存。
- 运行缓存目录。
- 日志文件。
- 数据库文件及其 WAL/SHM 文件。
- 本地 `.env` 或其他私有配置文件。
- 登录二维码、截图、临时图片和下载图片。

公开仓库中的 `.gitignore` 已排除这些内容。清理前应确认没有仍需保留的登录态、素材或历史数据。

## 12. 开源项目致谢

本项目的实现思路和运行链路受益于多个开源项目和开放生态，特此致谢：

- NapCat.OneBot：提供 QQ 接入和 OneBot 能力。
- OneBot：提供机器人事件和动作接口规范。
- GNU Screen：用于后台会话管理。
- Python 标准库：用于 HTTP 服务、线程、JSON、时间和网络请求等基础能力。
- DeepSeek API 生态：用于可选的 AI 问答能力。
- Jikan API 生态：用于可选的动漫数据查询能力。
- AniList API 生态：用于可选的动漫图片和条目信息查询能力。
- Wikimedia Commons、NASA 等开放素材生态：为公开天文图片和来源说明提供基础。

如公开发布或二次分发，应遵守各项目和数据源的许可证、服务条款与使用限制。
