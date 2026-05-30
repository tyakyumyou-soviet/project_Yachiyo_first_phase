# Realtime UI Fix

Date: 2026-05-19

## What changed

- Switched the browser chat flow in [app_shell.html](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\app_shell.html) from streamed `POST /chat` reading to a persistent `WebSocket` connection over `/ws/chat`.
- Added live `Thinking` and `Plan` panels so `thinking_summary` and `plan_summary` can be displayed as they arrive.
- Kept automatic history restore on page load so the current session, or the latest session, appears without a manual reload step.

## Verification

- Ran `python -m unittest tests.test_phase1`: `10` tests passed.
- Ran [scripts/verify_websocket_rally.py](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\scripts\verify_websocket_rally.py) against `ws://127.0.0.1:8000/ws/chat`.
- Confirmed live packets were received in this order:
  - `system_status`
  - `emotion_trigger`
  - `text_chunk`

## Expected behavior now

- Sending a message from the browser should append the reply without reloading the page.
- `Thinking` and `Plan` should update in the dedicated live panels while a response is being generated.
