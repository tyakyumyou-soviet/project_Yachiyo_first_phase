from __future__ import annotations

from datetime import datetime


def get_current_time() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_current_date() -> str:
    return datetime.now().date().isoformat()
