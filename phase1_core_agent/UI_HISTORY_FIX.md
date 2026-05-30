# UI History Fix

Date: 2026-05-19

## What changed

- Added `GET /sessions/{session_id}` so the browser UI can reload saved session history from the backend.
- Added `GET /demo/ten-rally` so the saved 10-turn demo log can be displayed inside the web app.
- Moved the root-page HTML into [app_shell.html](C:\Users\taizu\OneDrive\デスクトップ\project_yachiyo\phase1_core_agent\app_shell.html).
- Added a session picker, session ID loader, and demo loader controls to the browser UI.

## Why

- The old UI only showed messages that were streamed during the current browser session.
- Past conversations created from another client, another server process, or a saved demo log were not visible after reload.

## Expected behavior now

1. Open `http://127.0.0.1:8000/`.
2. Click `10ラリーデモ表示` to load the saved demo into the chat panel.
3. Or pick a session from `保存済みセッション`, then click `履歴表示` to replay that session's stored history.
