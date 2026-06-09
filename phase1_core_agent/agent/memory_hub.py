from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from config import EPISODE_SUMMARY_INTERVAL, MAX_RAG_ITEMS, MEMORY_DB_PATH


def _tokenize(text: str) -> List[str]:
    normalized = re.sub(r"[、。，．！？!?()\[\]「」『』:：/\\]+", " ", text.lower())
    return [token for token in re.split(r"\s+", normalized.strip()) if token]


def _is_usable_memory_text(text: str) -> bool:
    value = text.strip()
    if len(value) < 4:
        return False
    forbidden_fragments = ("縺", "繧", "繝", "邵ｺ", "郢", "\ufffd", "???")
    if any(fragment in value for fragment in forbidden_fragments):
        return False
    if value.count("?") >= 3 or value.count("？") >= 3:
        return False
    generic_fragments = (
        "その話、普通に続けよう",
        "気楽に続けよう",
        "もう少しだけ続けて",
        "さっきと同じ返し",
    )
    if any(fragment in value for fragment in generic_fragments):
        return False
    return True


class MemoryHub:
    """SQLite-backed memory store with conservative filtering."""

    def __init__(self, db_path: Path = MEMORY_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS semantic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL DEFAULT 'fact',
                    created_at REAL NOT NULL,
                    recall_count INTEGER NOT NULL DEFAULT 0,
                    last_recalled_at REAL
                );

                CREATE TABLE IF NOT EXISTS episodic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary TEXT NOT NULL,
                    transcript TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    turn_count INTEGER NOT NULL DEFAULT 1
                );
                """
            )

    def recall(self, query: str, limit: int = MAX_RAG_ITEMS) -> List[str]:
        tokens = _tokenize(query)
        if not tokens:
            return []

        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT text, source, created_at, recall_count, COALESCE(last_recalled_at, 0) AS last_recalled_at
                FROM semantic_memory
                UNION ALL
                SELECT summary AS text, 'episode' AS source, created_at, 0 AS recall_count, 0 AS last_recalled_at
                FROM episodic_memory
                """
            ).fetchall()

            scored = []
            now = time.time()
            query_lower = query.lower()
            for row in rows:
                text = str(row["text"])
                if not _is_usable_memory_text(text):
                    continue
                haystack = text.lower()
                keyword_score = sum(2 for token in tokens if token in haystack)
                if keyword_score == 0 and query_lower not in haystack:
                    continue
                recency_bonus = max(0.0, 3.0 - ((now - float(row["created_at"])) / 86400.0))
                recall_bonus = min(float(row["recall_count"]) * 0.2, 1.0)
                scored.append((keyword_score + recency_bonus + recall_bonus, text, str(row["source"])))

            scored.sort(key=lambda item: item[0], reverse=True)
            results = [text for _, text, _ in scored[:limit]]

            for _, text, source in scored[:limit]:
                if source != "fact":
                    continue
                connection.execute(
                    """
                    UPDATE semantic_memory
                    SET recall_count = recall_count + 1, last_recalled_at = ?
                    WHERE text = ?
                    """,
                    (time.time(), text),
                )
            connection.commit()
            return results

    def add_semantic_memory(self, text: str, source: str = "fact") -> None:
        cleaned = text.strip()
        if not _is_usable_memory_text(cleaned):
            return
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO semantic_memory (text, source, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(text) DO UPDATE SET source = excluded.source
                """,
                (cleaned, source, time.time()),
            )
            connection.commit()

    def add_episode(self, summary: str, transcript: Optional[str] = None, turn_count: int = 1) -> None:
        transcript_value = transcript or summary
        if not _is_usable_memory_text(summary) or not _is_usable_memory_text(transcript_value):
            return
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO episodic_memory (summary, transcript, created_at, turn_count)
                VALUES (?, ?, ?, ?)
                """,
                (summary.strip(), transcript_value.strip(), time.time(), turn_count),
            )
            connection.commit()

    def capture_user_facts(self, text: str) -> List[str]:
        patterns = [
            r"私は(.+?)です",
            r"僕は(.+?)です",
            r"俺は(.+?)だ",
            r"好きなのは(.+?)です",
            r"好きなものは(.+?)です",
            r"推しは(.+?)です",
        ]
        unique_facts: List[str] = []
        seen = set()

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                fact = match.group(0).strip()
                if fact in seen or len(fact) < 4 or len(fact) > 120 or not _is_usable_memory_text(fact):
                    continue
                seen.add(fact)
                unique_facts.append(fact)
                self.add_semantic_memory(fact, source="fact")
        return unique_facts

    def summarize_recent_turns(self, turns: List[Dict[str, str]]) -> Optional[str]:
        if len(turns) < EPISODE_SUMMARY_INTERVAL:
            return None
        if len(turns) % EPISODE_SUMMARY_INTERVAL != 0:
            return None

        recent = turns[-EPISODE_SUMMARY_INTERVAL:]
        unique_topics = []
        seen = set()
        for turn in recent:
            text = turn["user"].strip().replace("\n", " ")
            if not _is_usable_memory_text(text) or len(text) < 6:
                continue
            normalized = re.sub(r"[\s\u3000、。，．！？!?…\-ー]+", "", text.lower())
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_topics.append(text[:80])

        if len(unique_topics) < 2:
            return None
        joined = " / ".join(unique_topics[:3])
        return f"会話メモ: {joined}"

    def stats(self) -> Dict[str, int]:
        with self._lock, self._connect() as connection:
            semantic_count = connection.execute("SELECT COUNT(*) FROM semantic_memory").fetchone()[0]
            episode_count = connection.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0]
        return {"semantic_count": semantic_count, "episode_count": episode_count}

    def clear_all(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM semantic_memory")
            connection.execute("DELETE FROM episodic_memory")
            connection.commit()
