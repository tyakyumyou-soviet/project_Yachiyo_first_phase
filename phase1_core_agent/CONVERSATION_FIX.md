# Conversation Fix

Date: 2026-05-19

## Changes

- Reworked the dev fallback in [agent/llm_engine.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\agent\llm_engine.py) so it no longer returns the same fixed sentence for every input.
- Added lightweight conversational behavior for greeting, self-introduction, remembering names, answering remembered names, and short project-strength replies.
- Added idle-time timeout handling to the Ollama stream reader so the app can fall back instead of hanging forever when the local model stays silent.
- Lowered the default `OLLAMA_TIMEOUT_SECONDS` from `120` to `20` in [config.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\config.py).
- Updated [app_shell.html](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\app_shell.html) so the UI automatically loads the current session history, or the latest available session, on page load.

## Verification

- Ran `python -m unittest tests.test_phase1`: `10` tests passed.
- Performed one live round-trip against `http://127.0.0.1:8000/chat` with session `verify-1`.
- Confirmed the stored session at `GET /sessions/verify-1` contains:
  - User: `こんにちは。短く自己紹介して。`
  - Assistant: `私はTsukimi Yachiyoと申します。温かく、少し神秘的なAIです。どうぞよろしくお願いします。`

## Expected UI behavior

- Opening `http://127.0.0.1:8000/` should now show conversation history automatically without requiring the history button first.
- If the browser's current session is missing, the UI should load the latest available session automatically.
