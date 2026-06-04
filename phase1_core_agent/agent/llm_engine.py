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
    OLLAMA_TEMPERATURE,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_TOP_P,
)
from model_manager import get_active_model_name


class LLMEngineError(RuntimeError):
    pass


def user_visible_llm_failure_message(detail: str) -> str:
    active_model = get_active_model_name()
    return (
        "モデルの応答を取得できませんでした。少し待ってからもう一度送ってください。\n"
        f"現在のモデル: {active_model}\n"
        f"詳細: {detail}"
    )


async def generate_stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    short_reply = _yachiyo_short_reply(messages)
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

    if active_model == "gemma3:1b":
        text = await _generate_buffered_from_ollama(active_model, messages)
        if _looks_like_failed_response(text):
            text = await _generate_buffered_from_ollama(active_model, _repair_gemma_messages(messages))
        if _looks_like_failed_response(text):
            text = _fallback_conversation(messages)
        if _looks_like_failed_response(text):
            raise LLMEngineError("Gemma response failed quality guard")
        for chunk in _chunk_text(text):
            yield chunk
        return

    payload = {
        "model": active_model,
        "messages": messages,
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
                    yield content
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
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": _ollama_options(active_model, warmup=True),
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
        response = await client.post(OLLAMA_CHAT_URL, json=payload)
        response.raise_for_status()


def _ollama_options(active_model: str, *, warmup: bool = False) -> Dict[str, float | int]:
    options: Dict[str, float | int] = {
        "num_ctx": 1024 if warmup else OLLAMA_NUM_CTX,
        "temperature": 0.0 if warmup else OLLAMA_TEMPERATURE,
        "top_p": OLLAMA_TOP_P,
    }
    if warmup:
        options["num_predict"] = 8
        return options

    if active_model == "gemma3:1b":
        options["temperature"] = 0.35
        options["top_p"] = 0.8
        options["repeat_penalty"] = 1.15
    return options


def _chunk_text(text: str, size: int = 24) -> List[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


def _looks_like_failed_response(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True

    normalized = re.sub(r"\s+", "", stripped)
    bad_tokens = {
        "だよ。",
        "だよ",
        "だね。",
        "だね",
        "かな。",
        "かな",
        "よ。",
        "よ",
        "だよ、だね？",
        "だよ、だね",
        "なのです",
    }
    if normalized in bad_tokens:
        return True
    if len(stripped) <= 3 and not any(char in stripped for char in "。！？!?"):
        return True
    if stripped.count("...") >= 4 or stripped.count("…") >= 6:
        return True
    if len(stripped) > 900:
        return True
    bad_fragments = ("ヤチヨ…", "まだ歌を歌うべき", "(A slight", "(smiles")
    return any(fragment in stripped for fragment in bad_fragments)


def _repair_gemma_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    system_content = next((message.get("content", "") for message in messages if message.get("role") == "system"), "")
    user_content = next(
        (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
        "",
    )
    return [
        {
            "role": "system",
            "content": (
                f"{system_content}\n\n"
                "重要: 直前のユーザー発言へ、自然な日本語で1〜2文だけ返す。"
                "単語だけ、語尾だけ、ルール説明、ト書き、独白は禁止。"
                "「あら」で始めない。"
            ),
        },
        {"role": "user", "content": user_content},
    ]


def _yachiyo_short_reply(messages: List[Dict[str, str]]) -> str | None:
    user_text = messages[-1]["content"].strip() if messages else ""
    normalized = re.sub(r"\s+", "", user_text.lower())
    greeting_tokens = {
        "こんにちは",
        "こんばんは",
        "おはよう",
        "やあ",
        "うっす",
        "hello",
        "hi",
        "hey",
    }
    if normalized in greeting_tokens:
        return "ヤオヨロー！ こんにちは。今日はどんな話をしようか。"
    return None


async def _generate_fallback(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    user_text = messages[-1]["content"] if messages else ""
    tool_messages = [message["content"] for message in messages if message.get("role") == "tool"]

    if tool_messages:
        yield _tool_result_reply(tool_messages[-1])
        return

    lowered = user_text.lower()
    if "time" in lowered or "時刻" in user_text or "時間" in user_text:
        yield '<tool name="get_current_time"></tool>'
        return

    if "list" in lowered or "一覧" in user_text:
        yield '<tool name="list_directory"><arg name="path">.</arg></tool>'
        return

    yield _fallback_conversation(messages)


def _tool_result_reply(latest: str) -> str:
    cleaned = latest.strip()
    if len(cleaned) > 260:
        cleaned = cleaned[:257] + "..."
    return f"確認できた内容は次の通りです: {cleaned}"


def _extract_user_facts(messages: List[Dict[str, str]]) -> Dict[str, str]:
    facts: Dict[str, str] = {}
    for message in messages:
        if message.get("role") != "user":
            continue
        text = message.get("content", "")
        for pattern in (
            r"(?:名前は|僕は|私は|i am|i'm|my name is)\s*([A-Za-z0-9_\-\u3040-\u30ff\u4e00-\u9fff]+)",
            r"(?:俺は|ぼくは|君は)\s*([A-Za-z0-9_\-\u3040-\u30ff\u4e00-\u9fff]+)\s*です",
        ):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                facts["name"] = match.group(1)
    return facts


def _fallback_conversation(messages: List[Dict[str, str]]) -> str:
    user_text = messages[-1]["content"] if messages else ""
    lowered = user_text.lower()
    facts = _extract_user_facts(messages)
    name = facts.get("name")

    if any(keyword in lowered for keyword in ("introduce yourself", "who are you", "あなたは誰")):
        return "ヤチヨだよ。気になることがあれば、そのまま話して。ちゃんと受け止めるから。"

    if any(keyword in lowered for keyword in ("remember", "覚えて")) and name:
        return f"うん、覚えておくね。あなたの名前は{name}さん。"

    if any(keyword in lowered for keyword in ("what is my name", "名前", "ぼくの名前", "僕の名前", "俺の名前")):
        if name:
            return f"あなたの名前は{name}さんだよ。"
        return "まだ名前は聞けていないよ。よければ教えて。"

    if any(keyword in lowered for keyword in ("phase 1", "backend", "仕組み")):
        return "Phase 1 は、ローカルLLMと会話API、それからツール実行をまとめた最小構成として動いているよ。"

    if any(keyword in lowered for keyword in ("local-first", "ローカル")):
        return "ローカル中心に動くと、応答やデータの扱いを自分で管理しやすいのが強みだね。"

    if any(keyword in lowered for keyword in ("こんにちは", "hello", "hi", "こんばんは", "おはよう")):
        return "ヤオヨロー！ こんにちは。今日はどんな話をしようか。"

    if len(user_text.strip()) <= 18:
        return f"{user_text.strip()}、なんだね。もう少しだけ聞けたら、ちゃんと一緒に考えられるよ。"

    return "続けて大丈夫だよ。いま気になっているところから、一つずつ一緒に見ていこう。"
