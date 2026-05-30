from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import CHARACTER_PROFILE_PATH, MAX_CHARACTER_PROFILE_CHARS


@dataclass(frozen=True)
class CharacterProfileSnapshot:
    path: str
    loaded: bool
    chars: int
    truncated: bool
    content: str


_cached_profile: Optional[CharacterProfileSnapshot] = None
_cached_mtime: Optional[float] = None


def load_character_profile() -> CharacterProfileSnapshot:
    global _cached_mtime, _cached_profile

    path = CHARACTER_PROFILE_PATH
    mtime = _safe_mtime(path)
    if _cached_profile is not None and _cached_mtime == mtime:
        return _cached_profile

    if mtime is None:
        snapshot = CharacterProfileSnapshot(
            path=str(path),
            loaded=False,
            chars=0,
            truncated=False,
            content="(no character profile file found)",
        )
        _cached_profile = snapshot
        _cached_mtime = None
        return snapshot

    text = path.read_text(encoding="utf-8").strip()
    truncated = len(text) > MAX_CHARACTER_PROFILE_CHARS
    if truncated:
        text = text[: MAX_CHARACTER_PROFILE_CHARS - 3].rstrip() + "..."

    snapshot = CharacterProfileSnapshot(
        path=str(path),
        loaded=True,
        chars=len(text),
        truncated=truncated,
        content=text,
    )
    _cached_profile = snapshot
    _cached_mtime = mtime
    return snapshot


def character_profile_stats() -> dict:
    snapshot = load_character_profile()
    return {
        "path": snapshot.path,
        "loaded": snapshot.loaded,
        "chars": snapshot.chars,
        "truncated": snapshot.truncated,
    }


def _safe_mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None
