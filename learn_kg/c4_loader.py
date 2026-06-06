from __future__ import annotations

import re
from pathlib import Path
from .models import ProjectData
from .project_loader import read_source_files, infer_language, load_audit_report


def discover_contest_ids(c4_dir: Path) -> list[int]:
    ids: set[int] = set()
    for base_name in ("contracts", "audits", "reports"):
        base = c4_dir / base_name
        if not base.exists():
            continue
        for p in base.iterdir():
            m = re.search(r"(?:c4-)?(\d+)", p.stem if p.is_file() else p.name)
            if m:
                ids.add(int(m.group(1)))
    return sorted(ids, reverse=True)


def select_contest_ids(c4_dir: Path, c4_ids: str | None = None, skip_ids: str | None = None, limit: int | None = None) -> list[int]:
    if c4_ids:
        ids = [int(x) for x in c4_ids.split(",") if x.strip()]
    else:
        ids = discover_contest_ids(c4_dir)
    skip = {int(x) for x in (skip_ids or "").split(",") if x.strip()}
    ids = [i for i in ids if i not in skip]
    if limit is not None:
        ids = ids[:limit]
    return ids


def _find_contract_dir(c4_dir: Path, cid: int) -> Path:
    candidates = [c4_dir/"contracts"/str(cid), c4_dir/"contracts"/f"c4-{cid}"]
    contracts = c4_dir / "contracts"
    if contracts.exists():
        candidates += [p for p in contracts.iterdir() if p.is_dir() and str(cid) in p.name]
    for c in candidates:
        if c.is_dir():
            return c
    raise FileNotFoundError(f"contracts directory not found for contest {cid}")


def _find_report(c4_dir: Path, cid: int) -> Path | None:
    candidates = []
    for base in ("reports", "audits"):
        b = c4_dir / base
        candidates += [b/f"{cid}.md", b/f"c4-{cid}.md", b/str(cid), b/f"c4-{cid}"]
    for c in candidates:
        if c.exists():
            return c
    return None


def load_c4_project(c4_dir: Path, contest_id: int) -> ProjectData:
    root = _find_contract_dir(c4_dir, contest_id).resolve()
    files = read_source_files(root)
    report = load_audit_report(_find_report(c4_dir, contest_id))
    return ProjectData(name=f"c4-{contest_id}", platform_id=f"c4-{contest_id}", root_dir=root, source_language=infer_language(files), source_files=files, audit_report=report)
