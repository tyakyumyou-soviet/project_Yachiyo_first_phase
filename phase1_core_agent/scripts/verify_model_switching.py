from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import httpx


BASE_URL = "http://127.0.0.1:8000"
VERIFY_PROMPT = "こんにちは。短く自己紹介してください。"
MODEL_IDS = ["qwen25_3b", "gemma3_1b"]
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "model_switch_verification.json"


def select_model(client: httpx.Client, model_id: str) -> Dict[str, str]:
    response = client.post(f"{BASE_URL}/models/select", json={"model_id": model_id}, timeout=20.0)
    response.raise_for_status()
    return response.json()["active_model"]


def stream_chat_once(client: httpx.Client, model_id: str) -> Dict[str, object]:
    session_id = f"verify-{model_id}"
    payload = {"text": VERIFY_PROMPT, "session_id": session_id}
    event_types: List[str] = []
    text_chunks: List[str] = []

    with client.stream("POST", f"{BASE_URL}/chat", json=payload, timeout=90.0) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            packet = json.loads(line[6:])
            event_type = packet.get("event_type", "")
            event_types.append(event_type)
            if event_type == "text_chunk":
                text_chunks.append(str(packet.get("payload", "")))

    detail = client.get(f"{BASE_URL}/sessions/{session_id}", timeout=20.0)
    detail.raise_for_status()
    history = detail.json()["history"]

    assistant_messages = [item["content"] for item in history if item.get("role") == "assistant"]
    assistant_text = assistant_messages[-1] if assistant_messages else "".join(text_chunks).strip()

    return {
        "session_id": session_id,
        "event_types": event_types,
        "assistant_text": assistant_text,
        "history": history,
    }


def main() -> None:
    with httpx.Client() as client:
        health = client.get(f"{BASE_URL}/health", timeout=20.0).json()
        models = client.get(f"{BASE_URL}/models", timeout=20.0).json()
        results = []
        for model_id in MODEL_IDS:
            active_model = select_model(client, model_id)
            result = stream_chat_once(client, model_id)
            result["active_model"] = active_model
            results.append(result)

        payload = {"health": health, "models": models, "results": results}
        OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote verification log: {OUTPUT_PATH}")
        for result in results:
            preview = result["assistant_text"][:80].replace("\n", " ").encode("unicode_escape").decode("ascii")
            print(
                " | ".join(
                    [
                        result["active_model"]["display_name"],
                        result["active_model"]["model_name"],
                        preview,
                    ]
                )
            )


if __name__ == "__main__":
    main()
