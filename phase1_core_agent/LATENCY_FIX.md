# Latency Fix

Date: 2026-05-19

## What changed

- Added `OLLAMA_KEEP_ALIVE` and enabled it in [agent/llm_engine.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\agent\llm_engine.py) so the local model is more likely to stay resident between turns.
- Added startup warmup via `warmup_ollama()` and the FastAPI lifespan hook in [main.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\main.py).
- Emitted immediate `queued`, `thinking_summary`, and `plan_summary` packets at the start of each turn so the UI reacts right away.
- Updated [app_shell.html](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\app_shell.html) to show an instant preparing state before the first model token arrives.

## Verification

- Ran `python -m unittest tests.test_phase1`: `10` tests passed.
- Restarted the server on `http://127.0.0.1:8000`.

## Notes

- This should reduce the visible stall before a reply starts.
- It will not make local `qwen3-vl:8b` generation instant, but it should make the app feel less stuck and reduce cold-start cost after idle periods.
