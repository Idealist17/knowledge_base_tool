from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from . import prompts
from .llm_client import LLMClient
from .models import ExtractedSemantic, LinkStrength, SemanticMatchDecision
from .normalize import ensure_list

_STRENGTH_RANK = {LinkStrength.Low: 1, LinkStrength.Medium: 2, LinkStrength.High: 3}


def _coerce_strength(value: object) -> LinkStrength | None:
    try:
        return LinkStrength(value)
    except ValueError:
        return None


def _indexed_semantics(semantics: Sequence[ExtractedSemantic], indexes: Sequence[int] | None = None) -> list[dict[str, Any]]:
    if indexes is None:
        iterator = enumerate(semantics)
    else:
        iterator = ((idx, semantics[idx]) for idx in indexes)
    out: list[dict[str, Any]] = []
    for idx, sem in iterator:
        out.append({
            "extract_index": idx,
            "category": sem.category.value if hasattr(sem.category, "value") else str(sem.category),
            "name": sem.name,
            "definition": sem.definition,
            "description": sem.description,
        })
    return out


def _adopt(existing: SemanticMatchDecision | None, candidate: SemanticMatchDecision) -> SemanticMatchDecision:
    if existing is None:
        return candidate
    old_rank = _STRENGTH_RANK.get(existing.strength, 0)
    new_rank = _STRENGTH_RANK.get(candidate.strength, 0)
    if new_rank > old_rank:
        return candidate
    if new_rank == old_rank and len(candidate.evidence) > len(existing.evidence):
        return candidate
    return existing


async def map_project_semantics_to_historical(
    llm: LLMClient,
    semantics: Sequence[ExtractedSemantic],
    historicals: Sequence[dict],
    *,
    batch_size: int = 16,
    max_children: int = 5,
    max_rendered_children: int | None = None,
    extract_indexes: Sequence[int] | None = None,
    logger: Callable[[str], None] | None = None,
) -> list[SemanticMatchDecision]:
    """Read-only batch mapper from project semantics to historical canonical semantics."""
    if not semantics or not historicals:
        return []
    if extract_indexes is None:
        active_indexes = list(range(len(semantics)))
    else:
        active_indexes = []
        for raw_idx in extract_indexes:
            try:
                idx = int(raw_idx)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(semantics):
                active_indexes.append(idx)
    if not active_indexes:
        return []

    batch_size = max(1, int(batch_size or 1))
    if max_rendered_children is not None:
        max_children = max_rendered_children
    max_children = max(0, int(max_children or 0))
    extracted_block = _indexed_semantics(semantics, active_indexes)
    valid_extract_ids = set(active_indexes)
    by_pair: dict[tuple[int, int], SemanticMatchDecision] = {}

    batches = [list(historicals[i:i + batch_size]) for i in range(0, len(historicals), batch_size)]
    for batch_idx, batch in enumerate(batches):
        valid_historical_ids: set[int] = set()
        for item in batch:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            try:
                valid_historical_ids.add(int(item["id"]))
            except (TypeError, ValueError):
                continue
        if not valid_historical_ids:
            continue
        if logger:
            logger(f"[cyan]semantic-map[/cyan] batch={batch_idx + 1}/{len(batches)} extracted={len(active_indexes)} historicals={len(batch)}")
        prompt = prompts.semantic_map_prompt(extracted_block, batch, max_children=max_children)
        raw = await llm.json(prompt, schema_name="semantic_map")
        rows = ensure_list(raw, "items", "matches", "decisions")
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            strength = _coerce_strength(row.get("strength"))
            evidence = str(row.get("evidence") or "").strip()
            if strength is None or not evidence:
                continue
            try:
                decision = SemanticMatchDecision(
                    extract_index=int(row.get("extract_index")),
                    historical_id=int(row.get("historical_id")),
                    strength=strength,
                    evidence=evidence,
                )
            except (TypeError, ValueError):
                continue
            if decision.extract_index not in valid_extract_ids or decision.historical_id not in valid_historical_ids:
                continue
            key = (decision.extract_index, decision.historical_id)
            by_pair[key] = _adopt(by_pair.get(key), decision)

    return sorted(by_pair.values(), key=lambda d: (d.extract_index, d.historical_id))
