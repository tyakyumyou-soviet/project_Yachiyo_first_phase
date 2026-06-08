from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from config import DATA_DIR


MODEL_STATE_PATH = DATA_DIR / "model_state.json"

MODEL_PROFILES: List[Dict[str, str]] = [
    {
        "id": "gemma3_1b",
        "model_name": "gemma3:1b",
        "display_name": "Gemma 3 1B",
        "description": "Very light model for quickest local responses.",
        "size_label": "815 MB",
    },
    {
        "id": "qwen3_17b",
        "model_name": "qwen3:1.7b",
        "display_name": "Qwen3 1.7B",
        "description": "Fast Qwen3 text model for real-time Japanese roleplay trials.",
        "size_label": "1.3 GB",
    },
    {
        "id": "qwen3_4b_instruct_2507_q4km",
        "model_name": "qwen3:4b-instruct-2507-q4_K_M",
        "display_name": "Qwen3 4B Instruct 2507 Q4_K_M",
        "description": "Stronger Qwen3 instruct profile for roleplay quality comparisons.",
        "size_label": "2.5 GB",
    },
]

DEFAULT_MODEL_ID = "qwen3_17b"


def list_model_profiles() -> List[Dict[str, str]]:
    return [dict(profile) for profile in MODEL_PROFILES]


def get_active_profile() -> Dict[str, str]:
    active_id = _load_active_model_id()
    return _get_profile_by_id(active_id)


def get_active_model_name() -> str:
    return get_active_profile()["model_name"]


def set_active_profile(model_id: str) -> Dict[str, str]:
    profile = _get_profile(model_id)
    MODEL_STATE_PATH.write_text(json.dumps({"active_model_id": profile["id"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(profile)


def _load_active_model_id() -> str:
    if not MODEL_STATE_PATH.exists():
        return DEFAULT_MODEL_ID

    try:
        payload = json.loads(MODEL_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_MODEL_ID

    active_id = str(payload.get("active_model_id", DEFAULT_MODEL_ID))
    try:
        _get_profile_by_id(active_id)
    except KeyError:
        return DEFAULT_MODEL_ID
    return active_id


def _get_profile(model_id: str) -> Dict[str, str]:
    for profile in MODEL_PROFILES:
        if profile["id"] == model_id or profile["model_name"] == model_id:
            return profile
    raise KeyError(model_id)


def _get_profile_by_id(model_id: str) -> Dict[str, str]:
    for profile in MODEL_PROFILES:
        if profile["id"] == model_id:
            return profile
    raise KeyError(model_id)
