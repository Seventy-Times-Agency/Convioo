"""Чинит JSON, оборванный на середине (ответ модели упёрся в лимит)."""

from __future__ import annotations

import json
from typing import Any


def repair_truncated_json(text: str) -> dict[str, Any] | None:
    """Ответ оборвался на середине — взять всё до последнего целого
    значения и закрыть открытые скобки."""
    stack: list[str] = []
    in_str = esc = False
    cuts: list[tuple[int, str]] = []
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
            cuts.append((i + 1, "".join(reversed(stack))))
    for pos, closers in reversed(cuts):
        try:
            data = json.loads(text[:pos] + closers)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None
