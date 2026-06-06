from __future__ import annotations

from pathlib import Path
from .models import ProjectData, SourceFile, AuditReportMaterial, ProjectSpec

DEFAULT_EXCLUDES = {"node_modules", "lib", "out", "cache", ".git", "artifacts", "broadcast"}
SOURCE_EXTS = {".sol": "solidity", ".move": "move", ".vy": "vyper", ".md": "markdown"}


def should_exclude(path: Path) -> bool:
    return any(part in DEFAULT_EXCLUDES for part in path.parts)


def read_source_files(root: Path, max_file_bytes: int = 512 * 1024) -> list[SourceFile]:
    files: list[SourceFile] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or should_exclude(p.relative_to(root)):
            continue
        if p.suffix.lower() not in SOURCE_EXTS:
            continue
        try:
            if p.stat().st_size > max_file_bytes:
                continue
            content = p.read_text(errors="ignore")
        except Exception:
            continue
        files.append(SourceFile(path=str(p.relative_to(root)), content=content, language=SOURCE_EXTS[p.suffix.lower()]))
    return files


def infer_language(files: list[SourceFile]) -> str:
    langs = {f.language for f in files if f.language in {"solidity", "move"}}
    if langs == {"move"}:
        return "move"
    if len(langs) > 1:
        return "mixed"
    return "solidity"


def load_audit_report(path: Path | None) -> AuditReportMaterial | None:
    if path is None or not path.exists():
        return None
    if path.is_file():
        txt = path.read_text(errors="ignore")
        return AuditReportMaterial(content=txt) if txt.strip() else None
    parts = []
    for p in sorted(path.rglob("*.md")):
        parts.append(f"## Report File: {p.relative_to(path)}\n\n{p.read_text(errors='ignore')}")
    return AuditReportMaterial(content="\n\n".join(parts)) if parts else None


def load_project(spec: ProjectSpec, report_path: Path | None = None) -> ProjectData:
    root = spec.path.resolve()
    files = read_source_files(root)
    return ProjectData(name=spec.name, platform_id=spec.platform_id, root_dir=root, source_language=infer_language(files), source_files=files, audit_report=load_audit_report(report_path))


def parse_reports(report_specs: list[str] | None) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for spec in report_specs or []:
        name, path = spec.split(":", 1)
        out[name] = Path(path)
    return out
