from __future__ import annotations

import os
from pathlib import Path
from typing import List


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

APP_HOST = os.getenv("YACHIYO_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("YACHIYO_PORT", "8000"))

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.7"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.9"))
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
OLLAMA_FIRST_TOKEN_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_FIRST_TOKEN_TIMEOUT_SECONDS", "45"))
TURN_STREAM_TIMEOUT_SECONDS = float(os.getenv("TURN_STREAM_TIMEOUT_SECONDS", "150"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_WARMUP_ENABLED = os.getenv("OLLAMA_WARMUP_ENABLED", "1") != "0"

ENABLE_OLLAMA = os.getenv("ENABLE_OLLAMA", "1") != "0"
ENABLE_DEV_FALLBACK = os.getenv("ENABLE_DEV_FALLBACK", "1") != "0"

MAX_CHAT_HISTORY_MESSAGES = int(os.getenv("MAX_CHAT_HISTORY_MESSAGES", "20"))
MAX_RAG_ITEMS = int(os.getenv("MAX_RAG_ITEMS", "3"))
MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "20000"))
CHARACTER_PROFILE_PATH = Path(
    os.getenv("YACHIYO_CHARACTER_PROFILE", str(BASE_DIR / "yachiyo_spirit" / "Features_yachiyo.txt"))
)
MAX_CHARACTER_PROFILE_CHARS = int(os.getenv("MAX_CHARACTER_PROFILE_CHARS", "12000"))
MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "3"))
EPISODE_SUMMARY_INTERVAL = int(os.getenv("EPISODE_SUMMARY_INTERVAL", "5"))

MEMORY_DB_PATH = Path(os.getenv("YACHIYO_MEMORY_DB", str(DATA_DIR / "memory.sqlite3")))
SESSION_STORE_PATH = Path(os.getenv("YACHIYO_SESSION_STORE", str(DATA_DIR / "sessions.json")))

DEFAULT_FILE_ROOT = Path(os.getenv("YACHIYO_FILE_ROOT", str(PROJECT_ROOT))).resolve()
ALLOWED_FILE_ROOTS: List[Path] = [DEFAULT_FILE_ROOT]

SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "3"))
SEARCH_MAX_PAGE_CHARS = int(os.getenv("SEARCH_MAX_PAGE_CHARS", "900"))
SEARCH_TIMEOUT_SECONDS = float(os.getenv("SEARCH_TIMEOUT_SECONDS", "15"))

READ_FILE_MAX_CHARS = int(os.getenv("READ_FILE_MAX_CHARS", "120000"))
