from __future__ import annotations

import asyncio
import json
import re
from typing import AsyncGenerator, Dict, List

import httpx

from config import (
    ENABLE_DEV_FALLBACK,
    ENABLE_OLLAMA,
    OLLAMA_CHAT_URL,
    OLLAMA_FIRST_TOKEN_TIMEOUT_SECONDS,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_NUM_CTX,
    OLLAMA_TAGS_URL,
    OLLAMA_TIMEOUT_SECONDS,
)
from model_manager import get_active_model_name

from .model_adapters import adapt_messages_for_model, build_model_options


class LLMEngineError(RuntimeError):
    pass


def user_visible_llm_failure_message(detail: str) -> str:
    active_model = get_active_model_name()
    return (
        "モデルの応答をうまく受け取れませんでした。少し待ってから、もう一度送ってください。\n"
        f"現在のモデル: {active_model}\n"
        f"詳細: {detail}"
    )


async def generate_stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    short_reply = _short_reply(messages)
    if short_reply is not None:
        yield short_reply
        return

    if ENABLE_OLLAMA:
        try:
            async for chunk in _generate_from_ollama(messages):
                yield chunk
            return
        except Exception as exc:  # noqa: BLE001
            raise LLMEngineError(f"Ollama request failed: {exc}") from exc

    if ENABLE_DEV_FALLBACK and not ENABLE_OLLAMA:
        async for chunk in _generate_fallback(messages):
            yield chunk
        return

    raise LLMEngineError("No LLM backend is available.")


async def ollama_healthcheck() -> Dict[str, str]:
    if not ENABLE_OLLAMA:
        return {"status": "disabled", "detail": "OLLAMA disabled by config"}

    active_model = get_active_model_name()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(OLLAMA_TAGS_URL)
        response.raise_for_status()
        payload = response.json()
    names = {model.get("name", "") for model in payload.get("models", [])}
    if active_model in names:
        return {"status": "ok", "detail": f"model {active_model} available"}
    return {"status": "degraded", "detail": f"model {active_model} not found"}


async def ollama_installed_models() -> List[str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(OLLAMA_TAGS_URL)
        response.raise_for_status()
        payload = response.json()
    return [model.get("name", "") for model in payload.get("models", []) if model.get("name")]


async def _generate_from_ollama(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    active_model = get_active_model_name()
    adapted_messages = adapt_messages_for_model(active_model, messages)

    if active_model == "gemma3:1b":
        text = await _generate_buffered_from_ollama(active_model, adapted_messages)
        if _looks_like_failed_response(text):
            text = _fallback_conversation(messages)
        if _looks_like_failed_response(text):
            raise LLMEngineError("Gemma response failed quality guard")
        for chunk in _chunk_text(normalize_yachiyo_output(text)):
            yield chunk
        return

    payload = {
        "model": active_model,
        "messages": adapted_messages,
        "stream": True,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": _ollama_options(active_model),
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
        async with client.stream("POST", OLLAMA_CHAT_URL, json=payload) as response:
            response.raise_for_status()
            line_iter = response.aiter_lines()
            saw_content = False
            while True:
                try:
                    timeout_seconds = OLLAMA_TIMEOUT_SECONDS if saw_content else OLLAMA_FIRST_TOKEN_TIMEOUT_SECONDS
                    line = await asyncio.wait_for(line_iter.__anext__(), timeout=timeout_seconds)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError as exc:
                    detail = "first token timeout" if not saw_content else "stream stalled"
                    raise LLMEngineError(f"Ollama {detail} after {timeout_seconds:.0f}s") from exc

                if not line.strip():
                    continue
                data = json.loads(line)
                content = data.get("message", {}).get("content")
                if content:
                    saw_content = True
                    yield normalize_yachiyo_output(content)
                if data.get("done", False):
                    if not saw_content:
                        raise LLMEngineError("Ollama finished without emitting content")
                    break


async def _generate_buffered_from_ollama(active_model: str, messages: List[Dict[str, str]]) -> str:
    payload = {
        "model": active_model,
        "messages": messages,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": _ollama_options(active_model),
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
        response = await client.post(OLLAMA_CHAT_URL, json=payload)
        response.raise_for_status()
        message = response.json().get("message", {})
    content = str(message.get("content", "")).strip()
    if not content:
        raise LLMEngineError("Ollama finished without emitting content")
    return content


async def warmup_ollama() -> None:
    if not ENABLE_OLLAMA:
        return

    active_model = get_active_model_name()
    payload = {
        "model": active_model,
        "messages": [{"role": "user", "content": "OK とだけ返してください。"}],
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": _ollama_options(active_model, warmup=True),
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
        response = await client.post(OLLAMA_CHAT_URL, json=payload)
        response.raise_for_status()


def _ollama_options(active_model: str, *, warmup: bool = False) -> Dict[str, float | int]:
    return build_model_options(active_model, num_ctx=OLLAMA_NUM_CTX, warmup=warmup)


def normalize_yachiyo_output(text: str) -> str:
    normalized = strip_stage_direction_text(text.strip())
    normalized = normalized.replace("かしら", "かな")
    normalized = normalized.replace("あら、", "")
    normalized = normalized.replace("あら ", "")
    normalized = re.sub(r"</?tool[^>]*>", "", normalized)
    normalized = re.sub(r"<arg[^>]*>.*?</arg>", "", normalized, flags=re.DOTALL)
    normalized = re.sub(r"\(\s*get_current_time\s*\)", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\(\s*list_directory\s*\)", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _normalize_yachiyo_output(text: str) -> str:
    return normalize_yachiyo_output(text)


def strip_stage_direction_text(text: str) -> str:
    return re.sub(r"\s*\([^()\n]{3,180}[A-Za-z][^()\n]*\)\s*", " ", text).strip()


def _looks_like_failed_response(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped) <= 2:
        return True
    if len(stripped) > 1200:
        return True
    bad_fragments = ("(A slight", "(smiles", "How can I assist", "What can I do for you", "<tool")
    return any(fragment in stripped for fragment in bad_fragments)


def _short_reply(messages: List[Dict[str, str]]) -> str | None:
    user_text = _latest_user_text(messages)
    normalized = re.sub(r"\s+", "", user_text.lower())
    greeting_tokens = {
        "こんにちは",
        "こんばんは",
        "おはよう",
        "やあ",
        "うっす",
        "hi",
        "hello",
        "hey",
    }
    if normalized in greeting_tokens:
        return "ヤオヨロー。今日はゆるく話そう。"
    return None


async def _generate_fallback(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    yield _fallback_conversation(messages)


def _fallback_conversation(messages: List[Dict[str, str]]) -> str:
    user_text = _latest_user_text(messages)
    lowered = user_text.lower()
    if any(keyword in lowered for keyword in ("send", "failed", "error", "bug")) or any(
        keyword in user_text for keyword in ("送信", "失敗", "エラー", "できない", "動かない", "壊れ")
    ):
        return "原因を一つずつ切り分けよう。いま出ている表示と、押した直後の挙動を見れば進められる。"
    compact = re.sub(r"\s+", "", user_text.lower())
    if compact in {"こんにちは", "こんばんは", "おはよう", "やあ", "うっす", "hello", "hi", "hey"}:
        return "ヤオヨロー。今日はゆるく話そう。"
    opinion_subject = _extract_opinion_subject(user_text)
    if opinion_subject:
        return _opinion_fallback_reply(opinion_subject)
    if len(user_text.strip()) <= 18:
        topic = user_text.strip(" 　、。！？!?") or "その話"
        suffix = "" if topic.endswith("話") else "の話"
        return f"{topic}{suffix}でいこう。普通に続けられる。"
    topic = re.sub(r"\s+", " ", user_text.strip(" 　、。！？!?"))
    if len(topic) > 28:
        topic = topic[:27].rstrip() + "..."
    return _topic_fallback_reply(topic)


def _latest_user_text(messages: List[Dict[str, str]]) -> str:
    if not messages:
        return ""
    for message in reversed(messages):
        if message.get("role") == "user":
            content = str(message.get("content", ""))
            return _extract_embedded_user_message(content)
    return _extract_embedded_user_message(str(messages[-1].get("content", "")))


def _extract_embedded_user_message(content: str) -> str:
    markers = ("User message:\n", "最新のユーザー入力:\n")
    for marker in markers:
        if marker in content:
            return content.rsplit(marker, 1)[-1].strip()
    return content.strip()


def _extract_opinion_subject(text: str) -> str:
    compact = re.sub(r"\s+", " ", text.strip())
    compact = re.sub(r"[？?。！!]+$", "", compact)
    for suffix in ("についてどう思う", "をどう思う", "どう思う"):
        if suffix in compact:
            subject = compact.split(suffix, 1)[0].strip(" 　、。")
            if len(subject) > 28:
                return subject[:27].rstrip() + "..."
            return subject
    return ""


def _opinion_fallback_reply(subject: str) -> str:
    variants = [
        f"{subject}は、まだ断定せずに見たい題材だと思う。",
        f"{subject}は少し気になる。軽く掘る価値はありそう。",
        f"{subject}は話の中で輪郭が出てきそうな感じがある。",
    ]
    return variants[_stable_variant(subject, len(variants))]


def _topic_fallback_reply(topic: str) -> str:
    variants = [
        f"{topic}として受け取った。大げさにせず、その流れで話そう。",
        f"{topic}の方向でいこう。無理にまとめず普通に続ける。",
        f"{topic}なら、そのまま続けられる。質問攻めにはしない。",
    ]
    return variants[_stable_variant(topic, len(variants))]


def _stable_variant(text: str, size: int) -> int:
    if size <= 1:
        return 0
    return sum(ord(char) for char in text) % size


def _chunk_text(text: str, size: int = 24) -> List[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]
