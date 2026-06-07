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
from .models import ExtractedSemantic, LinkStrength, SemanticMatchDecision
from .semantic_mapper import map_project_semantics_to_historical
from .taxonomy import DeFiCategory, all_defi_categories, coerce_defi_category


@dataclass(frozen=True)
class ChecklistFinding:
    title: str
    severity: str
    root_cause: str
    risk_pattern: str
    exploit_shape: str
    kg_link_strength: str
    kg_evidence: str
    finding_id: int | None = None
    canonical_finding_id: int | None = None


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
class ChecklistCandidate:
    extract_index: int
    match: SemanticMatchDecision
    finding: ChecklistFinding


@dataclass(frozen=True)
class ChecklistDocument:
    project_name: str
    groups: list[ProjectSemanticChecklist] = field(default_factory=list)
    candidate_items_considered: int = 0
    candidate_items_rendered: int = 0
    candidate_items_deduped: int = 0
    candidate_items_trimmed: int = 0

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
        f"- Candidate checklist findings considered: {doc.candidate_items_considered}",
        f"- Candidate checklist findings rendered: {doc.candidate_items_rendered}",
        f"- Candidate checklist findings deduped: {doc.candidate_items_deduped}",
        f"- Candidate checklist findings trimmed by caps: {doc.candidate_items_trimmed}",
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


def fetch_semantic_findings(
    db: HistoricalDatabase,
    semantic_ids: list[int],
    *,
    min_kg_link_strength: LinkStrength | str | None = None,
) -> dict[int, list[ChecklistFinding]]:
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
                s.AuditFinding.id,
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
        canonical_finding_ids = _finding_canonical_ids(session, [row[3] for row in rows])

    seen_by_root: dict[int, dict[object, int]] = {semantic_id: {} for semantic_id in ids}
    for semantic_id, strength, evidence, finding_id, title, severity, root_cause, patterns, exploits in rows:
        if not _meets_min_strength(strength, min_kg_link_strength):
            continue
        root_id = root_by_member.get(int(semantic_id))
        if root_id is None:
            continue
        finding = ChecklistFinding(
            title=title,
            severity=severity,
            root_cause=root_cause,
            risk_pattern=patterns,
            exploit_shape=exploits,
            kg_link_strength=strength,
            kg_evidence=evidence,
            finding_id=int(finding_id) if finding_id is not None else None,
            canonical_finding_id=canonical_finding_ids.get(int(finding_id)) if finding_id is not None else None,
        )
        dedupe_key = _finding_dedupe_key(finding)
        seen = seen_by_root.setdefault(root_id, {})
        existing_index = seen.get(dedupe_key)
        if existing_index is None:
            seen[dedupe_key] = len(out[root_id])
            out[root_id].append(finding)
            continue
        existing = out[root_id][existing_index]
        if _prefer_finding_link(finding, existing):
            out[root_id][existing_index] = finding
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


def _finding_canonical_ids(session, finding_ids: list[int]) -> dict[int, int]:
    """Map each finding id to the root/canonical finding it was merged into."""
    ids = _dedupe_ints(finding_ids)
    canonical = {finding_id: finding_id for finding_id in ids}
    unresolved = set(ids)
    seen_frontier: set[int] = set()
    while unresolved:
        unresolved -= seen_frontier
        if not unresolved:
            break
        seen_frontier.update(unresolved)
        rows = session.execute(
            select(s.FindingMerge.from_finding_id, s.FindingMerge.to_finding_id)
            .where(s.FindingMerge.from_finding_id.in_(sorted(unresolved)))
        ).all()
        next_unresolved: set[int] = set()
        for child_id, parent_id in rows:
            child_id = int(child_id)
            parent_id = int(parent_id)
            for original_id, current_id in list(canonical.items()):
                if current_id == child_id:
                    canonical[original_id] = parent_id
                    next_unresolved.add(parent_id)
        unresolved = next_unresolved
    return canonical


def _strength_value(strength: object) -> str:
    return str(strength.value if hasattr(strength, "value") else strength)


def _strength_rank(strength: object) -> int:
    return {LinkStrength.Low.value: 1, LinkStrength.Medium.value: 2, LinkStrength.High.value: 3}.get(_strength_value(strength), 0)


def _severity_rank(severity: object) -> int:
    return {"Low": 1, "Medium": 2, "High": 3}.get(_text(severity), 0)


def _evidence_specificity(value: object) -> int:
    text = _text(value)
    if not text:
        return 0
    words = [part for part in text.replace("/", " ").replace("_", " ").split() if part]
    return len(set(words)) * 2 + min(len(text), 500)


def _meets_min_strength(strength: object, minimum: LinkStrength | str | None) -> bool:
    if minimum is None:
        return True
    return _strength_rank(strength) >= _strength_rank(minimum) > 0


def _finding_dedupe_key(finding: ChecklistFinding) -> tuple[str, object]:
    if finding.canonical_finding_id is not None:
        return ("id", finding.canonical_finding_id)
    if finding.finding_id is not None:
        return ("id", finding.finding_id)
    return ("text", (_text(finding.title), _text(finding.root_cause)))


def _prefer_finding_link(candidate: ChecklistFinding, existing: ChecklistFinding) -> bool:
    candidate_rank = _strength_rank(candidate.kg_link_strength)
    existing_rank = _strength_rank(existing.kg_link_strength)
    if candidate_rank != existing_rank:
        return candidate_rank > existing_rank
    return len(_text(candidate.kg_evidence)) > len(_text(existing.kg_evidence))


def _indexes_with_checklist_matches(matches: list[SemanticMatchDecision], minimum: LinkStrength | str | None = LinkStrength.Medium) -> set[int]:
    return {match.extract_index for match in matches if _meets_min_strength(match.strength, minimum)}


def _dedupe_checklist_matches(
    matches: list[SemanticMatchDecision],
    *,
    min_match_strength: LinkStrength | str | None = LinkStrength.Medium,
) -> list[SemanticMatchDecision]:
    by_pair: dict[tuple[int, int], SemanticMatchDecision] = {}
    for match in matches:
        if not _meets_min_strength(match.strength, min_match_strength):
            continue
        key = (match.extract_index, match.historical_id)
        existing = by_pair.get(key)
        if existing is None:
            by_pair[key] = match
            continue
        old_rank = _strength_rank(existing.strength)
        new_rank = _strength_rank(match.strength)
        if new_rank > old_rank or (new_rank == old_rank and len(match.evidence) > len(existing.evidence)):
            by_pair[key] = match
    return sorted(by_pair.values(), key=lambda item: (item.extract_index, item.historical_id))


def _candidate_sort_key(candidate: ChecklistCandidate) -> tuple[int, int, int, int, int, int]:
    finding_id = candidate.finding.finding_id if candidate.finding.finding_id is not None else -1
    return (
        _strength_rank(candidate.match.strength),
        _strength_rank(candidate.finding.kg_link_strength),
        _severity_rank(candidate.finding.severity),
        _evidence_specificity(candidate.finding.kg_evidence),
        _evidence_specificity(candidate.match.evidence),
        -finding_id,
    )


def _sort_candidates(candidates: list[ChecklistCandidate]) -> list[ChecklistCandidate]:
    return sorted(candidates, key=_candidate_sort_key, reverse=True)


def _plan_checklist_candidates(
    matches: list[SemanticMatchDecision],
    findings_by_semantic: dict[int, list[ChecklistFinding]],
    *,
    max_items: int,
    max_matches_per_extract: int,
    max_findings_per_historical: int,
    max_findings_per_extract: int,
    dedupe_findings: bool,
) -> tuple[dict[int, dict[int, list[ChecklistFinding]]], int, int, int, int]:
    """Rank finding candidates globally, apply per-extract/per-historical caps, then global cap."""
    candidates: list[ChecklistCandidate] = []
    for match in matches:
        findings = _sort_findings(findings_by_semantic.get(match.historical_id, []))
        for finding in findings:
            candidates.append(ChecklistCandidate(match.extract_index, match, finding))

    considered = len(candidates)
    sorted_candidates = _sort_candidates(candidates)
    selected: list[ChecklistCandidate] = []
    deduped = 0
    seen_findings: set[tuple[str, object]] = set()
    matches_by_extract: dict[int, set[int]] = {}
    findings_by_extract: dict[int, int] = {}
    findings_by_pair: dict[tuple[int, int], int] = {}

    for candidate in sorted_candidates:
        if dedupe_findings:
            dedupe_key = _finding_dedupe_key(candidate.finding)
            if dedupe_key in seen_findings:
                deduped += 1
                continue
        else:
            dedupe_key = None

        extract_matches = matches_by_extract.setdefault(candidate.extract_index, set())
        pair_key = (candidate.extract_index, candidate.match.historical_id)
        is_new_match_for_extract = candidate.match.historical_id not in extract_matches
        if max_items >= 0 and len(selected) >= max_items:
            continue
        if max_matches_per_extract >= 0 and is_new_match_for_extract and len(extract_matches) >= max_matches_per_extract:
            continue
        if max_findings_per_extract >= 0 and findings_by_extract.get(candidate.extract_index, 0) >= max_findings_per_extract:
            continue
        if max_findings_per_historical >= 0 and findings_by_pair.get(pair_key, 0) >= max_findings_per_historical:
            continue

        selected.append(candidate)
        extract_matches.add(candidate.match.historical_id)
        findings_by_extract[candidate.extract_index] = findings_by_extract.get(candidate.extract_index, 0) + 1
        findings_by_pair[pair_key] = findings_by_pair.get(pair_key, 0) + 1
        if dedupe_key is not None:
            seen_findings.add(dedupe_key)

    planned: dict[int, dict[int, list[ChecklistFinding]]] = {}
    for candidate in _sort_candidates(selected):
        planned.setdefault(candidate.extract_index, {}).setdefault(candidate.match.historical_id, []).append(candidate.finding)

    trimmed = max(0, considered - len(selected) - deduped)
    return planned, considered, len(selected), deduped, trimmed


def _sort_findings(findings: list[ChecklistFinding]) -> list[ChecklistFinding]:
    return sorted(
        findings,
        key=lambda finding: (
            _strength_rank(finding.kg_link_strength),
            _severity_rank(finding.severity),
            _evidence_specificity(finding.kg_evidence),
            -(finding.finding_id if finding.finding_id is not None else -1),
        ),
        reverse=True,
    )


def _sort_matches(matches: list[SemanticMatchDecision]) -> list[SemanticMatchDecision]:
    return sorted(
        matches,
        key=lambda match: (
            _strength_rank(match.strength),
            _evidence_specificity(match.evidence),
            -match.historical_id,
        ),
        reverse=True,
    )


async def build_project_checklist(
    db: HistoricalDatabase,
    llm: LLMClient,
    project,
    *,
    config: LLMConfig | None = None,
    min_kg_link_strength: LinkStrength | str | None = None,
    logger: Callable[[str], None] | None = None,
) -> ChecklistDocument:
    """Analyze a project and build a read-only historical checklist document."""
    config = config or LLMConfig()
    min_match_strength = getattr(config, "min_match_strength", LinkStrength.Medium.value)
    if min_kg_link_strength is None:
        min_kg_link_strength = getattr(config, "min_kg_link_strength", None)
    max_items = int(getattr(config, "max_items", 100))
    max_matches_per_extract = int(getattr(config, "max_matches_per_extract", 5))
    max_findings_per_historical = int(getattr(config, "max_findings_per_historical", 3))
    max_findings_per_extract = int(getattr(config, "max_findings_per_extract", 12))
    dedupe_findings = bool(getattr(config, "dedupe_findings", True))
    _log(logger, f"[cyan]stage[/cyan] categorize project={project.name}")
    categories = await categorize_project(llm, project)
    _log(logger, "[green]done[/green] categorize categories=" + ",".join(c.value if hasattr(c, "value") else str(c) for c in categories))

    _log(logger, f"[cyan]stage[/cyan] extract semantics budget={config.input_token_budget}")
    semantics = await extract_semantics(llm, project, categories, config.input_token_budget, config.model)
    _log(logger, f"[green]done[/green] extract semantics={len(semantics)}")

    semantic_categories = sorted({coerce_defi_category(sem.category).value for sem in semantics})
    pass1_categories = sorted({*semantic_categories, DeFiCategory.Others.value})
    pass1_candidates = db.canonical_semantics_with_children_for_categories(pass1_categories)
    _log(logger, f"[cyan]stage[/cyan] map semantics pass=1 candidates={len(pass1_candidates)} batch_size={config.map_batch_size}")
    match_results = await map_project_semantics_to_historical(
        llm,
        semantics,
        pass1_candidates,
        batch_size=config.map_batch_size,
        max_children=config.map_max_rendered_children,
        logger=logger,
    )

    strong_indexes = _indexes_with_checklist_matches(match_results, min_match_strength)
    unmatched_indexes = [idx for idx in range(len(semantics)) if idx not in strong_indexes]
    fallback_categories = sorted({cat.value for cat in all_defi_categories()} - set(pass1_categories))
    if unmatched_indexes and fallback_categories:
        pass2_candidates = db.canonical_semantics_with_children_for_categories(fallback_categories)
        _log(logger, f"[cyan]stage[/cyan] map semantics pass=2 unmatched={len(unmatched_indexes)} candidates={len(pass2_candidates)} batch_size={config.map_batch_size}")
        match_results.extend(await map_project_semantics_to_historical(
            llm,
            semantics,
            pass2_candidates,
            batch_size=config.map_batch_size,
            max_children=config.map_max_rendered_children,
            extract_indexes=unmatched_indexes,
            logger=logger,
        ))

    checklist_matches = _dedupe_checklist_matches(match_results, min_match_strength=min_match_strength)
    _log(logger, f"[green]done[/green] map semantics matched={len(checklist_matches)}")

    matched_ids = _dedupe_ints([match.historical_id for match in checklist_matches])
    names_by_id = fetch_historical_semantic_names(db, matched_ids)
    findings_by_semantic = fetch_semantic_findings(db, matched_ids, min_kg_link_strength=min_kg_link_strength)
    planned_findings, candidate_count, rendered_count, deduped_count, trimmed_count = _plan_checklist_candidates(
        checklist_matches,
        findings_by_semantic,
        max_items=max_items,
        max_matches_per_extract=max_matches_per_extract,
        max_findings_per_historical=max_findings_per_historical,
        max_findings_per_extract=max_findings_per_extract,
        dedupe_findings=dedupe_findings,
    )
    _log(
        logger,
        "[green]done[/green] plan checklist "
        f"candidates={candidate_count} rendered={rendered_count} deduped={deduped_count} trimmed={trimmed_count}",
    )

    matches_by_extract: dict[int, list[SemanticMatchDecision]] = {}
    for match in checklist_matches:
        matches_by_extract.setdefault(match.extract_index, []).append(match)

    groups: list[ProjectSemanticChecklist] = []
    for idx, semantic in enumerate(semantics):
        semantic_matches = _sort_matches(matches_by_extract.get(idx, []))
        selected_for_extract = planned_findings.get(idx, {})
        if not semantic_matches:
            groups.append(ProjectSemanticChecklist(semantic=semantic, matched_semantics=[]))
            continue

        renderable_matches = [match for match in semantic_matches if selected_for_extract.get(match.historical_id)]
        if not renderable_matches:
            # Keep one best empty historical match as a useful manual-review anchor when
            # matching succeeded but no linked finding survived KG-strength filtering.
            # Do not render every trimmed/capped empty match, or caps would not bound output.
            renderable_matches = semantic_matches[:1]

        matches = [
            MatchedHistoricalSemantic(
                semantic_id=match.historical_id,
                name=names_by_id.get(match.historical_id, f"#{match.historical_id}"),
                match_strength=match.strength.value if hasattr(match.strength, "value") else str(match.strength),
                match_evidence=match.evidence,
                findings=selected_for_extract.get(match.historical_id, []),
            )
            for match in renderable_matches
        ]
        groups.append(ProjectSemanticChecklist(semantic=semantic, matched_semantics=matches))

    return ChecklistDocument(
        project_name=project.name,
        groups=groups,
        candidate_items_considered=candidate_count,
        candidate_items_rendered=rendered_count,
        candidate_items_deduped=deduped_count,
        candidate_items_trimmed=trimmed_count,
    )


async def export_project_checklist(
    db: HistoricalDatabase,
    llm: LLMClient,
    project,
    out: Path,
    *,
    config: LLMConfig | None = None,
    min_kg_link_strength: LinkStrength | str | None = None,
    logger: Callable[[str], None] | None = None,
) -> ChecklistDocument:
    doc = await build_project_checklist(db, llm, project, config=config, min_kg_link_strength=min_kg_link_strength, logger=logger)
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
