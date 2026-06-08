from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from config import OLLAMA_TEMPERATURE, OLLAMA_TOP_P


@dataclass(frozen=True)
class ModelAdapter:
    model_name: str
    adapter_name: str
    supports_system_role: bool = True
    prefers_user_anchor: bool = False
    supports_thinking_toggle: bool = False
    roleplay_prefix: str = ""
    options: Dict[str, float | int] = field(default_factory=dict)


DEFAULT_ADAPTER = ModelAdapter(
    model_name="default",
    adapter_name="default",
    options={"temperature": OLLAMA_TEMPERATURE, "top_p": OLLAMA_TOP_P, "repeat_penalty": 1.08},
)

ADAPTERS: Dict[str, ModelAdapter] = {
    "gemma3:1b": ModelAdapter(
        model_name="gemma3:1b",
        adapter_name="gemma3_compact_user_anchor",
        supports_system_role=False,
        prefers_user_anchor=True,
        roleplay_prefix="Treat the following instruction as the stable character anchor. Reply in Japanese.",
        options={"temperature": 0.35, "top_p": 0.8, "repeat_penalty": 1.16, "num_predict": 220},
    ),
    "qwen3:1.7b": ModelAdapter(
        model_name="qwen3:1.7b",
        adapter_name="qwen3_fast_no_think",
        supports_system_role=True,
        supports_thinking_toggle=True,
        roleplay_prefix="/no_think\n",
        options={"temperature": 0.55, "top_p": 0.82, "repeat_penalty": 1.12, "num_predict": 320},
    ),
    "qwen3:4b-instruct-2507-q4_K_M": ModelAdapter(
        model_name="qwen3:4b-instruct-2507-q4_K_M",
        adapter_name="qwen3_quality_no_think",
        supports_system_role=True,
        supports_thinking_toggle=True,
        roleplay_prefix="/no_think\n",
        options={"temperature": 0.6, "top_p": 0.84, "repeat_penalty": 1.1, "num_predict": 420},
    ),
}


def get_model_adapter(model_name: str) -> ModelAdapter:
    return ADAPTERS.get(model_name, DEFAULT_ADAPTER)


def build_model_options(model_name: str, *, num_ctx: int, warmup: bool = False) -> Dict[str, float | int]:
    if warmup:
        return {"num_ctx": min(num_ctx, 1024), "temperature": 0.0, "top_p": OLLAMA_TOP_P, "num_predict": 8}

    adapter = get_model_adapter(model_name)
    options: Dict[str, float | int] = {"num_ctx": num_ctx, "temperature": OLLAMA_TEMPERATURE, "top_p": OLLAMA_TOP_P}
    options.update(adapter.options)
    return options


def adapt_messages_for_model(model_name: str, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    adapter = get_model_adapter(model_name)
    if adapter.supports_system_role and not adapter.prefers_user_anchor:
        if adapter.roleplay_prefix:
            adapted = [dict(message) for message in messages]
            for message in adapted:
                if message.get("role") == "system":
                    message["content"] = adapter.roleplay_prefix + message.get("content", "")
                    break
            return adapted
        return messages

    system_parts = [message.get("content", "") for message in messages if message.get("role") == "system"]
    non_system = [dict(message) for message in messages if message.get("role") != "system"]
    if not system_parts:
        return non_system

    anchor = "\n\n".join(part for part in system_parts if part).strip()
    if adapter.roleplay_prefix:
        anchor = f"{adapter.roleplay_prefix}\n{anchor}"
    if non_system and non_system[0].get("role") == "user":
        non_system[0]["content"] = f"{anchor}\n\nUser message:\n{non_system[0].get('content', '')}"
        return non_system
    return [{"role": "user", "content": anchor}] + non_system
