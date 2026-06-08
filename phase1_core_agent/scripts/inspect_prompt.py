from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.prompt_builder import inspect_prompt  # noqa: E402
from schemas import ChatMessage  # noqa: E402
from tools.tool_registry import render_tool_definitions  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the final prompt sent to Ollama.")
    parser.add_argument("text", nargs="?", default="こんにちは", help="User text to inspect.")
    parser.add_argument("--history", default="", help="Optional JSON list of chat messages.")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    args = parser.parse_args()

    history = _load_history(args.history)
    messages, inspection = inspect_prompt(
        user_text=args.text,
        chat_history=history,
        tool_definitions=render_tool_definitions(),
        rag_memories=[],
        scene_state={"mode": "normal", "topic": "prompt inspection"},
        delta_summary="Prompt inspection run.",
    )
    payload = {"inspection": inspection.__dict__, "messages": messages}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print("Prompt inspection")
    print(f"model: {inspection.active_model_name}")
    print(f"adapter: {inspection.adapter_name}")
    print(f"roles: {', '.join(inspection.message_roles)}")
    print(f"system_chars: {inspection.system_chars}")
    print(f"estimated_prompt_chars: {inspection.estimated_prompt_chars}")
    print(f"sections: {inspection.sections}")
    print("\nMessages:")
    for index, message in enumerate(messages):
        content = str(message.get("content", ""))
        print(f"[{index}] {message.get('role')} chars={len(content)}")
        print(content[:1200])
        print("---")


def _load_history(raw: str) -> list[ChatMessage]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    history = []
    for item in payload:
        try:
            history.append(ChatMessage.model_validate(item))
        except Exception:
            continue
    return history


if __name__ == "__main__":
    main()
