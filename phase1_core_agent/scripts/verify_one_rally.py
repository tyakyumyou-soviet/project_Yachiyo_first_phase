from __future__ import annotations

import json

import httpx


def main() -> None:
    payload = {"text": "こんにちは。短く自己紹介して。", "session_id": "verify-1"}
    with httpx.stream("POST", "http://127.0.0.1:8000/chat", json=payload, timeout=45.0) as response:
        print(f"status={response.status_code}")
        for line in response.iter_lines():
            if line:
                print(line)

    sessions = httpx.get("http://127.0.0.1:8000/sessions", timeout=10.0)
    print("sessions=" + json.dumps(sessions.json(), ensure_ascii=False))


if __name__ == "__main__":
    main()
