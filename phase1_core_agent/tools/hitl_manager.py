from __future__ import annotations

import asyncio
import json
from typing import Dict


DESTRUCTIVE_TOOLS = {"write_text_file", "delete_file"}
_approval_lock = asyncio.Lock()


async def request_approval(tool_name: str, args: Dict[str, str]) -> bool:
    async with _approval_lock:
        print(f"\n[Approval] Tool: {tool_name}")
        print(json.dumps(args, ensure_ascii=False, indent=2))
        response = await asyncio.to_thread(input, "Execute this tool? [Y/N]: ")
        return response.strip().upper() == "Y"
