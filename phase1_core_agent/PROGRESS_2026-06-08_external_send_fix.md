# 2026-06-08 External Send Fix

## Problem

- When accessing the app through `http://100.114.99.4:8000/`, the browser used `/chat/complete` instead of the streaming `/chat` endpoint.
- `/chat/complete` waits until the whole LLM response is generated before returning anything, so the UI can look like the message was not sent.
- This became more visible after testing newly added local models because first-token and full-turn latency can vary significantly by model.

## Fix

- Updated `app_shell.html` so external hosts use streaming chat when `ReadableStream` is available.
- `/chat/complete` now remains only as a fallback for browsers that do not support response streaming.

## Verification

- `POST /chat` works and streams packets.
- `POST /chat/complete` works but can take significantly longer before the UI receives any text.
