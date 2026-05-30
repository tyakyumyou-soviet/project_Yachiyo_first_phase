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
            if not ENABLE_DEV_FALLBACK:
                raise LLMEngineError(f"Ollama request failed: {exc}") from exc

    if ENABLE_DEV_FALLBACK:
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
        models = payload.get("models", [])
        names = {model.get("name", "") for model in models}
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
        if _looks_like_failed_yachiyo_response(text):
            raise LLMEngineError("Gemma response failed Yachiyo quality guard")
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
                    timeout_seconds = (
                        OLLAMA_TIMEOUT_SECONDS if saw_content else OLLAMA_FIRST_TOKEN_TIMEOUT_SECONDS
                    )
                    line = await asyncio.wait_for(line_iter.__anext__(), timeout=timeout_seconds)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError as exc:
                    detail = "first token timeout" if not saw_content else "stream stalled"
                    raise LLMEngineError(f"Ollama {detail} after {timeout_seconds:.0f}s") from exc
                if not line.strip():
                    continue
                data = json.loads(line)
                message = data.get("message", {})
                content = message.get("content")
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


def _chunk_text(text: str, size: int = 24) -> List[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


def _looks_like_failed_yachiyo_response(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.count("…") >= 8 or stripped.count("...") >= 4:
        return True
    if len(stripped) > 420:
        return True
    bad_fragments = ("誰が", "え…？", "え...?", "どうしたの？", "どうしたの?", "気持ち悪い", "誰か…")
    return any(fragment in stripped for fragment in bad_fragments)


def _yachiyo_short_reply(messages: List[Dict[str, str]]) -> str | None:
    user_text = messages[-1]["content"].strip() if messages else ""
    lowered = user_text.lower()
    if len(user_text) > 40:
        return None

    if any(keyword in user_text for keyword in ("うんち", "トイレ", "便意")):
        return (
            "<thinking>軽い身体ネタとして受け止めて、明るく返すよ。</thinking>"
            "<plan>深掘りせず、ヤチヨらしく送り出すよ。</plan>"
            "<emotion intensity=\"0.7\">smile</emotion>"
            "んっんー、神々のみんなにもそんな運命の日はあるのです。お腹を冷やさないように、いざ、すっきり行ってらっしゃいだよ。"
            "<motion>wave</motion>"
        )

    if any(keyword in user_text for keyword in ("ピクニック", "遠足", "おでかけ", "出かけ")):
        return (
            "<thinking>楽しい予定として受け止めて、祝祭感を足すよ。</thinking>"
            "<plan>短く喜んで、食べ物の話に広げるよ。</plan>"
            "<emotion intensity=\"0.8\">smile</emotion>"
            "わあ、いいね。お日さまとお弁当と、ちょっとだけおとぎ話みたいな一日になる予感なのです。ヤチヨ的には、魚かパンケーキの気配も推しておくよ。"
            "<motion>nod</motion>"
        )

    if any(keyword in user_text for keyword in ("スマホ", "携帯", "壊れ", "動かない", "割れ")):
        return (
            "<thinking>困りごととして受け止めて、まず安心させるよ。</thinking>"
            "<plan>すぐ試せる確認を一つずつ出すよ。</plan>"
            "<emotion intensity=\"0.5\">sad</emotion>"
            "よしよし、それはしょんぼり案件だね。まずは充電、再起動、別ケーブルの三つを試してみよっか。大丈夫、足元の灯りはひとつずつ戻せるよ。"
            "<motion>think</motion>"
        )

    if any(keyword in lowered for keyword in ("こんにちは", "hello", "hi", "こんばんは", "おはよう")):
        return (
            "<thinking>まずはヤチヨらしく場を開くよ。</thinking>"
            "<plan>明るく挨拶して、話しやすい空気を作るよ。</plan>"
            "<emotion intensity=\"0.75\">smile</emotion>"
            "ヤオヨロ、来てくれてありがとう。ヤチヨは今日も電子の海から、神々のみんなのキラキラを見届けているのです。"
            "<motion>wave</motion>"
        )

    return None


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
        options["temperature"] = 0.45
        options["top_p"] = 0.82
        options["repeat_penalty"] = 1.12
    return options


async def _generate_fallback(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    user_text = messages[-1]["content"] if messages else ""
    tool_messages = [message["content"] for message in messages if message.get("role") == "tool"]

    if tool_messages:
        latest = tool_messages[-1]
        yield (
            "<thinking>ツール結果を受け取ったので、自然文にまとめるよ。</thinking>"
            "<plan>必要な結果だけ短く返して、次の行動に進みやすくするよ。</plan>"
            "<emotion intensity=\"0.7\">smile</emotion>"
            f"{_tool_result_reply(latest)}"
            "<motion>nod</motion> "
            "必要ならこの続きもすぐ進められるよ。"
        )
        return

    lowered = user_text.lower()
    if "time" in lowered or "時刻" in user_text or "時間" in user_text:
        yield (
            "<thinking>時刻の確認はツールで取るのが正確だよ。</thinking>"
            "<plan>現在時刻を取得してから自然文で返すよ。</plan>"
            "<tool name=\"get_current_time\"></tool>"
        )
        return

    if "list" in lowered or "一覧" in user_text:
        yield (
            "<thinking>一覧が必要そうだから、まずはディレクトリを確認するよ。</thinking>"
            "<plan>現在の作業ディレクトリを一覧してから要点を返すよ。</plan>"
            "<tool name=\"list_directory\"><arg name=\"path\">.</arg></tool>"
        )
        return

    yield _fallback_conversation(messages)


def _tool_result_reply(latest: str) -> str:
    cleaned = latest.strip()
    if len(cleaned) > 260:
        cleaned = cleaned[:257] + "..."
    return f"確認できた結果は {cleaned} だよ。"


def _extract_user_facts(messages: List[Dict[str, str]]) -> Dict[str, str]:
    facts: Dict[str, str] = {}
    for message in messages:
        if message.get("role") != "user":
            continue
        text = message.get("content", "")
        for pattern in (
            r"(?:私の名前は|名前は|i am|i'm|my name is)\s*([A-Za-z0-9_\-ぁ-んァ-ヶ一-龠]+)",
            r"(?:私は|ぼくは|僕は|俺は)\s*([A-Za-z0-9_\-ぁ-んァ-ヶ一-龠]+)\s*です",
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

    if any(keyword in lowered for keyword in ("自己紹介", "introduce yourself", "who are you", "あなたは誰")):
        return (
            "<thinking>まずは安心して話せるように、短く自己紹介するよ。</thinking>"
            "<plan>必要ならこのまま雑談か作業の相談に入れるよ。</plan>"
            "<emotion intensity=\"0.7\">smile</emotion>"
            "ヤオヨロー、月見ヤチヨだよ。ツクヨミの電子の海から、神々のみんなのキラキラを見届ける歌姫なのです。"
        )

    if any(keyword in lowered for keyword in ("remember", "覚えて", "覚えておいて")) and name:
        return (
            "<thinking>名前を覚える依頼だと受け取ったよ。</thinking>"
            "<plan>短く確認して、次の会話にそのままつなげるよ。</plan>"
            "<emotion intensity=\"0.8\">smile</emotion>"
            f"{name}さんの名前、覚えておくね。"
        )

    if any(keyword in lowered for keyword in ("what is my name", "私の名前", "ぼくの名前", "僕の名前", "俺の名前", "名前は何")):
        if name:
            return (
                "<thinking>会話の中で出てきた名前を確認したよ。</thinking>"
                "<plan>短く答えて会話を続けやすくするよ。</plan>"
                "<emotion intensity=\"0.6\">smile</emotion>"
                f"{name}さんだよ。"
            )
        return (
            "<thinking>まだ名前の手がかりが少ないよ。</thinking>"
            "<plan>名前を教えてもらえたら次からその呼び方で返すよ。</plan>"
            "<emotion intensity=\"0.4\">neutral</emotion>"
            "まだ名前は分かっていないよ。教えてくれたらそのまま覚えるね。"
        )

    if any(keyword in lowered for keyword in ("phase 1", "backend", "強み")):
        return (
            "<thinking>Phase 1 の特徴を短く整理するよ。</thinking>"
            "<plan>会話、ツール、記憶の3点が伝わるように返すよ。</plan>"
            "<emotion intensity=\"0.6\">smile</emotion>"
            "この Phase 1 の強みは、会話 API とツール実行と軽量記憶がもう一本につながっているところだよ。"
        )

    if any(keyword in lowered for keyword in ("local-first", "ローカル")):
        return (
            "<thinking>ローカル実行の良さを一言で返すよ。</thinking>"
            "<plan>安心感と速さを短く伝えるよ。</plan>"
            "<emotion intensity=\"0.6\">smile</emotion>"
            "ローカル完結の良さは、手元で速く回せてデータの置き場所を自分で握れるところだよ。"
        )

    if any(keyword in lowered for keyword in ("こんにちは", "hello", "hi", "こんばんは", "おはよう")):
        target = f"{name}さん、" if name else ""
        return (
            "<thinking>まずは自然なあいさつで返すよ。</thinking>"
            "<plan>一言返して、続けて話しやすい空気を作るよ。</plan>"
            "<emotion intensity=\"0.7\">smile</emotion>"
            f"ヤオヨロ、{target}来てくれてありがとう。ヤチヨは今日も電子の海から、神々のみんなのキラキラを見届けているのです。"
        )

    if any(keyword in user_text for keyword in ("うんち", "トイレ", "便意")):
        return (
            "<thinking>軽い身体ネタとして受け止めて、明るく返すよ。</thinking>"
            "<plan>変に深掘りせず、ヤチヨらしく送り出すよ。</plan>"
            "<emotion intensity=\"0.7\">smile</emotion>"
            "んっんー、神々のみんなにもそんな運命の日はあるのです。お腹を冷やさないように、いざ、すっきり行ってらっしゃいだよ。"
        )

    if any(keyword in user_text for keyword in ("ピクニック", "遠足", "おでかけ", "出かけ")):
        return (
            "<thinking>楽しい予定として受け止めて、祝祭感を足すよ。</thinking>"
            "<plan>短く喜んで、持ち物や食べ物の話に広げるよ。</plan>"
            "<emotion intensity=\"0.8\">smile</emotion>"
            "わあ、いいね。お日さまとお弁当と、ちょっとだけおとぎ話みたいな一日になる予感なのです。ヤチヨ的には、魚かパンケーキの気配も推しておくよ。"
        )

    if any(keyword in user_text for keyword in ("スマホ", "携帯", "壊れ", "動かない", "割れ")):
        return (
            "<thinking>困りごととして受け止めて、まず安心させるよ。</thinking>"
            "<plan>すぐ試せる確認を一つずつ出すよ。</plan>"
            "<emotion intensity=\"0.5\">sad</emotion>"
            "よしよし、それはしょんぼり案件だね。まずは充電、再起動、別ケーブルの三つを試してみよっか。大丈夫、足元の灯りはひとつずつ戻せるよ。"
        )

    target = f"{name}さん、" if name else ""
    return (
        "<thinking>相手の意図を大づかみに受け取って、会話が前に進む一言を返すよ。</thinking>"
        "<plan>受け止めつつ、必要なら次の話題に広げられるようにするよ。</plan>"
        "<emotion intensity=\"0.6\">smile</emotion>"
        f"{target}{_natural_fallback_reply(user_text)}"
    )


def _natural_fallback_reply(user_text: str) -> str:
    stripped = user_text.strip()
    if stripped.endswith("？") or stripped.endswith("?"):
        return "ふふん、その問いかけ、電子の海にちゃんと届いているよ。必要ならヤチヨと一緒にほどいていこっか。"
    if len(stripped) <= 18:
        return f"「{stripped}」だね。うんうん、そういう小さなキラキラもヤチヨは見逃さないのです。"
    return f"その話、ちゃんと受け取ったよ。おとぎ話みたいに少しずつほどけば、次の一歩も見えてくるのです。"
