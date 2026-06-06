from __future__ import annotations
from pathlib import Path


class DebugStore:
    def __init__(self, root: str | Path | None = ".runs", enabled: bool = True):
        self.root = Path(root) if root else None
        self.enabled = enabled and self.root is not None

    def write(self, project: str, name: str, content: str) -> None:
        if not self.enabled or self.root is None:
            return
        d = self.root / project
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(content)
