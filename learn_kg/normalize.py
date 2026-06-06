from __future__ import annotations

from typing import Any


def ensure_list(raw: Any, *keys: str) -> list[Any]:
    """Normalize common LLM JSON shapes to a list.

    JSON mode guarantees parseable JSON, not a stable top-level shape. The model
    may return a bare list, {"items": [...]}, {"semantics": [...]}, or a single
    object. This keeps downstream model validation focused on item content.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in keys:
            value = raw.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return [value]
            if value is not None and key != "items":
                return [value]
        for key in ("items", "results", "data", "links", "decisions", "findings", "semantics", "categories"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return [value]
        # Treat a dict with payload fields as one item instead of iterating keys.
        return [raw]
    return [raw]
