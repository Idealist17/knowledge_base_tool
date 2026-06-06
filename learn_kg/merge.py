from __future__ import annotations
from .llm_client import LLMClient
from .models import ExtractedSemantic, ExtractedFinding, SemanticMergeDecision, FindingMergeDecision, SemanticMergeResult, FindingMergeResult
from . import prompts
from .normalize import ensure_list


def _match_key(text: str) -> str:
    return " ".join(str(text).lower().split())


async def merge_semantics(llm: LLMClient, new_semantics: list[ExtractedSemantic], canonicals: list[dict]) -> list[SemanticMergeResult]:
    if not new_semantics: return []
    raw = await llm.json(prompts.semantic_merge_prompt(new_semantics, canonicals), schema_name="semantic_merge")
    raw = ensure_list(raw, "items", "decisions")
    canonical_ids = {int(c["id"]) for c in canonicals if "id" in c}
    by_name = {}
    for d in raw or []:
        if not isinstance(d, dict):
            continue
        try:
            dec = SemanticMergeDecision.model_validate(d)
        except Exception:
            continue
        dec.target_ids = [tid for tid in dec.target_ids if tid in canonical_ids]
        by_name[_match_key(dec.new_semantic_name)] = dec
    out = []
    for sem in new_semantics:
        dec = by_name.get(_match_key(sem.name)) or SemanticMergeDecision(new_semantic_name=sem.name, target_ids=[], reason="default new")
        out.append(SemanticMergeResult(semantic=sem, decision=dec))
    return out


async def merge_findings(llm: LLMClient, new_findings: list[ExtractedFinding], canonicals: list[dict]) -> list[FindingMergeResult]:
    if not new_findings: return []
    raw = await llm.json(prompts.finding_merge_prompt(new_findings, canonicals), schema_name="finding_merge")
    raw = ensure_list(raw, "items", "decisions")
    canonical_ids = {int(c["id"]) for c in canonicals if "id" in c}
    by_title = {}
    for d in raw or []:
        if not isinstance(d, dict):
            continue
        try:
            dec = FindingMergeDecision.model_validate(d)
        except Exception:
            continue
        dec.target_ids = [tid for tid in dec.target_ids if tid in canonical_ids]
        by_title[_match_key(dec.new_finding_title)] = dec
    out = []
    for f in new_findings:
        dec = by_title.get(_match_key(f.title)) or FindingMergeDecision(new_finding_title=f.title, target_ids=[], reason="default new")
        out.append(FindingMergeResult(finding=f, decision=dec))
    return out
