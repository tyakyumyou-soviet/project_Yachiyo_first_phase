from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

from config import BASE_DIR, MAX_CHAT_HISTORY_MESSAGES, MAX_PROMPT_CHARS
from model_manager import get_active_profile
from schemas import ChatMessage

from .character_profile import load_character_profile
from .model_adapters import get_model_adapter


SPIRIT_DIR = BASE_DIR / "yachiyo_spirit"
PERSONA_ANCHOR_PATH = SPIRIT_DIR / "persona_anchor.md"
STYLE_EXAMPLES_PATH = SPIRIT_DIR / "style_examples.jsonl"
LOREBOOK_PATH = SPIRIT_DIR / "lorebook.jsonl"


@dataclass(frozen=True)
class PromptInspection:
    active_model_id: str
    active_model_name: str
    adapter_name: str
    message_roles: List[str]
    system_chars: int
    history_message_count: int
    rag_chars: int
    estimated_prompt_chars: int
    sections: Dict[str, int]


def build_messages(
    *,
    user_text: str,
    chat_history: List[ChatMessage],
    tool_definitions: str,
    rag_memories: List[str],
    scene_state: Dict[str, str] | None = None,
    delta_summary: str = "",
) -> List[dict]:
    del tool_definitions
    active_profile = get_active_profile()
    model_name = active_profile["model_name"]
    adapter = get_model_adapter(model_name)
    sections = _build_prompt_sections(
        user_text=user_text,
        chat_history=chat_history,
        rag_memories=rag_memories,
        scene_state=scene_state or {},
        delta_summary=delta_summary,
        model_label=f"{active_profile['display_name']} ({model_name})",
    )
    system_prompt = _truncate_text("\n\n".join(section for section in sections if section), _prompt_limit_for_model(model_name))
    history_limit = _history_limit_for_model(model_name)

    messages: List[dict] = [{"role": "system", "content": system_prompt}]
    for message in chat_history[-history_limit:]:
        if message.role not in {"user", "assistant"}:
            continue
        messages.append({"role": message.role, "content": _truncate_text(message.content, 900)})
    messages.append({"role": "user", "content": _truncate_text(user_text, 1600)})
    return _adapt_messages_for_model(messages, adapter)


def inspect_prompt(
    *,
    user_text: str,
    chat_history: List[ChatMessage],
    tool_definitions: str,
    rag_memories: List[str],
    scene_state: Dict[str, str] | None = None,
    delta_summary: str = "",
) -> tuple[List[dict], PromptInspection]:
    del tool_definitions
    active_profile = get_active_profile()
    messages = build_messages(
        user_text=user_text,
        chat_history=chat_history,
        tool_definitions="(unused)",
        rag_memories=rag_memories,
        scene_state=scene_state,
        delta_summary=delta_summary,
    )
    joined = "\n".join(str(message.get("content", "")) for message in messages)
    system_chars = sum(len(str(message.get("content", ""))) for message in messages if message.get("role") == "system")
    rag_chars = sum(len(item) for item in rag_memories)
    sections = {
        "persona_anchor": len(_render_persona_anchor()),
        "style_examples": len(_render_style_examples(active_profile["model_name"])),
        "lore": len(_render_lore(user_text, scene_state or {})),
        "delta_summary": len(_render_delta_summary(delta_summary)),
        "scene_state": len(_render_scene_state(scene_state or {})),
        "memory": len(_render_rag_context(rag_memories)),
    }
    return messages, PromptInspection(
        active_model_id=active_profile["id"],
        active_model_name=active_profile["model_name"],
        adapter_name=get_model_adapter(active_profile["model_name"]).adapter_name,
        message_roles=[str(message.get("role", "")) for message in messages],
        system_chars=system_chars,
        history_message_count=len(chat_history),
        rag_chars=rag_chars,
        estimated_prompt_chars=len(joined),
        sections=sections,
    )


def _adapt_messages_for_model(messages: List[dict], adapter) -> List[dict]:
    if adapter.supports_system_role and not adapter.prefers_user_anchor:
        adapted = [dict(message) for message in messages]
        if adapter.roleplay_prefix:
            for message in adapted:
                if message.get("role") == "system":
                    message["content"] = adapter.roleplay_prefix + message.get("content", "")
                    break
        return adapted

    system_parts = [message.get("content", "") for message in messages if message.get("role") == "system"]
    non_system = [dict(message) for message in messages if message.get("role") != "system"]
    if not system_parts:
        return non_system
    anchor = "\n\n".join(part for part in system_parts if part).strip()
    if adapter.roleplay_prefix:
        anchor = f"{adapter.roleplay_prefix}\n{anchor}"
    if non_system and non_system[0].get("role") == "user":
        non_system[0]["content"] = f"{anchor}\n\n最新のユーザー入力:\n{non_system[0].get('content', '')}"
        return non_system
    return [{"role": "user", "content": anchor}] + non_system


def _build_prompt_sections(
    *,
    user_text: str,
    chat_history: List[ChatMessage],
    rag_memories: List[str],
    scene_state: Dict[str, str],
    delta_summary: str,
    model_label: str,
) -> List[str]:
    model_name = get_active_profile()["model_name"]
    sections = [
        _render_model_contract(model_label),
        _render_persona_anchor(),
        _render_runtime_mode_hint(user_text, chat_history),
        _render_final_turn_instruction(),
    ]

    if model_name == "qwen3:1.7b":
        return sections

    for section in (
        _render_scene_state(scene_state),
        _render_delta_summary(delta_summary),
        _render_lore(user_text, scene_state),
        _render_rag_context(rag_memories),
        _render_style_examples(model_name),
    ):
        if section:
            sections.append(section)
    return sections


def _render_model_contract(model_label: str) -> str:
    return (
        "## Role\n"
        "普通の日本語会話を最優先し、ヤチヨらしさは受容、茶目っ気、余白として薄く乗せる。\n"
        "演出、設定説明、過剰な問い返しより、自然な返答を優先する。\n"
        f"Current model: {model_label}"
    )


def _render_persona_anchor() -> str:
    anchor = _load_text(PERSONA_ANCHOR_PATH, "").strip()
    if anchor:
        return "## Persona Anchor\n" + _truncate_text(anchor, 700)
    snapshot = load_character_profile()
    return "## Persona Anchor\n" + _truncate_text(snapshot.content, 600)


def _render_style_examples(model_name: str) -> str:
    rows = _load_jsonl(STYLE_EXAMPLES_PATH)
    if not rows:
        return ""
    limit = 1 if model_name == "gemma3:1b" else 2
    examples = []
    for row in rows[:limit]:
        user = str(row.get("user", "")).strip()
        assistant = str(row.get("assistant", "")).strip()
        if user and assistant:
            examples.append(f"User: {user}\nAssistant: {assistant}")
    if not examples:
        return ""
    return "## Style Examples\n" + "\n\n".join(examples)


def _render_scene_state(scene_state: Dict[str, str]) -> str:
    if not scene_state:
        return ""
    lines = [f"{key}: {value}" for key, value in scene_state.items() if value]
    if not lines:
        return ""
    return "## Scene State\n" + "\n".join(lines[:5])


def _render_delta_summary(delta_summary: str) -> str:
    value = delta_summary.strip()
    if not value:
        return ""
    return "## Conversation Summary\n" + _truncate_text(value, 320)


def _render_lore(user_text: str, scene_state: Dict[str, str]) -> str:
    rows = _select_lore(user_text, scene_state)
    if not rows:
        return ""
    rendered = [f"- {row.get('content', '')}" for row in rows[:1]]
    return "## Selected Lore\n" + "\n".join(rendered)


def _render_rag_context(memories: Sequence[str]) -> str:
    if not memories:
        return ""
    rendered = "\n".join(f"- {item}" for item in list(memories)[:1])
    return "## Relevant Memory\n" + _truncate_text(rendered, 260)


def _render_runtime_mode_hint(user_text: str, chat_history: List[ChatMessage]) -> str:
    context = "\n".join([message.content for message in chat_history[-3:]] + [user_text]).lower()
    troubleshooting_keywords = (
        "できない",
        "動かない",
        "壊れ",
        "エラー",
        "反応",
        "送信",
        "load failed",
        "bug",
        "error",
        "fail",
        "failed",
    )
    if any(keyword in context for keyword in troubleshooting_keywords):
        return (
            "## Mode\n"
            "不具合相談として扱う。\n"
            "挨拶や前置きは入れず、すぐ本題に入る。\n"
            "原因候補は一つか二つに絞る。\n"
            "次に確認することを一つだけ示す。"
        )
    return (
        "## Mode\n"
        "普通の雑談として自然に返す。\n"
        "まず受け止め、短い所感や返答を出す。\n"
        "疑問文は原則使わない。必要なときだけ一つまで。\n"
        "少しだけ「だよ」「だね」「かな」「ヤチヨ的には」などの語感を混ぜてよい。"
    )


def _render_final_turn_instruction() -> str:
    return (
        "## Reply Rule\n"
        "最新のユーザー入力にだけ答える。\n"
        "挨拶入力以外では「ヤオヨロー！」から始めない。\n"
        "雑談では質問で終わらせない。\n"
        "ユーザー文をそのまま反復しない。\n"
        "英語の舞台描写や括弧書きは禁止。\n"
        "ツール名やコマンド文字列を書かない。\n"
        "ヤチヨらしさは一語だけでよい。濃くしすぎない。\n"
        "1文から3文で返す。"
    )


def _select_lore(user_text: str, scene_state: Dict[str, str]) -> List[Dict[str, str]]:
    rows = _load_jsonl(LOREBOOK_PATH)
    if not rows:
        return []
    haystack = user_text.lower()
    mode = scene_state.get("mode", "normal")
    selected = []
    for row in rows:
        risk = str(row.get("risk", "safe"))
        if risk == "deep_only" and mode != "deep":
            continue
        keys = row.get("keys", [])
        if isinstance(keys, list) and any(str(key).lower() in haystack for key in keys):
            selected.append(row)
    return selected[:1]


def _history_limit_for_model(model_name: str) -> int:
    if model_name == "gemma3:1b":
        return min(MAX_CHAT_HISTORY_MESSAGES, 6)
    if model_name == "qwen3:1.7b":
        return min(MAX_CHAT_HISTORY_MESSAGES, 8)
    return min(MAX_CHAT_HISTORY_MESSAGES, 12)


def _prompt_limit_for_model(model_name: str) -> int:
    if model_name == "gemma3:1b":
        return min(MAX_PROMPT_CHARS, 1400)
    if model_name == "qwen3:1.7b":
        return min(MAX_PROMPT_CHARS, 1700)
    return min(MAX_PROMPT_CHARS, 3200)


def _truncate_text(text: str, limit: int) -> str:
    value = text.strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "..."


def _load_text(path: Path, fallback: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return fallback


def _load_jsonl(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    rows: List[Dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows
