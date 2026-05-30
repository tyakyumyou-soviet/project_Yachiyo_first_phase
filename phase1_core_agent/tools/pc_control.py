from __future__ import annotations

from pathlib import Path
from typing import List

from config import ALLOWED_FILE_ROOTS, READ_FILE_MAX_CHARS


class FileAccessError(RuntimeError):
    pass


def _is_within_roots(target: Path) -> bool:
    for root in ALLOWED_FILE_ROOTS:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def resolve_path(path: str) -> Path:
    target = Path(path)
    if not target.is_absolute():
        target = ALLOWED_FILE_ROOTS[0] / target
    target = target.expanduser().resolve()
    if not _is_within_roots(target):
        raise FileAccessError(f"Path is outside allowed roots: {target}")
    return target


def read_text_file(path: str) -> str:
    target = resolve_path(path)
    if not target.exists():
        raise FileNotFoundError(str(target))
    text = target.read_text(encoding="utf-8")
    return text[:READ_FILE_MAX_CHARS]


def write_text_file(path: str, content: str) -> str:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {target}"


def delete_file(path: str) -> str:
    target = resolve_path(path)
    if not target.exists():
        raise FileNotFoundError(str(target))
    if target.is_dir():
        raise IsADirectoryError(str(target))
    target.unlink()
    return f"Deleted {target}"


def list_directory(path: str = ".") -> str:
    target = resolve_path(path)
    if not target.exists():
        raise FileNotFoundError(str(target))
    if not target.is_dir():
        raise NotADirectoryError(str(target))
    entries: List[str] = []
    for child in sorted(target.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
        label = child.name + ("/" if child.is_dir() else "")
        entries.append(label)
    return "\n".join(entries[:200])
