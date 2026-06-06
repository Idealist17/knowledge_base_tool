from __future__ import annotations
from collections.abc import Callable
from .llm_client import LLMClient
from .models import ExtractedSemantic, ExtractedFinding, InProjectLink, GlobalLink
from . import prompts
from .db import HistoricalDatabase
from .normalize import ensure_list


def _dedupe_links(links: list[InProjectLink]) -> list[InProjectLink]:
    seen = set()
    out = []
    for link in links:
        key = (link.semantic_index, link.finding_index)
        if key in seen:
            continue
        seen.add(key)
        out.append(link)
    return out


async def in_project_link(llm: LLMClient, semantics: list[ExtractedSemantic], findings: list[ExtractedFinding]) -> list[InProjectLink]:
    if not semantics or not findings:
        return []
    raw = await llm.json(prompts.in_project_link_prompt(semantics, findings), schema_name="in_project_link")
    raw = ensure_list(raw, "items", "links")
    links = []
    for x in raw or []:
        if not isinstance(x, dict):
            continue
        try:
            link = InProjectLink.model_validate(x)
        except Exception:
            continue
        if 0 <= link.semantic_index < len(semantics) and 0 <= link.finding_index < len(findings):
            links.append(link)
    covered = {l.finding_index for l in links}
    for i in range(len(findings)):
        if i not in covered:
            links.append(InProjectLink(semantic_index=0, finding_index=i, strength="Low", evidence="Fallback low-confidence link to first extracted semantic for coverage."))
    return _dedupe_links(links)


async def global_link(llm: LLMClient, db: HistoricalDatabase, logger: Callable[[str], None] | None = None) -> list[GlobalLink]:
    findings = db.list_pending_findings_for_linking()
    semantics = db.list_all_canonical_semantics()
    if logger:
        logger(f"[dim]global link candidates[/dim] pending_findings={len(findings)} canonical_semantics={len(semantics)}")
    if not findings or not semantics:
        return []
    f_payload = [{"id": f.id, "title": f.title, "root_cause": f.root_cause, "description": f.description} for f in findings]
    s_payload = [{"id": s.id, "name": s.name, "definition": s.definition, "description": s.description, "category": s.category} for s in semantics]
    raw = await llm.json(prompts.global_link_prompt(f_payload, s_payload), schema_name="global_link")
    raw = ensure_list(raw, "items", "links")
    raw_count = len(raw)
    finding_ids = {f.id for f in findings}
    semantic_ids = {s.id for s in semantics}
    edges = []
    for x in raw or []:
        if not isinstance(x, dict):
            continue
        try:
            edge = GlobalLink.model_validate(x)
        except Exception:
            continue
        if edge.finding_id in finding_ids and edge.semantic_id in semantic_ids:
            edges.append(edge)
    if logger:
        logger(f"[dim]global link parsed[/dim] raw={raw_count} valid={len(edges)}")
    if edges:
        db.append_semantic_finding_links(edges)
        db.mark_findings_linked(sorted({e.finding_id for e in edges}))
    return edges
