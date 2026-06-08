from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.drift_detector import detect_drift  # noqa: E402
from main import ChatSession, stream_chat_turn  # noqa: E402


DEFAULT_EVAL = ROOT / "evals" / "yachiyo_short_style.jsonl"


async def run_eval(path: Path, *, max_cases: int | None = None) -> Dict[str, Any]:
    cases = _load_jsonl(path)
    if max_cases is not None:
        cases = cases[:max_cases]
    results = []
    for case in cases:
        session = ChatSession(session_id=f"eval-{case.get('id', len(results))}")
        started = time.perf_counter()
        final_text = ""
        first_text_latency = None
        for turn in case.get("turns", [{"user": case.get("input", "")}]):
            user_text = str(turn.get("user", ""))
            async for packet in stream_chat_turn(session, user_text):
                if packet.event_type == "text_chunk" and isinstance(packet.payload, str):
                    if first_text_latency is None:
                        first_text_latency = time.perf_counter() - started
                    final_text += packet.payload
        elapsed = time.perf_counter() - started
        drift = detect_drift(final_text, user_text=str(case.get("input", "")))
        results.append(
            {
                "id": case.get("id"),
                "elapsed_seconds": round(elapsed, 3),
                "first_text_latency_seconds": round(first_text_latency, 3) if first_text_latency is not None else None,
                "drifted": drift.drifted,
                "drift_reasons": drift.reasons,
                "empty": not bool(final_text.strip()),
                "reply_preview": final_text.strip()[:240],
            }
        )
    return {"eval_file": str(path), "cases": len(results), "results": results}


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a lightweight Yachiyo roleplay eval.")
    parser.add_argument("--file", default=str(DEFAULT_EVAL), help="JSONL eval file.")
    parser.add_argument("--max-cases", type=int, default=None)
    args = parser.parse_args()
    result = asyncio.run(run_eval(Path(args.file), max_cases=args.max_cases))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
