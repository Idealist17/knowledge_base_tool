from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select

from . import schema as s
from .config import LLMConfig
from .db import HistoricalDatabase
from .extract import categorize_project, extract_semantics
from .llm_client import LLMClient
from .merge import merge_semantics
from .models import ExtractedSemantic
from .taxonomy import coerce_defi_category


@dataclass(frozen=True)
class ChecklistFinding:
    title: str
    severity: str
    root_cause: str
    risk_pattern: str
    exploit_shape: str
    kg_link_strength: str
    kg_evidence: str


@dataclass(frozen=True)
class MatchedHistoricalSemantic:
    semantic_id: int | None
    name: str
    match_strength: str
    match_evidence: str
    findings: list[ChecklistFinding] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectSemanticChecklist:
    semantic: ExtractedSemantic
    matched_semantics: list[MatchedHistoricalSemantic] = field(default_factory=list)


@dataclass(frozen=True)
class ChecklistDocument:
    project_name: str
    groups: list[ProjectSemanticChecklist] = field(default_factory=list)

    @property
    def project_semantics_analyzed(self) -> int:
        return len(self.groups)

    @property
    def historical_semantics_matched(self) -> int:
        return len({match.semantic_id for group in self.groups for match in group.matched_semantics if match.semantic_id is not None})

    @property
    def checklist_items(self) -> int:
        total = 0
        for group in self.groups:
            if not group.matched_semantics:
                total += 1
                continue
            for match in group.matched_semantics:
                total += len(match.findings) if match.findings else 1
        return total


def _text(value: object, default: str = "") -> str:
    text = "" if value is None else str(value)
    text = text.strip()
    return text or default


def _category_text(value: object) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _single_line(value: object, default: str = "") -> str:
    """Collapse untrusted heading / checkbox text to one Markdown line."""
    return " ".join(_text(value, default).split())


def _bullet(label: str, value: object, *, default: str = "") -> list[str]:
    text = _text(value, default)
    if "\n" not in text:
        return [f"- {label}: {text}"]
    first, *rest = text.splitlines()
    lines = [f"- {label}: {first}"]
    lines.extend(f"  {line}" for line in rest)
    return lines


def _sub_bullet(label: str, value: object, *, default: str = "") -> list[str]:
    text = _text(value, default)
    if "\n" not in text:
        return [f"  - {label}: {text}"]
    first, *rest = text.splitlines()
    lines = [f"  - {label}: {first}"]
    lines.extend(f"    {line}" for line in rest)
    return lines


def render_checklist_markdown(doc: ChecklistDocument) -> str:
    """Render a checklist document in the fixed Markdown structure."""
    lines: list[str] = [
        f"# Audit Checklist: {_single_line(doc.project_name)}",
        "",
        "## Summary",
        f"- Project semantics analyzed: {doc.project_semantics_analyzed}",
        f"- Historical semantics matched: {doc.historical_semantics_matched}",
        f"- Checklist items: {doc.checklist_items}",
    ]

    if not doc.groups:
        lines.extend([
            "",
            "## No project semantics extracted",
            "- [ ] Manually review this project; semantic extraction produced no checklist groups.",
        ])
        return "\n".join(lines).rstrip() + "\n"

    for group in doc.groups:
        sem = group.semantic
        matches = group.matched_semantics or [
            MatchedHistoricalSemantic(
                semantic_id=None,
                name="None",
                match_strength="None",
                match_evidence="No historical semantic matched.",
                findings=[],
            )
        ]
        lines.extend([
            "",
            f"## {_single_line(sem.name, 'Unnamed semantic')}",
        ])
        lines.extend(_bullet("Category", _category_text(sem.category), default="Others"))
        lines.extend(_bullet("Definition", sem.definition, default=""))

        for match in matches:
            lines.extend([
                "",
                f"### Matched historical semantic: {_single_line(match.name, 'None')}",
            ])
            if match.semantic_id is not None:
                lines.extend(_bullet("Match strength", match.match_strength, default="High"))
                lines.extend(_bullet("Match evidence", match.match_evidence, default=""))
            lines.extend([
                "",
                "#### Checklist",
            ])
            if not match.findings:
                if match.semantic_id is None:
                    lines.append("- [ ] Manually review this semantic; no historical finding links were matched.")
                else:
                    lines.append("- [ ] Manually review this semantic; a historical semantic matched, but no linked findings were found.")
                continue
            for finding in match.findings:
                lines.append(f"- [ ] Check whether: {_single_line(finding.title, 'Untitled finding')}")
                lines.extend(_sub_bullet("Severity", finding.severity, default="Medium"))
                lines.extend(_sub_bullet("Historical root cause", finding.root_cause, default=""))
                lines.extend(_sub_bullet("Risk pattern", finding.risk_pattern, default=""))
                lines.extend(_sub_bullet("Exploit shape", finding.exploit_shape, default=""))
                lines.extend(_sub_bullet("KG link strength", finding.kg_link_strength, default=""))
                lines.extend(_sub_bullet("KG evidence", finding.kg_evidence, default=""))

    return "\n".join(lines).rstrip() + "\n"


def fetch_historical_semantic_names(db: HistoricalDatabase, semantic_ids: list[int]) -> dict[int, str]:
    ids = _dedupe_ints(semantic_ids)
    if not ids:
        return {}
    with db.session() as session:
        rows = session.execute(
            select(s.SemanticNode.id, s.SemanticNode.name).where(s.SemanticNode.id.in_(ids))
        ).all()
    return {int(semantic_id): name for semantic_id, name in rows}


def fetch_semantic_findings(db: HistoricalDatabase, semantic_ids: list[int]) -> dict[int, list[ChecklistFinding]]:
    """Read linked findings for historical semantic ids, including semantics merged into them."""
    ids = _dedupe_ints(semantic_ids)
    out: dict[int, list[ChecklistFinding]] = {semantic_id: [] for semantic_id in ids}
    if not ids:
        return out

    cluster_by_root = _semantic_cluster_ids(db, ids)
    root_by_member = {
        member_id: root_id
        for root_id, member_ids in cluster_by_root.items()
        for member_id in member_ids
    }
    query_ids = sorted(root_by_member)

    with db.session() as session:
        rows = session.execute(
            select(
                s.SemanticFindingLink.semantic_node_id,
                s.SemanticFindingLink.strength,
                s.SemanticFindingLink.evidence,
                s.AuditFinding.title,
                s.AuditFinding.severity,
                s.AuditFinding.root_cause,
                s.AuditFinding.patterns,
                s.AuditFinding.exploits,
            )
            .join(s.AuditFinding, s.AuditFinding.id == s.SemanticFindingLink.audit_finding_id)
            .where(s.SemanticFindingLink.semantic_node_id.in_(query_ids))
            .order_by(s.SemanticFindingLink.semantic_node_id, s.AuditFinding.id)
        ).all()

    for semantic_id, strength, evidence, title, severity, root_cause, patterns, exploits in rows:
        root_id = root_by_member.get(int(semantic_id))
        if root_id is None:
            continue
        out[root_id].append(
            ChecklistFinding(
                title=title,
                severity=severity,
                root_cause=root_cause,
                risk_pattern=patterns,
                exploit_shape=exploits,
                kg_link_strength=strength,
                kg_evidence=evidence,
            )
        )
    return out


def _semantic_cluster_ids(db: HistoricalDatabase, root_ids: list[int]) -> dict[int, set[int]]:
    """Return each canonical/root semantic plus all semantics merged into it."""
    clusters: dict[int, set[int]] = {root_id: {root_id} for root_id in root_ids}
    frontier = set(root_ids)
    with db.session() as session:
        while frontier:
            rows = session.execute(
                select(s.SemanticMerge.from_semantic_id, s.SemanticMerge.to_semantic_id)
                .where(s.SemanticMerge.to_semantic_id.in_(sorted(frontier)))
            ).all()
            next_frontier: set[int] = set()
            for child_id, parent_id in rows:
                child_id = int(child_id)
                parent_id = int(parent_id)
                for root_id, members in clusters.items():
                    if parent_id in members and child_id not in members:
                        members.add(child_id)
                        next_frontier.add(child_id)
            frontier = next_frontier
    return clusters


async def build_project_checklist(
    db: HistoricalDatabase,
    llm: LLMClient,
    project,
    *,
    config: LLMConfig | None = None,
    logger: Callable[[str], None] | None = None,
) -> ChecklistDocument:
    """Analyze a project and build a read-only historical checklist document."""
    config = config or LLMConfig()
    _log(logger, f"[cyan]stage[/cyan] categorize project={project.name}")
    categories = await categorize_project(llm, project)
    _log(logger, "[green]done[/green] categorize categories=" + ",".join(c.value if hasattr(c, "value") else str(c) for c in categories))

    _log(logger, f"[cyan]stage[/cyan] extract semantics budget={config.input_token_budget}")
    semantics = await extract_semantics(llm, project, categories, config.input_token_budget, config.model)
    _log(logger, f"[green]done[/green] extract semantics={len(semantics)}")

    semantic_categories = sorted({coerce_defi_category(sem.category).value for sem in semantics})
    canonicals = db.canonical_semantics_with_children_for_categories(semantic_categories)
    _log(logger, f"[cyan]stage[/cyan] merge semantics canon_candidates={len(canonicals)}")
    merge_results = await merge_semantics(llm, semantics, canonicals)
    _log(logger, f"[green]done[/green] merge semantics matched={sum(1 for r in merge_results if r.decision.target_ids)}")

    matched_ids = _dedupe_ints([tid for result in merge_results for tid in result.decision.target_ids])
    names_by_id = fetch_historical_semantic_names(db, matched_ids)
    findings_by_semantic = fetch_semantic_findings(db, matched_ids)

    groups: list[ProjectSemanticChecklist] = []
    for result in merge_results:
        if not result.decision.target_ids:
            groups.append(ProjectSemanticChecklist(semantic=result.semantic, matched_semantics=[]))
            continue
        matches = [
            MatchedHistoricalSemantic(
                semantic_id=tid,
                name=names_by_id.get(tid, f"#{tid}"),
                match_strength="High",
                match_evidence=result.decision.reason,
                findings=findings_by_semantic.get(tid, []),
            )
            for tid in result.decision.target_ids
        ]
        groups.append(ProjectSemanticChecklist(semantic=result.semantic, matched_semantics=matches))

    return ChecklistDocument(project_name=project.name, groups=groups)


async def export_project_checklist(
    db: HistoricalDatabase,
    llm: LLMClient,
    project,
    out: Path,
    *,
    config: LLMConfig | None = None,
    logger: Callable[[str], None] | None = None,
) -> ChecklistDocument:
    doc = await build_project_checklist(db, llm, project, config=config, logger=logger)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_checklist_markdown(doc), encoding="utf-8")
    return doc


def _dedupe_ints(values) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _log(logger: Callable[[str], None] | None, message: str) -> None:
    if logger:
        logger(message)
