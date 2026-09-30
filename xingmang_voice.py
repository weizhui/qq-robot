#!/usr/bin/env python3
"""Optional voice reply support for Xingmang.

The bot keeps text replies as the source of truth. This module turns a reply
into an audio file or URL through a configurable TTS provider, then main.py can
send it as a OneBot record segment.
"""

import base64
import glob
import json
import logging
import os
import random
import re
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


logger = logging.getLogger("qq-bot.voice")

BASE_DIR = Path(__file__).resolve().parent
VOICE_REPLY_ENABLED = os.getenv("VOICE_REPLY_ENABLED", "0").strip().lower() in {
    "1", "true", "yes", "on"
}
VOICE_REPLY_INCLUDE_TEXT = os.getenv("VOICE_REPLY_INCLUDE_TEXT", "1").strip().lower() in {
    "1", "true", "yes", "on"
}
VOICE_REPLY_ASYNC = os.getenv("VOICE_REPLY_ASYNC", "1").strip().lower() in {
    "1", "true", "yes", "on"
}
VOICE_REPLY_PROBABILITY = float(os.getenv("VOICE_REPLY_PROBABILITY", "1"))
VOICE_REPLY_PROBABILITY = max(0.0, min(1.0, VOICE_REPLY_PROBABILITY))
VOICE_REPLY_MAX_CHARS = int(os.getenv("VOICE_REPLY_MAX_CHARS", "260"))
VOICE_REPLY_DIR = Path(os.getenv("VOICE_REPLY_DIR", str(BASE_DIR / "runtime_cache" / "voice_replies")))
VOICE_RECORD_FILE_PREFIX = os.getenv("VOICE_RECORD_FILE_PREFIX", "").strip()

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "command").strip().lower()
TTS_COMMAND = os.getenv("TTS_COMMAND", "").strip()
TTS_TIMEOUT_SECONDS = int(os.getenv("TTS_TIMEOUT_SECONDS", "120"))
TTS_VOICE = os.getenv("TTS_VOICE", "xingmang").strip()
TTS_FORMAT = os.getenv("TTS_FORMAT", "wav").strip().lstrip(".") or "wav"

TTS_HTTP_URL = os.getenv("TTS_HTTP_URL", "").strip()
TTS_HTTP_AUTHORIZATION = os.getenv("TTS_HTTP_AUTHORIZATION", "").strip()

VOLCENGINE_AUDIO_API_KEY = (
    os.getenv("VOLCENGINE_AUDIO_API_KEY")
    or os.getenv("VOLCENGINE_ARK_API_KEY")
    or os.getenv("VOLCENGINE_TTS_API_KEY")
    or ""
).strip()
VOLCENGINE_AUDIO_URL = os.getenv(
    "VOLCENGINE_AUDIO_URL",
    "https://openspeech.bytedance.com/api/v3/tts/create",
).strip()
VOLCENGINE_AUDIO_MODEL = os.getenv("VOLCENGINE_AUDIO_MODEL", "seed-audio-1.0").strip()
VOLCENGINE_AUDIO_SAMPLE_RATE = int(os.getenv("VOLCENGINE_AUDIO_SAMPLE_RATE", "48000"))
VOLCENGINE_AUDIO_SPEECH_RATE = int(os.getenv("VOLCENGINE_AUDIO_SPEECH_RATE", "4"))
VOLCENGINE_AUDIO_PITCH_RATE = int(os.getenv("VOLCENGINE_AUDIO_PITCH_RATE", "2"))
VOLCENGINE_AUDIO_LOUDNESS_RATE = int(os.getenv("VOLCENGINE_AUDIO_LOUDNESS_RATE", "0"))
VOLCENGINE_AUDIO_PROMPT_TEMPLATE = os.getenv(
    "VOLCENGINE_AUDIO_PROMPT_TEMPLATE",
    "年轻清亮、偏可爱、软乎带笑意的中文少女/少年感赛博机器人星芒，"
    "用轻快温柔、俏皮但不幼稚的语气说道：{text}",
)
VOLCENGINE_AUDIO_SPEAKER = (
    os.getenv("VOLCENGINE_AUDIO_SPEAKER")
    or os.getenv("VOLCENGINE_AUDIO_VOICE_ID")
    or os.getenv("VOLCENGINE_TTS_VOICE_TYPE")
    or ""
).strip()
VOLCENGINE_AUDIO_REFERENCE_FILES = os.getenv("VOLCENGINE_AUDIO_REFERENCE_FILES", "").strip()
VOLCENGINE_AUDIO_REFERENCE_DIR = os.getenv(
    "VOLCENGINE_AUDIO_REFERENCE_DIR",
    str(BASE_DIR / "Tone_reference" / "normalized"),
).strip()
VOLCENGINE_AUDIO_REFERENCE_LIMIT = int(os.getenv("VOLCENGINE_AUDIO_REFERENCE_LIMIT", "3"))

VOICE_PROFILE_ZH = BASE_DIR / "xingmang_voice_profile.txt"
VOICE_PROFILE_EN = BASE_DIR / "xingmang_voice_profile_en.txt"

_CQ_RE = re.compile(r"\[CQ:[^\]]+\]")
_MARKDOWN_RE = re.compile(r"[*_`>#~-]+")
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def enabled():
    return VOICE_REPLY_ENABLED


def should_reply_with_voice():
    return VOICE_REPLY_ENABLED and random.random() < VOICE_REPLY_PROBABILITY


def include_text():
    return VOICE_REPLY_INCLUDE_TEXT


def async_enabled():
    return VOICE_REPLY_ASYNC


def clean_text_for_voice(message):
    """Convert a rich group reply into concise speakable text."""
    text = str(message or "")
    text = _CQ_RE.sub("", text)
    text = text.replace("【", " ").replace("】", " ")
    text = _MARKDOWN_RE.sub("", text)
    text = re.sub(r"https?://\S+", "链接", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    if len(text) <= VOICE_REPLY_MAX_CHARS:
        return text
    return text[:VOICE_REPLY_MAX_CHARS].rstrip() + "。"


def onebot_record_file(audio_ref):
    audio_ref = str(audio_ref or "").strip()
    if not audio_ref:
        return ""
    if audio_ref.startswith(("http://", "https://", "file://")):
        return audio_ref
    return f"{VOICE_RECORD_FILE_PREFIX}{audio_ref}"


def synthesize_reply(message):
    """Return an audio file path or URL for a bot reply. Return empty on failure."""
    if not VOICE_REPLY_ENABLED:
        return ""
    text = clean_text_for_voice(message)
    if not text:
        return ""
    try:
        if TTS_PROVIDER == "http":
            return _synthesize_http(text)
        if TTS_PROVIDER in {"volcengine_seed_audio", "seed_audio", "doubao_seed_audio"}:
            return _synthesize_volcengine_seed_audio(text)
        return _synthesize_command(text)
    except Exception:
        logger.exception("Voice synthesis failed")
        return ""


def _new_output_path():
    VOICE_REPLY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    millis = int((time.time() % 1) * 1000)
    return VOICE_REPLY_DIR / f"xingmang-{stamp}-{millis:03d}.{TTS_FORMAT}"


def _write_text_input(text, output_path):
    text_path = output_path.with_suffix(".txt")
    text_path.write_text(text, encoding="utf-8")
    return text_path


def _synthesize_command(text):
    if not TTS_COMMAND:
        logger.warning("VOICE_REPLY_ENABLED=1 but TTS_COMMAND is empty")
        return ""

    output_path = _new_output_path()
    text_path = _write_text_input(text, output_path)
    replacements = {
        "text_file": str(text_path),
        "output_file": str(output_path),
        "voice": TTS_VOICE,
        "format": TTS_FORMAT,
        "profile_zh": str(VOICE_PROFILE_ZH),
        "profile_en": str(VOICE_PROFILE_EN),
    }
    command = TTS_COMMAND.format(**replacements)
    args = shlex.split(command)
    logger.info("Running TTS command: %s", args[:2])
    subprocess.run(args, check=True, timeout=TTS_TIMEOUT_SECONDS)

    if not output_path.exists() or output_path.stat().st_size <= 0:
        logger.warning("TTS command did not create audio output: %s", output_path)
        return ""
    return str(output_path)


def _synthesize_http(text):
    if not TTS_HTTP_URL:
        logger.warning("VOICE_REPLY_ENABLED=1 but TTS_HTTP_URL is empty")
        return ""

    payload = {
        "text": text,
        "voice": TTS_VOICE,
        "format": TTS_FORMAT,
        "profile": {
            "name": "Xingmang",
            "style": "young clear cute playful sweet gentle cyber sci-fi Chinese voice, soft smiling tone",
        },
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if TTS_HTTP_AUTHORIZATION:
        headers["Authorization"] = TTS_HTTP_AUTHORIZATION

    request = urllib.request.Request(TTS_HTTP_URL, data=body, headers=headers, method="POST")
    with _LOCAL_OPENER.open(request, timeout=TTS_TIMEOUT_SECONDS) as response:
        content_type = response.headers.get("Content-Type", "")
        data = response.read()

    if "application/json" in content_type:
        return _audio_from_json_response(data)

    output_path = _new_output_path()
    output_path.write_bytes(data)
    if output_path.stat().st_size <= 0:
        return ""
    return str(output_path)


def _synthesize_volcengine_seed_audio(text):
    if not VOLCENGINE_AUDIO_API_KEY:
        logger.warning("VOICE_REPLY_ENABLED=1 but VOLCENGINE_AUDIO_API_KEY is empty")
        return ""

    references = _volcengine_audio_references()
    prompt = VOLCENGINE_AUDIO_PROMPT_TEMPLATE.format(text=text)
    if references and any("audio_data" in item for item in references):
        tags = "、".join(f"@Audio{i}" for i in range(1, len(references) + 1))
        prompt = f"参考 {tags} 的音色特征，保持星芒清亮可爱的声线。" + prompt

    payload = {
        "model": VOLCENGINE_AUDIO_MODEL,
        "text_prompt": prompt,
        "audio_config": {
            "format": TTS_FORMAT,
            "sample_rate": VOLCENGINE_AUDIO_SAMPLE_RATE,
            "pitch_rate": VOLCENGINE_AUDIO_PITCH_RATE,
            "speech_rate": VOLCENGINE_AUDIO_SPEECH_RATE,
            "loudness_rate": VOLCENGINE_AUDIO_LOUDNESS_RATE,
        },
        "watermark": {},
    }
    if references:
        payload["references"] = references
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": VOLCENGINE_AUDIO_API_KEY,
    }
    request = urllib.request.Request(
        VOLCENGINE_AUDIO_URL, data=body, headers=headers, method="POST"
    )
    with _LOCAL_OPENER.open(request, timeout=TTS_TIMEOUT_SECONDS) as response:
        content_type = response.headers.get("Content-Type", "")
        data = response.read()

    if "application/json" in content_type or data[:1] in (b"{", b"["):
        return _audio_from_json_response(data)

    output_path = _new_output_path()
    output_path.write_bytes(data)
    return str(output_path) if output_path.stat().st_size > 0 else ""


def _volcengine_audio_references():
    files = []
    if VOLCENGINE_AUDIO_REFERENCE_FILES:
        files = [part.strip() for part in VOLCENGINE_AUDIO_REFERENCE_FILES.split(",") if part.strip()]
    elif VOLCENGINE_AUDIO_REFERENCE_DIR:
        patterns = ("*.wav", "*.mp3", "*.pcm", "*.ogg", "*.opus")
        for pattern in patterns:
            files.extend(sorted(glob.glob(str(Path(VOLCENGINE_AUDIO_REFERENCE_DIR) / pattern))))

    refs = []
    for file_path in files[:max(0, VOLCENGINE_AUDIO_REFERENCE_LIMIT)]:
        try:
            data = Path(file_path).read_bytes()
        except OSError:
            logger.warning("Cannot read voice reference audio: %s", file_path)
            continue
        if not data or len(data) > 10 * 1024 * 1024:
            logger.warning("Skipping invalid/oversized voice reference audio: %s", file_path)
            continue
        refs.append({"audio_data": base64.b64encode(data).decode("ascii")})

    if refs:
        return refs
    if VOLCENGINE_AUDIO_SPEAKER:
        return [{"speaker": VOLCENGINE_AUDIO_SPEAKER}]
    return []


def _audio_from_json_response(data):
    payload = json.loads(data.decode("utf-8", errors="replace"))
    found = _find_audio_value(payload)
    if not found:
        logger.warning("TTS JSON response has no audio field: %s", str(payload)[:500])
        return ""

    kind, value = found
    if kind == "url":
        return value

    encoded = value
    if "," in encoded and encoded.split(",", 1)[0].startswith("data:"):
        encoded = encoded.split(",", 1)[1]
    audio = base64.b64decode(encoded)
    output_path = _new_output_path()
    output_path.write_bytes(audio)
    return str(output_path) if output_path.stat().st_size > 0 else ""


def _find_audio_value(payload):
    if isinstance(payload, dict):
        for key in ("url", "audio_url", "file", "path"):
            value = str(payload.get(key) or "").strip()
            if value:
                return "url", value
        for key in ("audio", "audio_base64", "base64", "data"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return "base64", value.strip()
        for value in payload.values():
            found = _find_audio_value(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_audio_value(item)
            if found:
                return found
    return None
