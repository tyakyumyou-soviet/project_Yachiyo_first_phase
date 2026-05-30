from __future__ import annotations

import asyncio
import json

import websockets


async def main() -> None:
    async with websockets.connect("ws://127.0.0.1:8000/ws/chat") as websocket:
        first = await websocket.recv()
        print(first)

        await websocket.send(
            json.dumps(
                {
                    "text": "こんにちは。短く自己紹介して。",
                    "session_id": "verify-ws-1",
                },
                ensure_ascii=False,
            )
        )

        for _ in range(12):
            message = await asyncio.wait_for(websocket.recv(), timeout=35)
            print(message)
            payload = json.loads(message)
            if payload.get("event_type") == "text_chunk":
                break


if __name__ == "__main__":
    asyncio.run(main())
