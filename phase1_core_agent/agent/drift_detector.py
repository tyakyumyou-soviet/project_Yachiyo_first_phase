from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class DriftReport:
    drifted: bool
    reasons: List[str]


FORBIDDEN_FRAGMENTS = (
    "(A slight",
    "(smiles",
    "as an AI",
    "How can I assist",
    "What can I do for you",
    "<tool",
    "get_current_time",
    "list_directory",
)


def normalize_for_compare(text: str) -> str:
    return re.sub(r"[\s\u3000、。・…\-\"'「」『』()]+", "", text.lower())


def detect_drift(reply: str, *, user_text: str = "", previous_reply: str = "") -> DriftReport:
    reasons: List[str] = []
    stripped = reply.strip()
    if not stripped:
        reasons.append("empty")

    normalized_reply = normalize_for_compare(stripped)
    normalized_user = normalize_for_compare(user_text)
    normalized_previous = normalize_for_compare(previous_reply)

    if normalized_user and normalized_reply == normalized_user:
        reasons.append("user_echo")
    if normalized_previous and normalized_reply == normalized_previous:
        reasons.append("repeat_previous")
    if len(stripped) > 900:
        reasons.append("too_long")
    if re.search(r"\([^()\n]{3,180}[A-Za-z][^()\n]*\)", stripped):
        reasons.append("english_stage_direction")
    if any(fragment in stripped for fragment in FORBIDDEN_FRAGMENTS):
        reasons.append("forbidden_fragment")
    if stripped.count("...") >= 4:
        reasons.append("ellipsis_loop")
    if _has_repeated_ngrams(stripped):
        reasons.append("local_repetition")

    return DriftReport(drifted=bool(reasons), reasons=reasons)


def build_recovery_instruction(user_text: str, reasons: List[str]) -> str:
    reason_text = ", ".join(reasons) if reasons else "style drift"
    return (
        "返答を作り直す。\n"
        f"問題: {reason_text}\n"
        "条件:\n"
        "- 日本語で返す\n"
        "- 1文から3文\n"
        "- ユーザー文を反復しない\n"
        "- 英語の舞台描写や括弧書きを入れない\n"
        "- ツール名やコマンド文字列を書かない\n"
        f"ユーザー入力: {user_text}"
    )


def safe_recovery_reply(user_text: str) -> str:
    if len(user_text.strip()) <= 18:
        return "その話題で答える。知りたい点を一つだけ言って。"
    return "その話題で続けられる。いま一番答えてほしい点を一つに絞って。"


def _has_repeated_ngrams(text: str) -> bool:
    compact = normalize_for_compare(text)
    if len(compact) < 18:
        return False
    for size in (4, 5, 6):
        seen = {}
        for index in range(0, max(0, len(compact) - size + 1)):
            token = compact[index : index + size]
            seen[token] = seen.get(token, 0) + 1
            if seen[token] >= 4:
                return True
    return False
