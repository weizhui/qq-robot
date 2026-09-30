# 星芒语音回复接入说明

星芒现在已经预留了语音回复通道。机器人仍然先生成文字回复，然后通过可配置的 TTS 服务把文字转成音频，再用 OneBot `record` 消息发到 QQ 群。

## 1. 当前已支持的接入方式

### 本地命令模式

适合 GPT-SoVITS、CosyVoice、Bert-VITS、其他本地 TTS 脚本。

配置示例：

```bash
VOICE_REPLY_ENABLED=1
VOICE_REPLY_INCLUDE_TEXT=1
TTS_PROVIDER=command
TTS_VOICE=xingmang
TTS_FORMAT=wav
TTS_COMMAND=/opt/gpt-sovits/infer_cli --text-file {text_file} --output {output_file} --voice {voice}
```

可用占位符：

- `{text_file}`：星芒要朗读的文本文件路径
- `{output_file}`：TTS 应该生成的音频文件路径
- `{voice}`：音色名，默认 `xingmang`
- `{format}`：音频格式，默认 `wav`
- `{profile_zh}`：中文音色设定稿路径
- `{profile_en}`：英文音色设定稿路径

### HTTP 服务模式

适合 Fish Audio、MiniMax、火山引擎、你自己封装的 GPT-SoVITS/CosyVoice HTTP 服务。

配置示例：

```bash
VOICE_REPLY_ENABLED=1
VOICE_REPLY_INCLUDE_TEXT=1
TTS_PROVIDER=http
TTS_VOICE=xingmang
TTS_FORMAT=wav
TTS_HTTP_URL=http://127.0.0.1:9880/tts
TTS_HTTP_AUTHORIZATION=
```

机器人会向 `TTS_HTTP_URL` 发送 JSON：

```json
{
  "text": "要朗读的内容",
  "voice": "xingmang",
  "format": "wav",
  "profile": {
    "name": "Xingmang",
    "style": "young clear playful gentle cyber sci-fi Chinese voice"
  }
}
```

HTTP 服务可以返回：

- 直接返回音频 bytes
- JSON 中返回 `url` / `audio_url`
- JSON 中返回 `file` / `path`
- JSON 中返回 `audio_base64` / `base64`

## 2. 关键配置

```bash
VOICE_REPLY_ENABLED=0
VOICE_REPLY_INCLUDE_TEXT=1
VOICE_REPLY_MAX_CHARS=260
VOICE_REPLY_DIR=runtime_cache/voice_replies
VOICE_RECORD_FILE_PREFIX=
TTS_PROVIDER=command
TTS_VOICE=xingmang
TTS_FORMAT=wav
TTS_TIMEOUT_SECONDS=120
TTS_COMMAND=
TTS_HTTP_URL=
TTS_HTTP_AUTHORIZATION=
```

说明：

- `VOICE_REPLY_ENABLED=1` 才会启用语音回复。
- `VOICE_REPLY_INCLUDE_TEXT=1` 表示语音和文字一起发。
- `VOICE_REPLY_INCLUDE_TEXT=0` 表示优先只发语音；如果 TTS 失败，仍会回退发送文字。
- `VOICE_REPLY_MAX_CHARS` 控制每条语音最多朗读多少字，避免长消息生成太慢。
- `VOICE_RECORD_FILE_PREFIX` 默认空。如果 NapCat 需要 `file://` 前缀，可以设成 `file://`。

## 3. 音色设定稿

项目内已经准备了两份星芒音色设定：

- `xingmang_voice_profile.txt`
- `xingmang_voice_profile_en.txt`

本地命令模式下可以通过 `{profile_zh}` 和 `{profile_en}` 把它们传给你的 TTS 脚本。

## 4. 运行逻辑

1. 群友 `@星芒`。
2. 星芒生成原本的文字回复。
3. 如果语音回复开启，机器人调用 TTS 生成音频。
4. 音频生成成功：发送 QQ 语音；根据配置决定是否附带文字。
5. 音频生成失败：自动发送原文字回复，不影响机器人正常使用。

## 5. 注意事项

- 当前代码只负责“接入语音回复通道”，不内置具体音色模型。
- 如果要真正使用独特声线，需要先在 TTS 平台或本地模型中创建 `xingmang` 音色。
- QQ 语音格式取决于 NapCat/OneBot 支持情况。多数情况下可先试 `wav`，如平台要求可改成 `mp3`、`amr` 或 `silk`。
- 语音缓存会写入 `runtime_cache/voice_replies`，该目录已被 `.gitignore` 忽略。
