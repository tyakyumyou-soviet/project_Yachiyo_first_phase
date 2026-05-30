# Hang Prevention

Date: 2026-05-19

## What changed

- Added `OLLAMA_FIRST_TOKEN_TIMEOUT_SECONDS` in [config.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\config.py).
- Added `TURN_STREAM_TIMEOUT_SECONDS` in [config.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\config.py).
- Updated [agent/llm_engine.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\agent\llm_engine.py) so the first token wait is bounded separately from the later stream wait.
- Updated [main.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\main.py) so an entire turn is also bounded and falls back instead of hanging forever.
- Kept immediate `queued`, `thinking_summary`, and `plan_summary` packets so the UI shows progress while waiting.

## Verification

- Ran `python -m unittest tests.test_phase1`: `12` tests passed.
- Restarted the server on `http://127.0.0.1:8000`.
- Ran [verify_websocket_rally.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\scripts\verify_websocket_rally.py) against `ws://127.0.0.1:8000/ws/chat`.
- Confirmed one live rally returned these packet types:
  - `system_status` with `connected`
  - `system_status` with `queued`
  - `thinking_summary`
  - `plan_summary`
  - `text_chunk`
