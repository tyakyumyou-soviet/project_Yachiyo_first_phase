from __future__ import annotations

from typing import Iterable, List

from config import MAX_CHAT_HISTORY_MESSAGES, MAX_PROMPT_CHARS
from model_manager import get_active_profile
from schemas import ChatMessage

from .character_profile import load_character_profile
from .persona import SYSTEM_PROMPT_TEMPLATE


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _render_history(chat_history: Iterable[ChatMessage]) -> str:
    recent = list(chat_history)[-MAX_CHAT_HISTORY_MESSAGES:]
    if not recent:
        return "(no conversation history)"
    rendered = "\n".join(f"- {message.role}: {message.content}" for message in recent)
    return _truncate_text(rendered, MAX_PROMPT_CHARS // 2)


def _render_rag_context(memories: List[str]) -> str:
    if not memories:
        return "(no relevant memory)"
    rendered = "\n".join(f"- {item}" for item in memories)
    return _truncate_text(rendered, MAX_PROMPT_CHARS // 4)


def _render_character_profile(model_name: str) -> str:
    snapshot = load_character_profile()
    if not snapshot.loaded:
        return snapshot.content

    if model_name == "gemma3:1b":
        limit = 700
    elif model_name == "gemma4:e2b":
        limit = 1400
    else:
        limit = 2200

    lines = [line.strip() for line in snapshot.content.splitlines() if line.strip()]
    condensed = "\n".join(f"- {line}" for line in lines[:18])
    return _truncate_text(condensed, limit)


def build_messages(
    *,
    user_text: str,
    chat_history: List[ChatMessage],
    tool_definitions: str,
    rag_memories: List[str],
) -> List[dict]:
    active_profile = get_active_profile()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        active_model_label=f"{active_profile['display_name']} ({active_profile['model_name']})",
        character_profile=_render_character_profile(active_profile["model_name"]),
        tool_definitions=tool_definitions,
        rag_context=_render_rag_context(rag_memories),
        chat_history=_render_history(chat_history),
    )
    system_prompt = _truncate_text(system_prompt, MAX_PROMPT_CHARS)

    messages: List[dict] = [{"role": "system", "content": system_prompt}]
    for message in chat_history[-MAX_CHAT_HISTORY_MESSAGES:]:
        messages.append({"role": message.role, "content": _truncate_text(message.content, 3000)})
    messages.append({"role": "user", "content": _truncate_text(user_text, 4000)})
    return messages
